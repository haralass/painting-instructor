"""
Lightweight full-pipeline integration test — runs in every CI build, not
just when someone explicitly asks for the slow/ML-heavy suite.

This exercises the real production path end to end: HTTP upload -> job
creation -> Celery task execution -> manifest -> hierarchical assets -> PDF
-> video -> asset existence on disk. It uses Celery's `task_always_eager`
so the task runs synchronously in-process (no broker required to dispatch
it, though the configured Redis backend is still used for state/results —
CI provides one as a service container).

The two network/model-download-dependent classic steps (line_art's
DexiNed/rembg, color_by_number's BiSeNet) are replaced with fast
deterministic stand-ins so this test has no external dependency and runs in
a few seconds. Everything hierarchical/lesson_plan/PDF/video-related is
real, unmocked code — that's the part this PR changed and needs coverage.

Run with:
    pytest tests/test_integration.py -v
"""
from __future__ import annotations
import io
import json
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.api.main import app, OUTPUTS_DIR
from backend.workers.tasks import celery_app


def _fake_line_art(img):
    """Stand-in for line_art.processor.process_with_mask — no DexiNed/rembg download."""
    return img.convert("L").convert("RGB"), np.ones((img.size[1], img.size[0]), dtype=np.uint8) * 255


def _fake_color_by_number(img, n_colors=12):
    """Stand-in for color_by_number.processor.process — no BiSeNet download."""
    return img.convert("RGB")


def _test_image(w: int = 120, h: int = 160) -> Image.Image:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[: h // 2] = [120, 170, 220]   # sky
    arr[h // 2 :] = [60, 130, 60]     # grass
    return Image.fromarray(arr)


@pytest.fixture(scope="module")
def eager_celery():
    """Run Celery tasks synchronously in-process for this test module only."""
    prev_eager = celery_app.conf.task_always_eager
    prev_propagates = celery_app.conf.task_eager_propagates
    prev_store_eager = celery_app.conf.task_store_eager_result
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    # GET /jobs/{job_id} looks the result up by id via AsyncResult against the
    # backend — under eager mode that lookup returns nothing unless the eager
    # result is also persisted to the backend.
    celery_app.conf.task_store_eager_result = True
    yield
    celery_app.conf.task_always_eager = prev_eager
    celery_app.conf.task_eager_propagates = prev_propagates
    celery_app.conf.task_store_eager_result = prev_store_eager


def _upload_and_wait(client: TestClient, medium: str = "oil") -> tuple[str, dict]:
    img = _test_image()
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    with patch("backend.pipeline.line_art.processor.process_with_mask", side_effect=_fake_line_art), \
         patch("backend.pipeline.color_by_number.processor.process", side_effect=_fake_color_by_number):
        res = client.post(
            "/jobs/",
            files=[("file", ("ref.jpg", buf, "image/jpeg"))],
            data={
                "medium": medium, "palette_size": "8", "initial_view_level": "3",
                "value_zones": "5", "region_complexity": "3",
                "texture_detail": "true", "background_detail": "false",
            },
        )
    assert res.status_code == 200, res.text
    job_id = res.json()["job_id"]

    # task_always_eager means the job is already finished by the time
    # apply_async returns above — this poll just fetches the final state.
    status_res = client.get(f"/jobs/{job_id}")
    body = status_res.json()
    assert body["status"] in ("completed", "completed_with_warnings"), body
    return job_id, body


@pytest.fixture(scope="module")
def oil_job(eager_celery):
    """One real upload+run, reused by every assertion test below — the
    pipeline is deterministic per input, so re-running it per assertion
    would just be wasted CI time."""
    client = TestClient(app)
    job_id, body = _upload_and_wait(client, medium="oil")
    manifest = json.loads((OUTPUTS_DIR / job_id / "manifest.json").read_text())
    return job_id, body, manifest


class TestFullPipelineIntegration:
    def test_upload_creates_completed_job(self, oil_job):
        _, body, _ = oil_job
        assert body["result"] is not None
        assert body["result"]["manifest"].endswith("manifest.json")
        assert body["result"]["pdf"], "job result missing pdf URL"
        assert body["result"]["video"], "job result missing video URL"

    def test_manifest_input_is_complete(self, oil_job):
        _, _, manifest = oil_job
        for key in ("medium", "palette_size", "initial_view_level", "value_zones",
                    "region_complexity", "texture_detail", "background_detail"):
            assert key in manifest["input"], f"manifest.input missing {key!r}"

    def test_hierarchical_assets_exist(self, oil_job):
        _, _, manifest = oil_job
        assert set(manifest["detail_levels"].keys()) == {"1", "2", "3", "4", "5"}
        for lvl, data in manifest["detail_levels"].items():
            for field in ("outlines", "values", "colours", "regions"):
                rel = data.get(field)
                assert rel, f"level {lvl} missing {field!r} path"
                assert (OUTPUTS_DIR / rel).exists(), f"level {lvl} {field} file missing: {rel}"

    def test_lesson_plan_assets_exist(self, oil_job):
        _, _, manifest = oil_job
        assert manifest["lesson_plan"], "lesson_plan is empty"
        for step in manifest["lesson_plan"]:
            assert step["assets"], f"lesson_plan step {step['name']!r} resolved no assets"
            for layer_key, rel in step["assets"].items():
                assert (OUTPUTS_DIR / rel).exists(), f"lesson_plan asset missing: {layer_key} -> {rel}"

    def test_pdf_and_video_outputs_exist(self, oil_job):
        _, _, manifest = oil_job

        assert manifest["pdf"]
        pdf_path = OUTPUTS_DIR / manifest["pdf"]
        assert pdf_path.exists() and pdf_path.stat().st_size > 0

        assert manifest["video"]
        video_path = OUTPUTS_DIR / manifest["video"]
        assert video_path.exists() and video_path.stat().st_size > 0

        assert manifest["video_chapters"], "video_chapters is empty"

    def test_all_referenced_classic_pages_exist(self, oil_job):
        _, _, manifest = oil_job
        for rel in manifest["pages"]:
            assert (OUTPUTS_DIR / rel).exists(), f"classic page missing: {rel}"

    @pytest.mark.parametrize("medium", ["oil", "watercolor", "acrylic", "pencil", "charcoal"])
    def test_every_medium_completes_with_pdf_and_video(self, eager_celery, medium):
        client = TestClient(app)
        job_id, _ = _upload_and_wait(client, medium=medium)
        manifest = json.loads((OUTPUTS_DIR / job_id / "manifest.json").read_text())
        assert manifest["input"]["medium"] == medium
        assert manifest["pdf"] and (OUTPUTS_DIR / manifest["pdf"]).exists()
        assert manifest["video"] and (OUTPUTS_DIR / manifest["video"]).exists()
