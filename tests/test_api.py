"""
API contract tests.

Run with:
    pytest tests/test_api.py -v
Requires:
    pip install -r requirements.txt -r requirements-dev.txt
No Redis / Celery needed — the API is tested with a mocked Celery task.
"""
from __future__ import annotations
import io
import uuid
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _jpeg_bytes(w: int = 100, h: int = 100, colour=(200, 100, 50)) -> bytes:
    img = Image.new("RGB", (w, h), colour)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_upload(data: bytes = None, filename: str = "test.jpg", content_type: str = "image/jpeg"):
    if data is None:
        data = _jpeg_bytes()
    return ("file", (filename, io.BytesIO(data), content_type))


def _fake_apply_async(*args, **kwargs):
    mock = MagicMock()
    mock.id = kwargs.get("task_id") or str(uuid.uuid4())
    return mock


# ── POST /jobs/ ───────────────────────────────────────────────────────────────
class TestCreateJob:
    def test_valid_upload_returns_job_id(self):
        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "oil", "palette_size": "12",
                                    "detail_level": "3", "value_zones": "5"})
        assert res.status_code == 200
        body = res.json()
        assert "job_id" in body
        assert isinstance(body["job_id"], str)
        assert len(body["job_id"]) == 36   # UUID

    def test_invalid_mime_type_rejected(self):
        res = client.post(
            "/jobs/",
            files=[_make_upload(b"not-an-image", "file.pdf", "application/pdf")],
            data={"medium": "oil"},
        )
        assert res.status_code == 400
        assert "Unsupported image type" in res.json()["detail"]

    def test_invalid_medium_rejected(self):
        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "gouache", "palette_size": "12"})
        assert res.status_code == 422
        assert "medium" in res.json()["detail"].lower()

    def test_palette_size_too_small_rejected(self):
        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "oil", "palette_size": "2"})
        assert res.status_code == 422
        assert "palette_size" in res.json()["detail"].lower()

    def test_palette_size_too_large_rejected(self):
        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "oil", "palette_size": "100"})
        assert res.status_code == 422

    def test_invalid_detail_level_rejected(self):
        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "oil", "palette_size": "12", "detail_level": "9"})
        assert res.status_code == 422

    def test_invalid_value_zones_rejected(self):
        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "oil", "palette_size": "12",
                                    "value_zones": "4"})
        assert res.status_code == 422

    def test_n_colors_backward_compat(self):
        """n_colors alias should still work and map to palette_size."""
        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "oil", "n_colors": "16"})
        assert res.status_code == 200
        assert "job_id" in res.json()

    def test_job_id_used_as_celery_task_id(self):
        """The Celery task must be started with task_id=job_id."""
        captured = {}
        def _capture(*args, **kwargs):
            captured["task_id"] = kwargs.get("task_id")
            m = MagicMock(); m.id = kwargs["task_id"]; return m

        with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_capture):
            res = client.post("/jobs/", files=[_make_upload()],
                              data={"medium": "oil", "palette_size": "12"})
        assert res.status_code == 200
        job_id = res.json()["job_id"]
        assert captured["task_id"] == job_id, "Celery task_id must equal job_id"

    def test_all_valid_mediums_accepted(self):
        for medium in ("oil", "watercolor", "acrylic", "pencil", "charcoal"):
            with patch("backend.workers.tasks.run_pipeline.apply_async", side_effect=_fake_apply_async):
                res = client.post("/jobs/", files=[_make_upload()],
                                  data={"medium": medium, "palette_size": "12"})
            assert res.status_code == 200, f"medium={medium} should be accepted"


# ── GET /jobs/{job_id} ────────────────────────────────────────────────────────
class TestGetJob:
    def test_queued_status_shape(self):
        with patch("celery.result.AsyncResult") as MockResult:
            instance = MockResult.return_value
            instance.state = "PENDING"
            res = client.get(f"/jobs/{uuid.uuid4()}")
        body = res.json()
        assert body["status"] == "queued"
        assert "progress" in body
        assert "step"     in body
        assert "message"  in body
        assert body.get("error") is None

    def test_processing_status_has_progress(self):
        with patch("celery.result.AsyncResult") as MockResult:
            instance = MockResult.return_value
            instance.state = "PROGRESS"
            instance.info  = {"step": "notan", "progress": 30, "message": "Mapping values"}
            res = client.get(f"/jobs/{uuid.uuid4()}")
        body = res.json()
        assert body["status"] == "processing"
        assert body["progress"] == 30
        assert body["step"]     == "notan"

    def test_completed_status_has_result(self):
        jid = str(uuid.uuid4())
        with patch("celery.result.AsyncResult") as MockResult:
            instance = MockResult.return_value
            instance.state  = "SUCCESS"
            instance.result = {
                "pages": [f"outputs/{jid}/line_art.png"],
                "video": f"outputs/{jid}/tutorial.mp4",
                "pdf":   f"outputs/{jid}/tutorial_book.pdf",
            }
            res = client.get(f"/jobs/{jid}")
        body = res.json()
        assert body["status"]   == "completed"
        assert body["progress"] == 100
        assert body["result"]   is not None
        assert "manifest" in body["result"]
        assert "pages"    in body["result"]

    def test_failed_status_has_error(self):
        with patch("celery.result.AsyncResult") as MockResult:
            instance = MockResult.return_value
            instance.state  = "FAILURE"
            instance.result = RuntimeError("out of memory")
            res = client.get(f"/jobs/{uuid.uuid4()}")
        body = res.json()
        assert body["status"] == "failed"
        assert body["error"]  is not None

    def test_status_always_lowercase(self):
        """All returned statuses must be in the canonical lowercase set."""
        valid = {"queued", "processing", "completed", "failed"}
        for celery_state in ("PENDING", "STARTED", "PROGRESS", "SUCCESS", "FAILURE"):
            with patch("celery.result.AsyncResult") as MockResult:
                instance = MockResult.return_value
                instance.state  = celery_state
                instance.info   = {"step": "test", "progress": 50, "message": "ok"}
                instance.result = {} if celery_state in ("SUCCESS", "FAILURE") else None
                res = client.get(f"/jobs/{uuid.uuid4()}")
            body = res.json()
            assert body["status"] in valid, f"state={celery_state} produced invalid status={body['status']!r}"


class TestMediumsEndpoint:
    def test_list_mediums_returns_all_five(self):
        res = client.get("/mediums/")
        assert res.status_code == 200
        data = res.json()
        for m in ("oil", "watercolor", "acrylic", "pencil", "charcoal"):
            assert m in data, f"medium {m!r} missing from /mediums/ response"

    def test_list_mediums_has_recommended_settings(self):
        res = client.get("/mediums/")
        data = res.json()
        oil = data["oil"]
        assert "recommended_value_zones"  in oil
        assert "recommended_palette_size" in oil

    def test_get_medium_returns_stages(self):
        for medium in ("oil", "watercolor", "acrylic", "pencil", "charcoal"):
            res = client.get(f"/mediums/{medium}")
            assert res.status_code == 200, f"{medium} endpoint failed"
            data = res.json()
            assert "stages"       in data
            assert "instructions" in data
            assert len(data["stages"]) > 0

    def test_get_unknown_medium_returns_404(self):
        res = client.get("/mediums/gouache")
        assert res.status_code == 404
