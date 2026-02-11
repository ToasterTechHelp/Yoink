"""Supabase Storage helpers for uploading/deleting component images."""

import asyncio
import base64
import json
import logging
from pathlib import Path
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


async def save_job_to_supabase(
    user_id: str,
    job_id: str,
    title: str,
    total_pages: int,
    total_components: int,
    components: list[dict[str, Any]],
    supabase: SupabaseClient,
) -> None:
    """Insert a completed job row into Supabase Postgres.

    Args:
        user_id: Authenticated user's UUID.
        job_id: The job identifier.
        title: Original filename.
        total_pages: Number of pages extracted.
        total_components: Number of components extracted.
        components: List of component metadata dicts (with URLs).
        supabase: Supabase client instance (service_role).
    """
    storage_path = f"scans/{user_id}/{job_id}/"

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: supabase.table("jobs").insert(
            {
                "id": job_id,
                "user_id": user_id,
                "status": "completed",
                "title": title,
                "total_pages": total_pages,
                "total_components": total_components,
                "results": {"components": components},
                "storage_path": storage_path,
            }
        ).execute(),
    )
    logger.info("Saved job %s to Supabase for user %s", job_id, user_id)


async def delete_job_from_supabase(
    user_id: str,
    job_id: str,
    supabase: SupabaseClient,
) -> None:
    """Delete a job's Supabase DB row and all its Storage objects.

    Args:
        user_id: Authenticated user's UUID.
        job_id: The job identifier.
        supabase: Supabase client instance (service_role).
    """
    loop = asyncio.get_running_loop()

    # List and delete all storage objects for this job
    storage_prefix = f"{user_id}/{job_id}"
    try:
        files = await loop.run_in_executor(
            None,
            lambda: supabase.storage.from_(BUCKET_NAME).list(storage_prefix),
        )
        if files:
            paths = [f"{storage_prefix}/{f['name']}" for f in files]
            await loop.run_in_executor(
                None,
                lambda: supabase.storage.from_(BUCKET_NAME).remove(paths),
            )
            logger.info("Deleted %d storage objects for job %s", len(paths), job_id)
    except Exception:
        logger.exception("Error cleaning up storage for job %s", job_id)

    # Delete the DB row
    try:
        await loop.run_in_executor(
            None,
            lambda: supabase.table("jobs").delete().eq("id", job_id).execute(),
        )
        logger.info("Deleted Supabase job row %s", job_id)
    except Exception:
        logger.exception("Error deleting Supabase job row %s", job_id)


async def count_user_jobs(user_id: str, supabase: SupabaseClient) -> int:
    """Count how many saved jobs a user has in Supabase.

    Args:
        user_id: Authenticated user's UUID.
        supabase: Supabase client instance (service_role).

    Returns:
        Number of jobs the user currently has.
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("jobs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute(),
    )
    return result.count or 0
