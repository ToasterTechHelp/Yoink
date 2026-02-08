"""API route handlers for the Yoink extraction service."""

import json
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from yoink.api.models import (
    ErrorResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    JobResponse,
    JobStatusResponse,
    ProgressInfo,
)
from yoink.api.worker import ExtractionWorker

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
UPLOAD_DIR = Path("./uploads")


@router.post(
    "/extract",
    response_model=JobResponse,
    status_code=202,
    responses={413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def extract(request: Request, file: UploadFile):
    """Upload a file and start an extraction job."""
    job_store = request.app.state.job_store
    worker: ExtractionWorker = request.app.state.worker

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
async def get_job_result(request: Request, background_tasks: BackgroundTasks, job_id: str):
    """Get the extraction result. Triggers cleanup after response is sent."""
    job_store = request.app.state.job_store
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] == "delivered":
        raise HTTPException(status_code=409, detail="Result already delivered and cleaned up")
    if job["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed yet. Current status: {job['status']}",
        )

    result_path = job["result_path"]
    if result_path is None or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="Result file not found")

    # Read result JSON
    with open(result_path, "r", encoding="utf-8") as f:
        result_data = json.load(f)

    # Schedule cleanup after response is sent
    background_tasks.add_task(
        _cleanup_after_delivery,
        job_store,
        job_id,
        job.get("upload_path"),
        result_path,
    )

    return result_data


async def _cleanup_after_delivery(
    job_store, job_id: str, upload_path: str | None, result_path: str | None
):
    """Mark job as delivered and clean up files."""
    try:
        ExtractionWorker.cleanup_job_files(upload_path, result_path)
        await job_store.update_status(job_id, "delivered")
        logger.info("Job %s delivered and cleaned up", job_id)
    except Exception:
        logger.exception("Failed to clean up job %s after delivery", job_id)


@router.delete(
    "/jobs/{job_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse}},
)
async def delete_job(request: Request, job_id: str):
    """Cancel and clean up a job."""
    job_store = request.app.state.job_store
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Clean up files
    ExtractionWorker.cleanup_job_files(job.get("upload_path"), job.get("result_path"))

    # Delete from DB
    await job_store.delete_job(job_id)
    logger.info("Job %s deleted", job_id)


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
