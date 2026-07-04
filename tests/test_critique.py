"""Critique engine + endpoint tests — synthetic images, no ML, no network."""
import io
import json

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from backend.critique.engine import critique_attempt
from backend.api.main import app


W, H = 320, 240


def _reference() -> Image.Image:
    """Two-value composition: dark left half, light right half, mid band."""
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    arr[:, : W // 2] = [60, 50, 45]      # dark warm left
    arr[:, W // 2 :] = [200, 195, 185]   # light right
    arr[H // 3 : 2 * H // 3, :] = [130, 125, 120]  # mid band
    return Image.fromarray(arr)


def _attempt_too_light_left() -> Image.Image:
    """Same picture but the dark left half painted 2 bands too light."""
    arr = np.array(_reference())
    left = arr[:, : W // 2].astype(np.int16)
    arr[:, : W // 2] = np.clip(left + 90, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def _attempt_oversaturated() -> Image.Image:
    """Correct values but the right side pushed strongly toward red."""
    arr = np.array(_reference()).astype(np.int16)
    arr[:, W // 2 :, 0] = np.clip(arr[:, W // 2 :, 0] + 60, 0, 255)
    arr[:, W // 2 :, 2] = np.clip(arr[:, W // 2 :, 2] - 40, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


class TestCritiqueEngine:
    def test_identical_attempt_scores_high_no_feedback(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _reference().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        assert result["scores"]["overall"] >= 95
        assert result["feedback"] == []
        assert "track the reference" in result["first_fix"]

    def test_value_error_is_localised_to_left_side(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _attempt_too_light_left().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        value_items = [f for f in result["feedback"] if f["kind"] == "value"]
        assert value_items, "expected value feedback for a 2-band lightening"
        # every flagged value cell must be on the left half of the picture
        assert all(f["cx"] < 0.5 for f in value_items)
        assert all("too light" in f["message"] for f in value_items)
        assert result["scores"]["values"] < 90

    def test_value_feedback_ranks_before_colour(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _attempt_too_light_left().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        kinds = [f["kind"] for f in result["feedback"]]
        if "value" in kinds and any(k in kinds for k in ("temperature", "saturation")):
            assert kinds.index("value") < min(
                kinds.index(k) for k in ("temperature", "saturation") if k in kinds
            )

    def test_saturation_error_detected_on_right(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _attempt_oversaturated().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        colour_items = [f for f in result["feedback"] if f["kind"] in ("saturation", "temperature")]
        assert colour_items, "expected colour feedback for a strong red shift"
        assert all(f["cx"] > 0.5 for f in colour_items)

    def test_outputs_written(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _attempt_too_light_left().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        from pathlib import Path
        assert Path(result["assets"]["overlay"]).exists()
        assert Path(result["assets"]["side_by_side"]).exists()

    def test_attempt_resized_to_reference(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _reference().resize((W * 2, H * 2)).save(att)  # same picture, double size

        result = critique_attempt(ref, att, tmp_path / "out")
        assert result["scores"]["overall"] >= 90


class TestCritiqueEndpoint:
    @pytest.fixture
    def job_with_reference(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
        job_id = "job-critique-test"
        job_dir = tmp_path / job_id
        job_dir.mkdir()
        _reference().save(job_dir / "reference.png")
        (job_dir / "manifest.json").write_text(json.dumps({
            "input": {"medium": "oil", "value_zones": 5},
        }))
        return job_id

    def _upload(self, client, job_id, img: Image.Image):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return client.post(
            f"/jobs/{job_id}/critique",
            files={"file": ("attempt.png", buf, "image/png")},
        )

    def test_critique_roundtrip(self, job_with_reference):
        client = TestClient(app)
        res = self._upload(client, job_with_reference, _attempt_too_light_left())
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["attempt"] == 1
        assert body["scores"]["values"] < 90
        assert any(f["kind"] == "value" for f in body["feedback"])
        assert body["assets"]["overlay"].startswith(f"/outputs/{job_with_reference}/critique/attempt_1/")

    def test_second_attempt_gets_next_number(self, job_with_reference):
        client = TestClient(app)
        first = self._upload(client, job_with_reference, _attempt_too_light_left())
        second = self._upload(client, job_with_reference, _reference())
        assert first.json()["attempt"] == 1
        assert second.json()["attempt"] == 2
        # the corrected attempt must score better than the flawed one
        assert second.json()["scores"]["overall"] > first.json()["scores"]["overall"]

    def test_unknown_job_404(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
        client = TestClient(app)
        res = self._upload(client, "no-such-job", _reference())
        assert res.status_code == 404

    def test_bad_mime_rejected(self, job_with_reference):
        client = TestClient(app)
        res = client.post(
            f"/jobs/{job_with_reference}/critique",
            files={"file": ("attempt.txt", io.BytesIO(b"not an image"), "text/plain")},
        )
        assert res.status_code == 400
