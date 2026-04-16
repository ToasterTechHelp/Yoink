"""Supabase Storage helpers for uploading component images."""

import asyncio
import base64
import logging
import uuid
from typing import Any

from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)

BUCKET_NAME = "scans"


_UPLOAD_CONCURRENCY = 8  # max parallel Supabase Storage uploads
_UPLOAD_MAX_RETRIES = 3
_UPLOAD_RETRY_BACKOFF = 1.0  # seconds, doubles each retry


async def upload_components_to_supabase(
    user_id: str,
    job_id: str,
    result_data: dict[str, Any],
    supabase: SupabaseClient,
    supabase_url: str,
) -> list[dict[str, Any]]:
    """Upload component PNGs from pipeline output to Supabase Storage.

    Decodes base64 images from the result JSON, uploads each as a PNG
    concurrently (up to _UPLOAD_CONCURRENCY at a time), and returns
    component metadata with public storage URLs (no base64).

    Args:
        user_id: Authenticated user's UUID.
        job_id: The job identifier (used as storage subfolder).
        result_data: Pipeline output dict with pages[].components[].base64.
        supabase: Supabase client instance (service_role).
        supabase_url: Supabase project URL for constructing public URLs.

    Returns:
        Flat list of component dicts with 'url' replacing 'base64'.
    """
    storage_prefix = f"{user_id}/{job_id}"
    sem = asyncio.Semaphore(_UPLOAD_CONCURRENCY)
    loop = asyncio.get_running_loop()

    # Collect upload tasks and their corresponding metadata
    tasks: list[asyncio.Task] = []
    meta: list[dict[str, Any]] = []

    for page in result_data.get("pages", []):
        page_number = page["page_number"]
        for comp in page.get("components", []):
            comp_id = comp["id"]
            b64_data = comp.get("base64", "")
            if not b64_data:
                continue

            image_bytes = base64.b64decode(b64_data)
            object_path = f"{storage_prefix}/{comp_id}.png"
            public_url = (
                f"{supabase_url}/storage/v1/object/public/"
                f"{BUCKET_NAME}/{object_path}"
            )

            meta.append(
                {
                    "id": comp_id,
                    "page_number": page_number,
                    "category": comp.get("category", ""),
                    "original_label": comp.get("original_label", ""),
                    "confidence": comp.get("confidence", 0),
                    "bbox": comp.get("bbox", []),
                    "url": public_url,
                }
            )

            async def _upload(path: str = object_path, data: bytes = image_bytes) -> None:
                async with sem:
                    for attempt in range(_UPLOAD_MAX_RETRIES):
                        try:
                            await loop.run_in_executor(
                                None,
                                lambda: supabase.storage.from_(BUCKET_NAME).upload(
                                    path,
                                    data,
                                    file_options={
                                        "content-type": "image/png",
                                        "upsert": "true",
                                    },
                                ),
                            )
                            return
                        except Exception:
                            if attempt == _UPLOAD_MAX_RETRIES - 1:
                                raise
                            wait = _UPLOAD_RETRY_BACKOFF * (2 ** attempt)
                            logger.warning(
                                "Upload %s failed (attempt %d/%d), retrying in %.1fs",
                                path, attempt + 1, _UPLOAD_MAX_RETRIES, wait,
                            )
                            await asyncio.sleep(wait)

            tasks.append(asyncio.create_task(_upload()))

    # Run all uploads concurrently (bounded by semaphore)
    await asyncio.gather(*tasks)

    logger.info(
        "Uploaded %d components to Supabase Storage: %s",
        len(meta),
        storage_prefix,
    )
    return meta


