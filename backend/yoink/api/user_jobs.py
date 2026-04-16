"""Supabase-backed operations for authenticated user jobs."""

import asyncio
import logging
import uuid

from supabase import Client as SupabaseClient

logger = logging.getLogger(__name__)


async def count_user_jobs(user_id: str, supabase: SupabaseClient) -> int:
    """Count how many saved jobs a user has in Supabase."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("jobs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute(),
    )
    return result.count or 0


async def get_user_job_status(
    user_id: str, job_id_hex: str, supabase: SupabaseClient
) -> str | None:
    """Return the status of a user-owned job, or None if it doesn't exist."""
    job_uuid = str(uuid.UUID(job_id_hex))
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: supabase.table("jobs")
        .select("status")
        .eq("id", job_uuid)
        .eq("user_id", user_id)
        .limit(1)
        .execute(),
    )
    if not result.data:
        return None
    return result.data[0].get("status")
