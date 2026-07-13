"""Local ("Analyse this area") rectangle-selection analysis.

Verifies the house rule this feature exists to enforce: a local study is
always cut from the ORIGINAL, full-resolution reference file — never from a
resized preview or any generated/overlay asset — plus the bbox
clamping/rejection and the offset/scale contract that lets a caller map a
local-analysis pixel back onto the parent image.
"""
from __future__ import annotations

import json
import uuid

import numpy as np
import pytest
from PIL import Image

from backend.analysis.local import (
    MIN_CROP_SIDE,
    LocalAnalysisError,
    run_local_analysis,
)


def _reference_image(w: int = 640, h: int = 480) -> Image.Image:
    """A synthetic reference with distinct quadrants so a crop is visibly
    "the right piece" rather than an arbitrary region."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[: h // 2, : w // 2] = [200, 60, 60]     # top-left: red
    arr[: h // 2, w // 2 :] = [60, 200, 60]     # top-right: green
    arr[h // 2 :, : w // 2] = [60, 60, 200]     # bottom-left: blue
    arr[h // 2 :, w // 2 :] = [200, 200, 60]    # bottom-right: yellow
    return Image.fromarray(arr)


@pytest.fixture()
def job(tmp_path, monkeypatch):
    """A minimal job directory: full-res reference.jpg + a manifest.json
    recording input settings, nothing else. run_local_analysis only needs
    these two things to do its job."""
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))
    from backend.utils.paths import job_dir

    job_id = str(uuid.uuid4())
    out = job_dir(job_id)
    out.mkdir(parents=True)

    ref = _reference_image()
    ref_path = out / "reference.jpg"
    ref.save(ref_path, format="JPEG", quality=95)

    # A much smaller "preview" placed at a level_*-style name, so a bug that
    # accidentally reads *some* image out of the job dir instead of the true
    # reference would be caught by the resolution assertions below.
    preview = ref.resize((64, 48))
    preview.save(out / "level_1_colours.png")

    (out / "manifest.json").write_text(json.dumps({
        "job_id": job_id,
        "input": {"medium": "oil", "palette_size": 8, "value_zones": 5, "region_complexity": 2},
    }))

    return job_id, out, ref.size


class TestCropsFromOriginal:
    def test_crop_dimensions_match_bbox_not_preview(self, job):
        job_id, out, (W, H) = job
        bbox = {"x": 50, "y": 40, "w": 200, "h": 150}
        result = run_local_analysis(job_id, bbox)

        # The true crop rect is preserved verbatim in the response bbox —
        # dimensions come straight from the ORIGINAL-resolution request, not
        # from the 64x48 preview sitting in the same job dir.
        assert result["bbox"] == {"x": 50, "y": 40, "w": 200, "h": 150}
        assert result["offset"] == {"x": 50, "y": 40}

    def test_working_crop_is_derived_from_full_res_pixels(self, job):
        """A crop pulled from the full-res reference must reproduce the
        source quadrant colours; pulling from the 64x48 preview instead would
        blur/average them past recognition at this crop size."""
        job_id, out, (W, H) = job
        # A crop entirely inside the top-left (red) quadrant.
        bbox = {"x": 10, "y": 10, "w": 100, "h": 100}
        result = run_local_analysis(job_id, bbox)

        # assets are outputs-relative; resolve against the real outputs root
        from backend.utils.paths import outputs_root
        full_path = outputs_root() / result["assets"]["colours"]
        arr = np.array(Image.open(full_path).convert("RGB"))
        mean_rgb = arr.reshape(-1, 3).mean(axis=0)
        # Dominant channel should be red (matches the source quadrant), not a
        # blend with the neighbouring quadrants a lower-res source would leak.
        assert mean_rgb[0] > mean_rgb[1] + 20
        assert mean_rgb[0] > mean_rgb[2] + 20


class TestClamping:
    def test_bbox_clamps_to_image_bounds(self, job):
        job_id, out, (W, H) = job
        # Selection hangs far off the right/bottom edge of the image.
        bbox = {"x": W - 100, "y": H - 100, "w": 500, "h": 500}
        result = run_local_analysis(job_id, bbox)
        b = result["bbox"]
        assert b["x"] + b["w"] <= W
        assert b["y"] + b["h"] <= H
        assert b["x"] == W - 100 and b["y"] == H - 100

    def test_negative_origin_clamps_to_zero(self, job):
        job_id, out, (W, H) = job
        bbox = {"x": -50, "y": -30, "w": 150, "h": 150}
        result = run_local_analysis(job_id, bbox)
        b = result["bbox"]
        assert b["x"] == 0 and b["y"] == 0
        # w/h shrink to account for the clamped origin (selection extent was
        # x:[-50,100) -> clamps to [0,100))
        assert b["w"] == 100 and b["h"] == 120

    def test_inverted_rect_is_normalised(self, job):
        """A drag that ends up top-left of its start (negative w/h) is still
        a valid rectangle — same convention as bboxToCropRect on the frontend."""
        job_id, out, (W, H) = job
        bbox = {"x": 200, "y": 200, "w": -100, "h": -100}
        result = run_local_analysis(job_id, bbox)
        b = result["bbox"]
        assert b["x"] == 100 and b["y"] == 100
        assert b["w"] == 100 and b["h"] == 100


class TestRejection:
    def test_tiny_bbox_is_rejected(self, job):
        job_id, out, (W, H) = job
        bbox = {"x": 10, "y": 10, "w": MIN_CROP_SIDE - 1, "h": MIN_CROP_SIDE - 1}
        with pytest.raises(LocalAnalysisError):
            run_local_analysis(job_id, bbox)

    def test_degenerate_zero_size_bbox_is_rejected(self, job):
        job_id, out, (W, H) = job
        with pytest.raises(LocalAnalysisError):
            run_local_analysis(job_id, {"x": 10, "y": 10, "w": 0, "h": 0})

    def test_selection_entirely_outside_image_is_rejected(self, job):
        job_id, out, (W, H) = job
        bbox = {"x": W + 100, "y": H + 100, "w": 200, "h": 200}
        with pytest.raises(LocalAnalysisError):
            run_local_analysis(job_id, bbox)

    def test_missing_reference_raises_file_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))
        from backend.utils.paths import job_dir
        job_id = str(uuid.uuid4())
        job_dir(job_id).mkdir(parents=True)
        with pytest.raises(FileNotFoundError):
            run_local_analysis(job_id, {"x": 0, "y": 0, "w": 100, "h": 100})

    def test_non_numeric_bbox_is_rejected(self, job):
        job_id, out, (W, H) = job
        with pytest.raises(LocalAnalysisError):
            run_local_analysis(job_id, {"x": "nope", "y": 0, "w": 100, "h": 100})


class TestOffsetScaleMapping:
    def test_offset_and_scale_map_local_point_back_to_parent(self, job):
        job_id, out, (W, H) = job
        bbox = {"x": 120, "y": 80, "w": 220, "h": 180}
        result = run_local_analysis(job_id, bbox)

        offset = result["offset"]
        scale = result["scale"]
        working = result["working_size"]

        # The crop's working size must match bbox * scale (rounding-safe).
        assert working["width"] == pytest.approx(bbox["w"] * scale, abs=1)
        assert working["height"] == pytest.approx(bbox["h"] * scale, abs=1)

        # A point at the far corner of the working (local) image maps back
        # to the far corner of the ORIGINAL selection rectangle.
        local_x, local_y = working["width"], working["height"]
        parent_x = offset["x"] + local_x / scale
        parent_y = offset["y"] + local_y / scale
        assert parent_x == pytest.approx(bbox["x"] + bbox["w"], abs=1)
        assert parent_y == pytest.approx(bbox["y"] + bbox["h"], abs=1)

        # And the local origin maps back to the selection's top-left corner.
        assert offset["x"] + 0 / scale == bbox["x"]
        assert offset["y"] + 0 / scale == bbox["y"]

    def test_small_crop_is_not_downscaled(self, job):
        """A crop under MAX_WORKING_SIDE should pass through at scale 1.0 —
        no pointless resampling for the common case of a modest selection."""
        job_id, out, (W, H) = job
        bbox = {"x": 50, "y": 50, "w": 200, "h": 150}
        result = run_local_analysis(job_id, bbox)
        assert result["scale"] == pytest.approx(1.0)
        assert result["working_size"] == {"width": 200, "height": 150}


class TestResponseShape:
    def test_assets_are_outputs_relative_and_exist(self, job):
        job_id, out, (W, H) = job
        result = run_local_analysis(job_id, {"x": 30, "y": 30, "w": 180, "h": 180})

        from backend.utils.paths import outputs_root
        root = outputs_root()
        for key in ("outlines", "regions", "values", "colours", "label_map", "regions_json"):
            rel = result["assets"][key]
            assert rel is not None, key
            assert not rel.startswith("/"), f"{key} should be outputs-relative, got {rel!r}"
            assert (root / rel).exists(), f"{key} asset missing on disk: {rel}"
            # Every asset lives under this selection's own local/ directory —
            # never overwrites/reuses the parent job's whole-image assets.
            assert f"{job_id}/local/{result['selection_id']}/" in rel

    def test_selection_id_is_present_and_short(self, job):
        job_id, out, (W, H) = job
        result = run_local_analysis(job_id, {"x": 30, "y": 30, "w": 180, "h": 180})
        assert result["selection_id"]
        assert len(result["selection_id"]) <= 16

    def test_repeated_calls_get_distinct_selection_ids_and_dirs(self, job):
        job_id, out, (W, H) = job
        bbox = {"x": 30, "y": 30, "w": 180, "h": 180}
        r1 = run_local_analysis(job_id, bbox)
        r2 = run_local_analysis(job_id, bbox)
        assert r1["selection_id"] != r2["selection_id"]
        assert (out / "local" / r1["selection_id"]).is_dir()
        assert (out / "local" / r2["selection_id"]).is_dir()


class TestAPIEndpoint:
    """Thin smoke test for the FastAPI wiring (POST /jobs/{job_id}/local-analysis)."""

    def test_endpoint_returns_local_analysis(self, job):
        job_id, out, (W, H) = job
        from fastapi.testclient import TestClient
        from backend.api.main import app

        client = TestClient(app)
        resp = client.post(f"/jobs/{job_id}/local-analysis",
                            json={"x": 40, "y": 40, "w": 200, "h": 160})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["bbox"] == {"x": 40, "y": 40, "w": 200, "h": 160}
        assert "assets" in data and "outlines" in data["assets"]

    def test_endpoint_404s_when_no_reference(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path / "outputs"))
        from backend.utils.paths import job_dir
        job_id = str(uuid.uuid4())
        job_dir(job_id).mkdir(parents=True)

        from fastapi.testclient import TestClient
        from backend.api.main import app
        client = TestClient(app)
        resp = client.post(f"/jobs/{job_id}/local-analysis",
                            json={"x": 0, "y": 0, "w": 100, "h": 100})
        assert resp.status_code == 404

    def test_endpoint_422s_on_tiny_bbox(self, job):
        job_id, out, (W, H) = job
        from fastapi.testclient import TestClient
        from backend.api.main import app
        client = TestClient(app)
        resp = client.post(f"/jobs/{job_id}/local-analysis",
                            json={"x": 0, "y": 0, "w": 2, "h": 2})
        assert resp.status_code == 422
