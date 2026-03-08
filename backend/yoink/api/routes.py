"""API route handlers for the Yoink extraction service."""

import json
import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from time import perf_counter
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile

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
    RenameJobRequest,
    RenameJobResponse,
    ResultMetadataResponse,
)
from yoink.api.transparent_render import (
    MAX_SOURCE_IMAGE_BYTES,
    load_source_bytes,
    make_background_transparent,
    parse_and_validate_source_url,
)
from yoink.api.user_jobs import (
    count_user_jobs,
    delete_user_job,
    get_user_job,
    rename_user_job,
)
from yoink.api.storage import create_job_in_supabase
from yoink.api.worker import ExtractionWorker

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_UPLOAD_FILES = 50
MAX_USER_SLOTS = 5
UPLOAD_DIR = Path("./uploads")
API_URL = os.environ.get("YOINK_API_URL", "http://127.0.0.1:8000")
MAX_BASE_NAME_LENGTH = 120
INVALID_BASE_NAME_PATTERN = re.compile(r"[\\/]|[\x00-\x1f\x7f]")

SENSITIVITY_PRESETS = {
    "fastest": 0.5,
    "fast": 0.35,
    "balanced": 0.2,
    "thorough": 0.1,
    "most_thorough": 0.05,
}


def _normalize_job_id(job_id: str) -> str:
    """Normalize supported job ID formats to lowercase 32-char hex."""
    try:
        return uuid.UUID(job_id).hex
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid job ID format") from exc


