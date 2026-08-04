"""
Upload limits and per-IP rate limiting.

These guard the "three friends on one Mac" deployment: a bad upload must fail
with a sentence the person can act on, not a 500, and nobody should be able to
queue an unbounded amount of ML work.
"""
from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))
    from backend.api.main import app
    from backend.api import limits

    # Fresh counters per test — the limiters are process-global by design.
    limits.job_limiter._hits.clear()
    limits.critique_limiter._hits.clear()
    return TestClient(app)


def _jpeg(size=(64, 64)) -> io.BytesIO:
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 90, 60)).save(buf, format="JPEG")
    buf.seek(0)
    return buf


class TestUploadValidation:
    def test_rejects_non_image_content_type(self, client):
        r = client.post("/jobs/", files={"file": ("notes.txt", b"hello", "text/plain")})
        assert r.status_code == 415
        assert "unsupported image type" in r.json()["detail"].lower()

    def test_rejects_a_file_that_only_claims_to_be_an_image(self, client):
        """A renamed non-image must not reach the pipeline and 500 there."""
        r = client.post("/jobs/", files={"file": ("payload.jpg", b"MZ\x90\x00not an image", "image/jpeg")})
        assert r.status_code == 415
        assert "not a readable image" in r.json()["detail"]

    def test_rejects_empty_file(self, client):
        r = client.post("/jobs/", files={"file": ("empty.jpg", b"", "image/jpeg")})
        assert r.status_code == 400
        assert "empty" in r.json()["detail"].lower()

    def test_rejects_oversized_upload_with_a_clear_message(self, client, monkeypatch):
        from backend.api import limits
        monkeypatch.setattr(limits, "MAX_UPLOAD_BYTES", 64 * 1024)
        monkeypatch.setattr(limits, "MAX_UPLOAD_MB", 1)

        big = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * (200 * 1024))
        r = client.post("/jobs/", files={"file": ("huge.jpg", big, "image/jpeg")})
        assert r.status_code == 413
        detail = r.json()["detail"]
        assert "larger than" in detail and "MB" in detail

    def test_accepts_a_real_jpeg(self, client):
        r = client.post("/jobs/", files={"file": ("ref.jpg", _jpeg(), "image/jpeg")})
        assert r.status_code == 200, r.text
        assert r.json()["job_id"]

    def test_critique_upload_is_validated_too(self, client):
        r = client.post("/jobs/some-job/critique",
                        files={"file": ("notes.txt", b"hello", "text/plain")})
        assert r.status_code == 415


class TestRateLimiter:
    def test_allows_up_to_the_budget_then_429s(self):
        from backend.api.limits import RateLimiter

        rl = RateLimiter(max_events=3, window_sec=3600)
        for _ in range(3):
            rl.check("1.2.3.4")

        with pytest.raises(HTTPException) as exc:
            rl.check("1.2.3.4")
        assert exc.value.status_code == 429
        assert "Retry-After" in exc.value.headers

    def test_limits_are_per_client(self):
        from backend.api.limits import RateLimiter

        rl = RateLimiter(max_events=1, window_sec=3600)
        rl.check("1.1.1.1")
        rl.check("2.2.2.2")  # a different person is unaffected
        with pytest.raises(HTTPException):
            rl.check("1.1.1.1")

    def test_window_expiry_frees_the_budget(self, monkeypatch):
        from backend.api import limits

        clock = {"t": 1000.0}
        monkeypatch.setattr(limits.time, "monotonic", lambda: clock["t"])
        rl = limits.RateLimiter(max_events=1, window_sec=60)

        rl.check("1.1.1.1")
        with pytest.raises(HTTPException):
            rl.check("1.1.1.1")

        clock["t"] += 61
        rl.check("1.1.1.1")  # window has rolled over

    def test_rejected_uploads_do_not_cost_quota(self, client, monkeypatch):
        """A mistyped file must not burn a person's hourly budget."""
        from backend.api import limits
        monkeypatch.setattr(limits.job_limiter, "max_events", 2)

        for _ in range(5):
            assert client.post("/jobs/", files={"file": ("x.txt", b"nope", "text/plain")}).status_code == 415

        # Budget untouched: both real uploads still go through.
        assert client.post("/jobs/", files={"file": ("a.jpg", _jpeg(), "image/jpeg")}).status_code == 200
        assert client.post("/jobs/", files={"file": ("b.jpg", _jpeg(), "image/jpeg")}).status_code == 200
        assert client.post("/jobs/", files={"file": ("c.jpg", _jpeg(), "image/jpeg")}).status_code == 429

    def test_job_endpoint_enforces_the_limit(self, client, monkeypatch):
        from backend.api import limits
        monkeypatch.setattr(limits.job_limiter, "max_events", 2)

        assert client.post("/jobs/", files={"file": ("a.jpg", _jpeg(), "image/jpeg")}).status_code == 200
        assert client.post("/jobs/", files={"file": ("b.jpg", _jpeg(), "image/jpeg")}).status_code == 200

        r = client.post("/jobs/", files={"file": ("c.jpg", _jpeg(), "image/jpeg")})
        assert r.status_code == 429
        assert r.headers.get("Retry-After")


class TestClientIp:
    def test_prefers_cloudflare_header(self):
        from backend.api.limits import client_ip

        class _Req:
            headers = {"cf-connecting-ip": "9.9.9.9", "x-forwarded-for": "8.8.8.8"}
            client = type("C", (), {"host": "127.0.0.1"})()

        assert client_ip(_Req()) == "9.9.9.9"

    def test_falls_back_through_forwarded_for_then_peer(self):
        from backend.api.limits import client_ip

        class _Fwd:
            headers = {"x-forwarded-for": "8.8.8.8, 10.0.0.1"}
            client = type("C", (), {"host": "127.0.0.1"})()

        class _Direct:
            headers: dict[str, str] = {}
            client = type("C", (), {"host": "127.0.0.1"})()

        assert client_ip(_Fwd()) == "8.8.8.8"
        assert client_ip(_Direct()) == "127.0.0.1"
