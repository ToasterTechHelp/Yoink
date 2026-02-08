"""JobStore: Async SQLite-backed job state management."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite

logger = logging.getLogger(__name__)

JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'queued',
    filename     TEXT NOT NULL,
    upload_path  TEXT,
    result_path  TEXT,
    error        TEXT,
    current_page INTEGER DEFAULT 0,
    total_pages  INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""

FEEDBACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id         TEXT PRIMARY KEY,
    job_id     TEXT NOT NULL,
    type       TEXT NOT NULL CHECK(type IN ('bug', 'content_violation')),
    message    TEXT,
    created_at TEXT NOT NULL
);
"""

VALID_STATUSES = {"queued", "processing", "completed", "failed", "delivered"}


class JobStore:
    """Lightweight async SQLite job store."""

    def __init__(self, db_path: str = "yoink_jobs.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(JOBS_SCHEMA)
        await self._db.execute(FEEDBACK_SCHEMA)
        await self._db.commit()
        logger.info("JobStore initialized: %s", self._db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def create_job(self, filename: str, upload_path: str) -> str:
        job_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO jobs (id, status, filename, upload_path, created_at, updated_at)
               VALUES (?, 'queued', ?, ?, ?, ?)""",
            (job_id, filename, upload_path, now, now),
        )
        await self._db.commit()
        logger.info("Created job %s for file '%s'", job_id, filename)
        return job_id

    async def get_job(self, job_id: str) -> dict | None:
        cursor = await self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def update_status(self, job_id: str, status: str, **kwargs) -> None:
        assert status in VALID_STATUSES, f"Invalid status: {status}"
        now = datetime.now(timezone.utc).isoformat()
        # Build dynamic SET clause for extra fields
        fields = ["status = ?", "updated_at = ?"]
        values = [status, now]
        for key, val in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(val)
        values.append(job_id)
        sql = f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?"
        await self._db.execute(sql, values)
        await self._db.commit()

    async def update_progress(self, job_id: str, current_page: int, total_pages: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "UPDATE jobs SET current_page = ?, total_pages = ?, updated_at = ? WHERE id = ?",
            (current_page, total_pages, now, job_id),
        )
        await self._db.commit()

    async def delete_job(self, job_id: str) -> bool:
        cursor = await self._db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """Delete jobs older than max_age_hours. Returns count of deleted jobs."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        cursor = await self._db.execute(
            "SELECT id, upload_path, result_path FROM jobs WHERE created_at < ?",
            (cutoff,),
        )
        old_jobs = await cursor.fetchall()

        if not old_jobs:
            return 0

        job_ids = [row["id"] for row in old_jobs]
        placeholders = ",".join("?" * len(job_ids))
        await self._db.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
        await self._db.commit()

        # Return paths for file cleanup (caller handles actual deletion)
        logger.info("Cleaned up %d old jobs", len(old_jobs))
        return len(old_jobs)

    async def get_old_job_paths(self, max_age_hours: int = 24) -> list[dict]:
        """Get file paths of jobs older than max_age_hours for cleanup."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()
        cursor = await self._db.execute(
            "SELECT id, upload_path, result_path FROM jobs WHERE created_at < ?",
            (cutoff,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # ---- Feedback ----

    async def create_feedback(
        self, job_id: str, feedback_type: str, message: str | None = None,
    ) -> str:
        """Store a feedback entry. Returns the feedback id."""
        feedback_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """INSERT INTO feedback (id, job_id, type, message, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (feedback_id, job_id, feedback_type, message, now),
        )
        await self._db.commit()
        logger.info("Feedback %s created for job %s (type=%s)", feedback_id, job_id, feedback_type)
        return feedback_id
