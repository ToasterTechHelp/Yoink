"""Tests for the DELETE /jobs/{job_id} route."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yoink.api import routes

HEX_JOB_ID = "0123456789abcdef0123456789abcdef"
DASHED_JOB_ID = "01234567-89ab-cdef-0123-456789abcdef"
OWNER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _client(supabase=object()) -> TestClient:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.state.supabase = supabase
    return TestClient(app)


def test_delete_requires_auth(monkeypatch):
    async def fake_get_optional_user(_request):
        return None

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)

    with _client() as client:
        resp = client.delete(f"/api/v1/jobs/{HEX_JOB_ID}")

    assert resp.status_code == 401


def test_delete_502_when_supabase_unconfigured(monkeypatch):
    async def fake_get_optional_user(_request):
        return OWNER_ID

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)

    with _client(supabase=None) as client:
        resp = client.delete(f"/api/v1/jobs/{HEX_JOB_ID}")

    assert resp.status_code == 502


def test_delete_422_for_invalid_job_id(monkeypatch):
    async def fake_get_optional_user(_request):
        return OWNER_ID

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)

    with _client() as client:
        resp = client.delete("/api/v1/jobs/not-a-uuid")

    assert resp.status_code == 422


def test_delete_missing_or_non_owned_returns_404(monkeypatch):
    """Strict ownership check — 404 when the job doesn't exist for this user."""
    async def fake_get_optional_user(_request):
        return OWNER_ID

    async def fake_get_user_job_status(_user_id, _job_id_hex, _supabase):
        return None

    scheduled: list = []

    def fake_add_task(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)
    monkeypatch.setattr(routes, "get_user_job_status", fake_get_user_job_status)
    monkeypatch.setattr(
        "starlette.background.BackgroundTasks.add_task", fake_add_task
    )

    with _client(supabase="supabase-client") as client:
        resp = client.delete(f"/api/v1/jobs/{HEX_JOB_ID}")

    assert resp.status_code == 404
    # Crucial: no background deletion was scheduled.
    assert scheduled == []


def test_delete_processing_job_returns_409(monkeypatch):
    """Cannot delete a job that hasn't finished processing yet."""
    async def fake_get_optional_user(_request):
        return OWNER_ID

    async def fake_get_user_job_status(_user_id, _job_id_hex, _supabase):
        return "processing"

    scheduled: list = []

    def fake_add_task(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)
    monkeypatch.setattr(routes, "get_user_job_status", fake_get_user_job_status)
    monkeypatch.setattr(
        "starlette.background.BackgroundTasks.add_task", fake_add_task
    )

    with _client(supabase="supabase-client") as client:
        resp = client.delete(f"/api/v1/jobs/{HEX_JOB_ID}")

    assert resp.status_code == 409
    assert scheduled == []


def test_delete_failed_job_is_allowed(monkeypatch):
    """Failed jobs should still be deletable so users can clear them."""
    async def fake_get_optional_user(_request):
        return OWNER_ID

    async def fake_get_user_job_status(_user_id, _job_id_hex, _supabase):
        return "failed"

    async def fake_delete_user_job_row(_user_id, _job_id_hex, _supabase):
        return None

    scheduled: list = []

    def fake_add_task(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)
    monkeypatch.setattr(routes, "get_user_job_status", fake_get_user_job_status)
    monkeypatch.setattr(routes, "delete_user_job_row", fake_delete_user_job_row)
    monkeypatch.setattr(
        "starlette.background.BackgroundTasks.add_task", fake_add_task
    )

    with _client(supabase="supabase-client") as client:
        resp = client.delete(f"/api/v1/jobs/{HEX_JOB_ID}")

    assert resp.status_code == 202
    assert len(scheduled) == 1


def test_delete_502_when_row_delete_fails(monkeypatch):
    """If the synchronous DB row delete fails, return 502 and don't schedule cleanup."""
    async def fake_get_optional_user(_request):
        return OWNER_ID

    async def fake_get_user_job_status(_user_id, _job_id_hex, _supabase):
        return "completed"

    async def failing_row_delete(*_args, **_kwargs):
        raise RuntimeError("db is down")

    scheduled: list = []

    def fake_add_task(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)
    monkeypatch.setattr(routes, "get_user_job_status", fake_get_user_job_status)
    monkeypatch.setattr(routes, "delete_user_job_row", failing_row_delete)
    monkeypatch.setattr(
        "starlette.background.BackgroundTasks.add_task", fake_add_task
    )

    with _client(supabase="supabase-client") as client:
        resp = client.delete(f"/api/v1/jobs/{HEX_JOB_ID}")

    assert resp.status_code == 502
    assert scheduled == []


def test_delete_schedules_background_task_and_returns_202(monkeypatch):
    """Happy path — verifies 202, normalized id, and that the background task is queued."""
    async def fake_get_optional_user(_request):
        return OWNER_ID

    async def fake_get_user_job_status(user_id, job_id_hex, supabase):
        assert user_id == OWNER_ID
        assert job_id_hex == HEX_JOB_ID
        assert supabase == "supabase-client"
        return "completed"

    async def fake_delete_user_job_row(_user_id, _job_id_hex, _supabase):
        return None

    scheduled: list = []

    def fake_add_task(self, func, *args, **kwargs):  # noqa: ANN001
        scheduled.append((func, args, kwargs))

    monkeypatch.setattr(routes, "get_optional_user", fake_get_optional_user)
    monkeypatch.setattr(routes, "get_user_job_status", fake_get_user_job_status)
    monkeypatch.setattr(routes, "delete_user_job_row", fake_delete_user_job_row)
    monkeypatch.setattr(
        "starlette.background.BackgroundTasks.add_task", fake_add_task
    )

    with _client(supabase="supabase-client") as client:
        # Accepts dashed form too — _normalize_job_id should strip dashes.
        resp = client.delete(f"/api/v1/jobs/{DASHED_JOB_ID}")

    assert resp.status_code == 202
    assert resp.json() == {"status": "deleting"}
    assert len(scheduled) == 1
    func, args, _ = scheduled[0]
    assert func is routes.delete_user_job_storage
    assert args == (OWNER_ID, HEX_JOB_ID, "supabase-client")
