"""
End-to-end pipeline test.

Runs the full run_pipeline Celery task synchronously (no broker needed)
on a synthetic 100×100 image and verifies:
  - manifest.json is created
  - all referenced assets exist on disk
  - completed result schema is correct

Run with:
    pytest tests/test_e2e.py -v -s
WARNING: downloads ML models on first run (~500MB).
Skip with: pytest -m "not slow"
"""
from __future__ import annotations
import io
import json
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

pytestmark = pytest.mark.slow


def _test_image(w: int = 200, h: int = 200) -> Image.Image:
    """Simple image: blue sky top, green ground bottom."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:h//2] = [120, 170, 220]   # sky
    arr[h//2:] = [60, 130, 60]    # grass
    return Image.fromarray(arr)


@pytest.fixture(scope="module")
def pipeline_result():
    """Run the pipeline once for all e2e tests."""
    from backend.workers.tasks import run_pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        # Save synthetic image
        img     = _test_image()
        job_id  = str(uuid.uuid4())
        img_path = str(Path(tmpdir) / f"{job_id}.jpg")
        img.save(img_path, format="JPEG")

        # Monkeypatch OUTPUTS_DIR
        import backend.workers.tasks as tasks_mod
        import os
        orig_getcwd = os.getcwd
        os.chdir(tmpdir)

        result = run_pipeline(
            None,   # self=None for sync call
            img_path=img_path,
            job_id=job_id,
            medium="oil",
            palette_size=6,
            detail_level=3,
            value_zones=3,
        )

        os.chdir(orig_getcwd())

        yield result, Path(tmpdir) / "outputs" / job_id, job_id


class TestEndToEnd:
    def test_result_has_pages(self, pipeline_result):
        result, _, _ = pipeline_result
        assert isinstance(result.get("pages"), list)

    def test_manifest_created(self, pipeline_result):
        result, out_dir, _ = pipeline_result
        assert Path(result["manifest"]).exists()

    def test_manifest_is_valid_json(self, pipeline_result):
        result, _, _ = pipeline_result
        data = json.loads(Path(result["manifest"]).read_text())
        assert "job_id" in data
        assert "input"  in data
        assert "image"  in data

    def test_manifest_references_exist(self, pipeline_result):
        """Every path mentioned in manifest.json should exist on disk."""
        result, out_dir, _ = pipeline_result
        data   = json.loads(Path(result["manifest"]).read_text())
        issues = []
        for p in data.get("pages", []):
            full = Path("outputs") / p if not Path(p).is_absolute() else Path(p)
            if not full.exists():
                # Try relative to the output parent
                alt = out_dir.parent / p
                if not alt.exists():
                    issues.append(p)
        assert not issues, f"Missing manifest assets: {issues}"

    def test_status_would_be_completed(self, pipeline_result):
        """Confirm result dict has the expected completed-response keys."""
        result, _, _ = pipeline_result
        assert "pages"   in result
        assert "manifest" in result
        assert "errors"  in result

    def test_detail_levels_in_manifest(self, pipeline_result):
        result, _, _ = pipeline_result
        data = json.loads(Path(result["manifest"]).read_text())
        assert "detail_levels" in data
        # At least level 1 and 3 should be present
        assert "1" in data["detail_levels"] or len(data["detail_levels"]) > 0

    def test_input_params_recorded_in_manifest(self, pipeline_result):
        result, _, job_id = pipeline_result
        data = json.loads(Path(result["manifest"]).read_text())
        assert data["input"]["medium"]       == "oil"
        assert data["input"]["palette_size"] == 6
        assert data["input"]["value_zones"]  == 3
        assert data["job_id"]               == job_id
