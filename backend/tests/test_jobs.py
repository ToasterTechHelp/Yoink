"""Tests for yoink.api.jobs — JobStore."""

import asyncio

import pytest
import pytest_asyncio

from yoink.api.jobs import JobStore


@pytest_asyncio.fixture
async def job_store(tmp_path):
    """Create a JobStore backed by a temp SQLite DB."""
    store = JobStore(db_path=str(tmp_path / "test_jobs.db"))
    await store.init()
    yield store
    await store.close()


@pytest.mark.asyncio
async def test_create_and_get_job(job_store):
    job_id = await job_store.create_job("lecture.pdf", "/tmp/uploads/lecture.pdf")
    assert len(job_id) == 32  # hex UUID

    job = await job_store.get_job(job_id)
    assert job is not None
    assert job["filename"] == "lecture.pdf"
    assert job["status"] == "queued"
    assert job["upload_path"] == "/tmp/uploads/lecture.pdf"
    assert job["current_page"] == 0
    assert job["total_pages"] == 0


@pytest.mark.asyncio
async def test_get_nonexistent_job(job_store):
    job = await job_store.get_job("nonexistent")
    assert job is None


@pytest.mark.asyncio
async def test_update_status(job_store):
    job_id = await job_store.create_job("test.pdf", "/tmp/test.pdf")
    await job_store.update_status(job_id, "processing")

    job = await job_store.get_job(job_id)
    assert job["status"] == "processing"


@pytest.mark.asyncio
async def test_update_status_with_extra_fields(job_store):
    job_id = await job_store.create_job("test.pdf", "/tmp/test.pdf")
    await job_store.update_status(job_id, "failed", error="Something broke")

    job = await job_store.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error"] == "Something broke"


@pytest.mark.asyncio
async def test_update_progress(job_store):
    job_id = await job_store.create_job("test.pdf", "/tmp/test.pdf")
    await job_store.update_progress(job_id, 5, 10)

    job = await job_store.get_job(job_id)
    assert job["current_page"] == 5
    assert job["total_pages"] == 10


@pytest.mark.asyncio
async def test_delete_job(job_store):
    job_id = await job_store.create_job("test.pdf", "/tmp/test.pdf")
    deleted = await job_store.delete_job(job_id)
    assert deleted is True

    job = await job_store.get_job(job_id)
    assert job is None


@pytest.mark.asyncio
async def test_delete_nonexistent_job(job_store):
    deleted = await job_store.delete_job("nonexistent")
    assert deleted is False


@pytest.mark.asyncio
async def test_invalid_status_raises(job_store):
    job_id = await job_store.create_job("test.pdf", "/tmp/test.pdf")
    with pytest.raises(AssertionError, match="Invalid status"):
        await job_store.update_status(job_id, "bogus")