async def create_job_in_supabase(
    user_id: str,
    job_id: str,
    title: str,
    supabase: SupabaseClient,
) -> None:
    """Insert a skeleton job row with status='processing' into Supabase Postgres.

    Called at upload time so the row exists before the worker starts,
    allowing the frontend to discover in-flight jobs after a refresh.

    Args:
        user_id: Authenticated user's UUID.
        job_id: The job identifier (32-char hex).
        title: Original filename.
        supabase: Supabase client instance (service_role).
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: supabase.table("jobs").insert(
            {
                "id": job_id,
                "user_id": user_id,
                "status": "processing",
                "title": title,
                "total_pages": 0,
                "total_components": 0,
                "results": None,
                "storage_path": None,
            }
        ).execute(),
    )
    logger.info("Created processing job %s in Supabase for user %s", job_id, user_id)


async def complete_job_in_supabase(
    user_id: str,
    job_id: str,
    title: str,
    total_pages: int,
    total_components: int,
    components: list[dict[str, Any]],
    supabase: SupabaseClient,
    source_type: str = "pdf",
) -> None:
    """Update an existing job row to status='completed' with results.

    Args:
        user_id: Authenticated user's UUID.
        job_id: The job identifier.
        title: Original filename.
        total_pages: Number of pages extracted.
        total_components: Number of components extracted.
        components: List of component metadata dicts (with URLs).
        supabase: Supabase client instance (service_role).
        source_type: "pdf" or "images" — persisted in results JSON.
    """
    storage_path = f"scans/{user_id}/{job_id}/"

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: supabase.table("jobs").update(
            {
                "status": "completed",
                "title": title,
                "total_pages": total_pages,
                "total_components": total_components,
                "results": {"components": components, "source_type": source_type},
                "storage_path": storage_path,
                "source_type": source_type,
            }
        ).eq("id", job_id).execute(),
    )
    logger.info("Completed job %s in Supabase for user %s", job_id, user_id)


_LIST_PAGE_SIZE = 100


async def delete_user_job(
    user_id: str,
    job_id_hex: str,
    supabase: SupabaseClient,
) -> None:
    """Delete storage objects and the jobs row for a user-owned job.

    Paginates the storage listing so jobs with >100 component PNGs are fully
    cleaned up. Runs as a FastAPI BackgroundTask — must never raise into the
    response cycle. Logs and swallows exceptions.
    """
    try:
        loop = asyncio.get_running_loop()
        storage_prefix = f"{user_id}/{job_id_hex}"

        total_deleted = 0
        offset = 0
        while True:
            files = await loop.run_in_executor(
                None,
                lambda off=offset: supabase.storage.from_(BUCKET_NAME).list(
                    storage_prefix,
                    {"limit": _LIST_PAGE_SIZE, "offset": off},
                ),
            )
            if not files:
                break

            paths = [f"{storage_prefix}/{f['name']}" for f in files]
            await loop.run_in_executor(
                None,
                lambda p=paths: supabase.storage.from_(BUCKET_NAME).remove(p),
            )
            total_deleted += len(paths)

            # Last page — stop before issuing another list() that would return empty.
            if len(files) < _LIST_PAGE_SIZE:
                break
            # We just deleted this batch, so the next "page" starts back at offset 0.
            offset = 0

        logger.info(
            "Deleted %d storage objects for job %s", total_deleted, job_id_hex
        )

        job_uuid = str(uuid.UUID(job_id_hex))
        await loop.run_in_executor(
            None,
            lambda: supabase.table("jobs")
            .delete()
            .eq("id", job_uuid)
            .eq("user_id", user_id)
            .execute(),
        )
        logger.info("Deleted jobs row %s for user %s", job_id_hex, user_id)
    except Exception:
        logger.exception(
            "Background delete failed for job %s (user %s)", job_id_hex, user_id
        )


async def fail_job_in_supabase(
    job_id: str,
    supabase: SupabaseClient,
) -> None:
    """Update an existing job row to status='failed'.

    Args:
        job_id: The job identifier.
        supabase: Supabase client instance (service_role).
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: supabase.table("jobs").update(
            {"status": "failed"}
        ).eq("id", job_id).execute(),
    )
    logger.info("Marked job %s as failed in Supabase", job_id)