def _validate_base_name(base_name: str) -> str:
    """Validate and sanitize rename base name."""
    cleaned = base_name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    if len(cleaned) > MAX_BASE_NAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Name must be at most {MAX_BASE_NAME_LENGTH} characters",
        )
    if INVALID_BASE_NAME_PATTERN.search(cleaned):
        raise HTTPException(
            status_code=422,
            detail="Name cannot contain slashes or control characters",
        )
    return cleaned


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
async def extract(
    request: Request,
    files: List[UploadFile] = File(...),
    sensitivity: str = Form("balanced"),
):
    """Upload one or more files and start an extraction job.

    - Single PDF or image: processed as before.
    - Multiple files: all must be images (no PDFs). Each image becomes a "page".
    - Guest (no token): results saved to /static/guest/{job_id}/
    - User (valid token): results uploaded to Supabase Storage.
      Rejected if user already has 5 saved jobs.
    """
    job_store = request.app.state.job_store
    worker: ExtractionWorker = request.app.state.worker
    supabase = request.app.state.supabase
    conf = SENSITIVITY_PRESETS.get(sensitivity, 0.2)

    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=422,
            detail=f"Too many files. Maximum is {MAX_UPLOAD_FILES}.",
        )

    # When multiple files are uploaded, all must be images
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
    if len(files) > 1:
        for f in files:
            ext = Path(f.filename or "").suffix.lower()
            if ext not in IMAGE_EXTENSIONS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Multi-file upload only supports images. '{f.filename}' is not an image.",
                )

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

    # Read all file contents and check total size
    file_contents: list[tuple[str, bytes]] = []
    total_size = 0
    for f in files:
        content = await f.read()
        total_size += len(content)
        file_contents.append((f.filename or "upload", content))

    if total_size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Total upload size too large. Maximum is {MAX_UPLOAD_SIZE // (1024*1024)}MB.",
        )

    # Save uploads to a unique directory
    upload_id = uuid.uuid4().hex
    upload_dir = UPLOAD_DIR / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    for idx, (filename, content) in enumerate(file_contents):
        # Index-prefix filenames to avoid collisions
        safe_name = f"{idx}_{filename}" if len(file_contents) > 1 else filename
        upload_path = upload_dir / safe_name
        upload_path.write_bytes(content)
        saved_paths.append(upload_path)
        logger.info("Saved upload: %s (%d bytes)", upload_path, len(content))

    # Display name for the job
    if len(files) == 1:
        display_name = files[0].filename or "upload"
    else:
        display_name = f"{len(files)} images"

    # Extra paths for multi-image (all paths beyond the first)
    extra_paths_json: str | None = None
    if len(saved_paths) > 1:
        extra_paths_json = json.dumps([str(p) for p in saved_paths[1:]])

    # Create job and enqueue
    job_id = await job_store.create_job(
        filename=display_name,
        upload_path=str(saved_paths[0]),
        user_id=user_id,
        conf=conf,
        extra_paths=extra_paths_json,
    )

    # For authenticated users, create a Supabase row immediately so the
    # job is visible in "Recent Uploads" even if the user refreshes.
    if user_id and supabase:
        try:
            await create_job_in_supabase(user_id, job_id, display_name, supabase)
        except Exception:
            # Supabase INSERT failed — clean up SQLite job + uploaded file
            logger.exception("Failed to create Supabase job row for %s", job_id)
            await job_store.delete_job(job_id)
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise HTTPException(status_code=502, detail="Failed to create job record")

    await worker.enqueue(job_id)

    return JobResponse(job_id=job_id, status="queued")


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_job_status(request: Request, job_id: str):
    """Get the status and progress of a job."""
    job_id = _normalize_job_id(job_id)
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
    job_id = _normalize_job_id(job_id)
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

    source_type = result_data.get("source_type", "pdf")

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
            source_type=source_type,
        )
    else:
        return ResultMetadataResponse(
            source_file=result_data["source_file"],
            total_pages=result_data["total_pages"],
            total_components=result_data["total_components"],
            is_guest=False,
            source_type=source_type,
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
    job_id = _normalize_job_id(job_id)
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


@router.get(
    "/render/transparent.png",
    responses={
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def render_transparent_png(request: Request, src: str = Query(..., min_length=1)):
    """Render a transparent-background PNG from a supported source image URL."""
    started = perf_counter()
    source_kind = "unknown"

    try:
        source = parse_and_validate_source_url(
            src=src,
            supabase_url=request.app.state.supabase_url or "",
            api_url=API_URL,
        )
        source_kind = source.kind
    except ValueError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "transparent_render source_kind=%s status=invalid elapsed_ms=%d detail=%s",
            source_kind,
            elapsed_ms,
            str(exc),
        )
        raise HTTPException(status_code=422, detail="Invalid or unsupported source URL") from exc

    try:
        image_bytes = await load_source_bytes(
            source=source,
            supabase=request.app.state.supabase,
            static_dir=Path(os.environ.get("YOINK_STATIC_DIR", "./static")),
        )
    except FileNotFoundError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "transparent_render source_kind=%s status=missing elapsed_ms=%d",
            source_kind,
            elapsed_ms,
        )
        raise HTTPException(status_code=404, detail="Source image not found") from exc
    except ValueError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "transparent_render source_kind=%s status=invalid elapsed_ms=%d detail=%s",
            source_kind,
            elapsed_ms,
            str(exc),
        )
        raise HTTPException(status_code=422, detail="Invalid source path") from exc
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.exception(
            "transparent_render source_kind=%s status=error stage=load elapsed_ms=%d",
            source_kind,
            elapsed_ms,
        )
        raise HTTPException(status_code=502, detail="Failed to load source image") from exc

    if len(image_bytes) > MAX_SOURCE_IMAGE_BYTES:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "transparent_render source_kind=%s status=too_large elapsed_ms=%d bytes=%d",
            source_kind,
            elapsed_ms,
            len(image_bytes),
        )
        raise HTTPException(
            status_code=413,
            detail=f"Source image is too large (max {MAX_SOURCE_IMAGE_BYTES} bytes)",
        )

    try:
        output_bytes = make_background_transparent(image_bytes)
    except ValueError as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.info(
            "transparent_render source_kind=%s status=invalid elapsed_ms=%d detail=%s",
            source_kind,
            elapsed_ms,
            str(exc),
        )
        raise HTTPException(status_code=422, detail="Unsupported image data") from exc
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.exception(
            "transparent_render source_kind=%s status=error stage=transform elapsed_ms=%d",
            source_kind,
            elapsed_ms,
        )
        raise HTTPException(status_code=502, detail="Failed to render transparent image") from exc

    elapsed_ms = int((perf_counter() - started) * 1000)
    logger.info(
        "transparent_render source_kind=%s status=ok elapsed_ms=%d",
        source_kind,
        elapsed_ms,
    )
    return Response(
        content=output_bytes,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/jobs/{job_id}",
    status_code=204,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def delete_job(request: Request, job_id: str):
    """Cancel and clean up a job.

    - Authenticated user jobs are deleted from Supabase (source of truth).
    - Guest jobs cannot be manually deleted.
    """
    requester_id = await get_optional_user(request)
    if requester_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    job_id = _normalize_job_id(job_id)
    job_store = request.app.state.job_store
    supabase = request.app.state.supabase

    # Explicitly block manual guest delete when a local guest job exists.
    local_job = await job_store.get_job(job_id)
    if local_job is not None and local_job.get("user_id") is None:
        raise HTTPException(status_code=403, detail="Guest jobs cannot be deleted manually")

    if supabase is None:
        raise HTTPException(status_code=502, detail="Supabase is not configured")

    # Supabase is authoritative for authenticated user jobs.
    if await get_user_job(requester_id, job_id, supabase) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        await delete_user_job(requester_id, job_id, supabase)
    except Exception:
        logger.exception(
            "Delete failed at Supabase stage (job_id=%s requester_id=%s stage=supabase_delete)",
            job_id,
            requester_id,
        )
        raise HTTPException(status_code=502, detail="Failed to delete job resources")

    # Best-effort local cleanup for drifted local rows.
    if local_job is not None:
        ExtractionWorker.cleanup_job_files(local_job.get("upload_path"), local_job.get("result_path"))
        await job_store.delete_job(job_id)

    logger.info("Deleted user job %s for requester %s", job_id, requester_id)


@router.patch(
    "/jobs/{job_id}/rename",
    response_model=RenameJobResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def rename_job(request: Request, job_id: str, body: RenameJobRequest):
    """Rename a saved upload for an authenticated user."""
    requester_id = await get_optional_user(request)
    if requester_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    job_id = _normalize_job_id(job_id)
    supabase = request.app.state.supabase

    if supabase is None:
        raise HTTPException(status_code=502, detail="Supabase is not configured")

    user_job = await get_user_job(requester_id, job_id, supabase)
    if user_job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    base_name = _validate_base_name(body.base_name)
    old_title = user_job.title
    extension = Path(old_title).suffix
    new_title = f"{base_name}{extension}"

    if old_title == new_title:
        return RenameJobResponse(job_id=job_id, title=new_title)

    try:
        await rename_user_job(
            user_id=requester_id,
            job_id_hex=job_id,
            title=new_title,
            supabase=supabase,
        )
    except Exception:
        logger.exception(
            "Rename failed at Supabase stage (job_id=%s requester_id=%s stage=supabase_rename)",
            job_id,
            requester_id,
        )
        raise HTTPException(
            status_code=502,
            detail="Failed to rename job",
        )

    # Best-effort local sync if a matching local user row still exists.
    job_store = request.app.state.job_store
    local_job = await job_store.get_job(job_id)
    if local_job is not None and local_job.get("user_id") == requester_id:
        await job_store.rename_job(job_id, new_title)

    return RenameJobResponse(job_id=job_id, title=new_title)


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    responses={404: {"model": ErrorResponse}},
)
async def submit_feedback(request: Request, body: FeedbackRequest):
    """Submit a bug report or content violation report for a job."""
    job_store = request.app.state.job_store
    job_id = _normalize_job_id(body.job_id)

    # Verify the job exists
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    feedback_id = await job_store.create_feedback(
        job_id=job_id,
        feedback_type=body.type,
        message=body.message,
    )
    return FeedbackResponse(feedback_id=feedback_id)


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    """Health check endpoint."""
    model_loaded = hasattr(request.app.state, "extractor") and request.app.state.extractor is not None
    return HealthResponse(status="ok", model_loaded=model_loaded)
