"""API route handlers for the Yoink extraction service."""

import json
import logging
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from yoink.api.auth import get_optional_user
from yoink.api.models import (
    ComponentBatchResponse,
    ComponentOut,
    ErrorResponse,
    FeedbackRequest,
    FeedbackResponse,
    GuestResultResponse,
    HealthResponse,
    JobResponse,
    JobStatusResponse,
    ProgressInfo,
    ResultMetadataResponse,
)
from yoink.api.storage import count_user_jobs, delete_job_from_supabase
from yoink.api.worker import ExtractionWorker

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_USER_SLOTS = 5
UPLOAD_DIR = Path("./uploads")
API_URL = os.environ.get("YOINK_API_URL", "http://127.0.0.1:8000")


@router.post(
    "/extract",
    response_model=JobResponse,
    status_code=202,
    responses={
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def extract(request: Request, file: UploadFile):
    """Upload a file and start an extraction job.

    - Guest (no token): 1 file, results saved to /static/guest/{job_id}/
    - User (valid token): 1 file, results uploaded to Supabase Storage.
      Rejected if user already has 5 saved jobs.
    """
    job_store = request.app.state.job_store
    worker: ExtractionWorker = request.app.state.worker
    supabase = request.app.state.supabase

    # Authenticate (optional)
    user_id = await get_optional_user(request)

    # Enforce 5-slot limit for authenticated users
    if user_id and supabase:
        slot_count = await count_user_jobs(user_id, supabase)
        if slot_count >= MAX_USER_SLOTS:
            raise HTTPException(
                status_code=409,
                detail=f"Slot limit reached ({slot_count}/{MAX_USER_SLOTS}). Delete a job to continue.",
            )

    # Read file content and check size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB.",
        )

    # Save upload to a unique directory
    upload_id = uuid.uuid4().hex
    upload_dir = UPLOAD_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / file.filename
    upload_path.write_bytes(content)
    logger.info("Saved upload: %s (%d bytes)", upload_path, len(content))

    # Create job and enqueue
    job_id = await job_store.create_job(
        filename=file.filename,
        upload_path=str(upload_path),
        user_id=user_id,
    )
    await worker.enqueue(job_id)

    return JobResponse(job_id=job_id, status="queued")


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_job_status(request: Request, job_id: str):
    """Get the status and progress of a job."""
    job_id = job_id.replace("-", "")
    job_store = request.app.state.job_store
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        filename=job["filename"],
        progress=ProgressInfo(
            current_page=job["current_page"],
            total_pages=job["total_pages"],
        ),
        error=job["error"],
        created_at=job["created_at"],
    )


@router.get(
    "/jobs/{job_id}/result",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def get_job_result(request: Request, job_id: str):
    """Get extraction result.

    - Guest jobs: returns full GuestResultResponse with static URLs.
    - User jobs: returns ResultMetadataResponse (frontend reads from Supabase).
    """
    job_id = job_id.replace("-", "")
    job_store = request.app.state.job_store
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed yet. Current status: {job['status']}",
        )

    result_path = job["result_path"]
    if result_path is None or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    with open(result_path, "r", encoding="utf-8") as f:
        result_data = json.load(f)

    is_guest = job["user_id"] is None

    if is_guest:
        # Build static URLs for guest components
        components = []
        for page in result_data.get("pages", []):
            for comp in page.get("components", []):
                components.append(
                    ComponentOut(
                        id=comp["id"],
                        page_number=page["page_number"],
                        category=comp.get("category", ""),
                        original_label=comp.get("original_label", ""),
                        confidence=comp.get("confidence", 0),
                        bbox=comp.get("bbox", []),
                        url=f"{API_URL}/static/guest/{job_id}/{comp['id']}.png",
                    )
                )
        return GuestResultResponse(
            source_file=result_data["source_file"],
            total_pages=result_data["total_pages"],
            total_components=result_data["total_components"],
            components=components,
        )
    else:
        return ResultMetadataResponse(
            source_file=result_data["source_file"],
            total_pages=result_data["total_pages"],
            total_components=result_data["total_components"],
            is_guest=False,
        )


@router.get(
    "/jobs/{job_id}/result/components",
    response_model=ComponentBatchResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def get_result_components(
    request: Request, job_id: str, offset: int = 0, limit: int = 10,
):
    """Get a batch of components from the extraction result.

    Primarily used for guest jobs. User jobs read directly from Supabase.
    Returns components with static URLs (no base64).
    """
    job_id = job_id.replace("-", "")
    job_store = request.app.state.job_store
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed yet. Current status: {job['status']}",
        )

    result_path = job["result_path"]
    if result_path is None or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    with open(result_path, "r", encoding="utf-8") as f:
        result_data = json.load(f)

    is_guest = job["user_id"] is None

    # Flatten all components across pages, preserving page_number
    all_components = []
    for page in result_data["pages"]:
        for comp in page["components"]:
            comp_out = {
                "id": comp["id"],
                "page_number": page["page_number"],
                "category": comp.get("category", ""),
                "original_label": comp.get("original_label", ""),
                "confidence": comp.get("confidence", 0),
                "bbox": comp.get("bbox", []),
            }
            if is_guest:
                comp_out["url"] = f"{API_URL}/static/guest/{job_id}/{comp['id']}.png"
            else:
                comp_out["url"] = comp.get("url", "")
            all_components.append(comp_out)

    total = len(all_components)
    batch = all_components[offset : offset + limit]
    has_more = (offset + limit) < total

    return ComponentBatchResponse(
        offset=offset,
        limit=limit,
        total=total,
        has_more=has_more,
        components=batch,
    )


@router.delete(
    "/jobs/{job_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
)
async def delete_job(request: Request, job_id: str):
    """Cancel and clean up a job.

    - Guest: cleans local files + SQLite row.
    - User: also deletes Supabase DB row + Storage objects.
    """
    # Normalize: Supabase returns UUIDs with dashes, SQLite stores hex (no dashes)
    job_id = job_id.replace("-", "")

    job_store = request.app.state.job_store
    supabase = request.app.state.supabase

    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    user_id = job.get("user_id")

    # Clean up local files
    ExtractionWorker.cleanup_job_files(job.get("upload_path"), job.get("result_path"))

    # Clean up guest static files
    if user_id is None:
        guest_static_dir = Path("./static/guest") / job_id
        if guest_static_dir.exists():
            shutil.rmtree(guest_static_dir, ignore_errors=True)

    # Clean up Supabase resources for user jobs
    if user_id and supabase:
        await delete_job_from_supabase(user_id, job_id, supabase)

    # Delete from SQLite
    await job_store.delete_job(job_id)
    logger.info("Job %s deleted (user=%s)", job_id, user_id or "guest")


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    responses={404: {"model": ErrorResponse}},
)
async def submit_feedback(request: Request, body: FeedbackRequest):
    """Submit a bug report or content violation report for a job."""
    job_store = request.app.state.job_store

    # Verify the job exists
    job = await job_store.get_job(body.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    feedback_id = await job_store.create_feedback(
        job_id=body.job_id,
        feedback_type=body.type,
        message=body.message,
    )
    return FeedbackResponse(feedback_id=feedback_id)


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    """Health check endpoint."""
    model_loaded = hasattr(request.app.state, "extractor") and request.app.state.extractor is not None
    return HealthResponse(status="ok", model_loaded=model_loaded)
