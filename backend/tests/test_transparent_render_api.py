"""Tests for transparent render endpoint and transform helper."""

from __future__ import annotations

import io

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from yoink.api import routes
from yoink.api.transparent_render import (
    MAX_SOURCE_IMAGE_BYTES,
    make_background_transparent,
)


class _DummyBucket:
    def __init__(self, payloads: dict[str, bytes | Exception]):
        self._payloads = payloads

    def download(self, path: str):
        payload = self._payloads.get(path)
        if payload is None:
            raise FileNotFoundError(path)
        if isinstance(payload, Exception):
            raise payload
        return payload


class _DummyStorage:
    def __init__(self, payloads: dict[str, bytes | Exception]):
        self._payloads = payloads

    def from_(self, bucket_name: str):
        assert bucket_name == "scans"
        return _DummyBucket(self._payloads)


class _DummySupabase:
    def __init__(self, payloads: dict[str, bytes | Exception]):
        self.storage = _DummyStorage(payloads)


def _png_bytes(pixels: list[tuple[int, int, int, int]], size: tuple[int, int]) -> bytes:
    image = Image.new("RGBA", size)
    image.putdata(pixels)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _client(supabase, supabase_url: str) -> TestClient:
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/v1")
    app.state.supabase = supabase
    app.state.supabase_url = supabase_url
    return TestClient(app)


def test_render_transparent_from_supabase_public_url():
    object_path = "user/job/1.png"
    source_bytes = _png_bytes([(255, 255, 255, 255)], (1, 1))
    supabase_url = "https://example.supabase.co"
    source_url = f"{supabase_url}/storage/v1/object/public/scans/{object_path}"

    with _client(_DummySupabase({object_path: source_bytes}), supabase_url) as client:
        resp = client.get("/api/v1/render/transparent.png", params={"src": source_url})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers["cache-control"] == "public, max-age=86400"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.content


def test_render_transparent_from_guest_static_url(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    guest_file = static_dir / "guest" / "abc123" / "2.png"
    guest_file.parent.mkdir(parents=True, exist_ok=True)
    guest_file.write_bytes(_png_bytes([(240, 240, 240, 255)], (1, 1)))
    monkeypatch.setenv("YOINK_STATIC_DIR", str(static_dir))

    source_url = f"{routes.API_URL}/static/guest/abc123/2.png"
    with _client(None, "https://example.supabase.co") as client:
        resp = client.get("/api/v1/render/transparent.png", params={"src": source_url})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_render_transparent_rejects_invalid_host():
    source_url = "https://evil.example.com/storage/v1/object/public/scans/user/job/1.png"
    with _client(None, "https://example.supabase.co") as client:
        resp = client.get("/api/v1/render/transparent.png", params={"src": source_url})
    assert resp.status_code == 422


def test_render_transparent_rejects_guest_path_traversal(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("YOINK_STATIC_DIR", str(static_dir))

    source_url = f"{routes.API_URL}/static/guest/../secret.png"
    with _client(None, "https://example.supabase.co") as client:
        resp = client.get("/api/v1/render/transparent.png", params={"src": source_url})
    assert resp.status_code == 422


def test_render_transparent_returns_404_when_source_missing(tmp_path, monkeypatch):
    static_dir = tmp_path / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("YOINK_STATIC_DIR", str(static_dir))

    source_url = f"{routes.API_URL}/static/guest/missing/1.png"
    with _client(None, "https://example.supabase.co") as client:
        resp = client.get("/api/v1/render/transparent.png", params={"src": source_url})
    assert resp.status_code == 404


def test_render_transparent_returns_413_when_source_too_large():
    object_path = "user/job/large.png"
    source_url = f"https://example.supabase.co/storage/v1/object/public/scans/{object_path}"
    payload = b"\x00" * (MAX_SOURCE_IMAGE_BYTES + 1)

    with _client(_DummySupabase({object_path: payload}), "https://example.supabase.co") as client:
        resp = client.get("/api/v1/render/transparent.png", params={"src": source_url})

    assert resp.status_code == 413


def test_make_background_transparent_pixel_behavior():
    src = _png_bytes(
        [
            (255, 255, 255, 255),  # pure white -> fully transparent
            (200, 200, 200, 255),  # mid gray -> semi transparent
            (0, 0, 0, 255),        # dark -> unchanged alpha
        ],
        (3, 1),
    )

    out = make_background_transparent(src)
    img = Image.open(io.BytesIO(out)).convert("RGBA")
    p0, p1, p2 = list(img.getdata())

    assert p0[3] == 0
    assert 0 < p1[3] < 255
    assert p2[3] == 255
