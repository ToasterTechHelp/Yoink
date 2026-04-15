"""Supabase-backed operations for authenticated user jobs."""

import asyncio
import logging

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
