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


def _attempt_value_compressed() -> Image.Image:
    """Same picture but every value pulled toward mid grey (flat range)."""
    arr = np.array(_reference()).astype(np.float64)
    mid = float(arr.mean())
    arr = mid + (arr - mid) * 0.4      # squash the value range to 40%
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _attempt_too_warm() -> Image.Image:
    """Correct values/structure but a global warm cast over the whole picture."""
    arr = np.array(_reference()).astype(np.int16)
    arr[..., 0] = np.clip(arr[..., 0] + 40, 0, 255)   # more red
    arr[..., 2] = np.clip(arr[..., 2] - 40, 0, 255)   # less blue
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

    # ── new signed metrics (additive) ────────────────────────────────────────
    def test_signed_metrics_present_and_neutral_when_identical(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _reference().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        # keys exist and cover every named metric
        from backend.critique.engine import METRIC_KEYS
        assert set(result["errors"]) == set(METRIC_KEYS)
        assert set(result["weights"]) == set(METRIC_KEYS)
        assert set(result["metric_scores"]) == set(METRIC_KEYS)
        assert "alignment_method" in result and "alignment_confidence" in result
        # an identical painting has ~zero signed error and near-perfect scores
        assert all(abs(v) < 0.05 for v in result["errors"].values())
        assert all(s >= 95 for s in result["metric_scores"].values())

    def test_value_compressed_attempt_flags_value_compression(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _attempt_value_compressed().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        # a squashed value range shows up as a strong positive compression error
        assert result["errors"]["value_compression"] > 0.3
        assert result["metric_scores"]["value_compression"] < 70

    def test_over_warm_attempt_flags_warm_temp_bias(self, tmp_path):
        ref = tmp_path / "ref.png"
        _reference().save(ref)
        att = tmp_path / "att.png"
        _attempt_too_warm().save(att)

        result = critique_attempt(ref, att, tmp_path / "out")
        # positive temp_bias == too warm (our sign convention)
        assert result["errors"]["temp_bias"] > 0.3


# ── prioritised progress critique (Phase 6) ──────────────────────────────────
#   These use a *structured* shared background (scattered light squares) so the
#   alignment step can confidently register the two frames — that lets the engine
#   trust the geometry and assert a structural correction. The subject is a solid
#   dark block whose bounds we vary (narrower, shifted, resized).
def _structured_bg() -> np.ndarray:
    rng = np.random.default_rng(3)
    bg = np.full((H, W, 3), 210, np.uint8)
    for _ in range(120):
        y = int(rng.integers(0, H - 10)); x = int(rng.integers(0, W - 10))
        bg[y:y + 8, x:x + 8] = int(rng.integers(150, 235))
    return bg


_BG = _structured_bg()


def _subject_reference() -> Image.Image:
    """Dark subject block (width 120, height 160) on a registrable background."""
    a = _BG.copy()
    a[40:200, 100:220] = [40, 40, 40]
    return Image.fromarray(a)


def _subject_narrowed() -> Image.Image:
    """Same subject drawn far too narrow (width 40 vs 120), same height."""
    a = _BG.copy()
    a[40:200, 140:180] = [40, 40, 40]
    return Image.fromarray(a)


def _subject_multi_error() -> Image.Image:
    """Narrow subject (structure) + lifted values (value) + warm cast (colour)."""
    a = _BG.copy().astype(np.int16)
    a[40:200, 140:180] = [110, 110, 110]        # narrower and too light
    a[..., 0] = np.clip(a[..., 0] + 35, 0, 255)  # warm cast
    a[..., 2] = np.clip(a[..., 2] - 35, 0, 255)
    return Image.fromarray(a.astype(np.uint8))


class TestPrioritisedCritique:
    def _run(self, tmp_path, ref_img, att_img):
        ref = tmp_path / "ref.png"; ref_img.save(ref)
        att = tmp_path / "att.png"; att_img.save(att)
        return critique_attempt(ref, att, tmp_path / "out")

    def test_priority_and_secondary_present_and_first_fix_matches(self, tmp_path):
        result = self._run(tmp_path, _reference(), _reference())
        assert "priority" in result and "secondary" in result
        assert set(result["priority"]) >= {"component", "severity", "message"}
        assert isinstance(result["secondary"], list)
        # first_fix is the single prioritised correction's message
        assert result["first_fix"] == result["priority"]["message"]

    def test_narrowed_subject_yields_structural_priority(self, tmp_path):
        result = self._run(tmp_path, _subject_reference(), _subject_narrowed())
        # the frames registered well enough to trust the geometry
        assert result["alignment_confidence"] >= 0.35
        assert result["priority"]["component"] in ("placement", "proportion")

    def test_priority_orders_structure_then_value_then_colour(self, tmp_path):
        result = self._run(tmp_path, _subject_reference(), _subject_multi_error())
        assert result["alignment_confidence"] >= 0.35
        ordered = [result["priority"], *result["secondary"]]
        comps = [c["component"] for c in ordered]
        # a structural correction is prioritised first
        assert comps[0] in ("placement", "proportion")
        # and value is ranked ahead of colour when both are present
        assert "value" in comps and "colour" in comps
        assert comps.index("value") < comps.index("colour")
        # structural corrections precede value/colour ones
        struct_idx = [i for i, c in enumerate(comps) if c in ("placement", "proportion")]
        other_idx = [i for i, c in enumerate(comps) if c in ("value", "colour", "edges")]
        assert max(struct_idx) < min(other_idx)

    def test_low_alignment_downgrades_to_value_or_colour(self, tmp_path):
        # flat regions + a global warm cast: nothing to register on, so the
        # alignment falls back to resize (confidence 0) and structure is unsafe.
        result = self._run(tmp_path, _reference(), _attempt_too_warm())
        assert result["alignment_confidence"] < 0.35
        assert result["priority"]["component"] in ("value", "colour", "edges")
        # and we say plainly that structure couldn't be checked this time
        assert result["priority"].get("structure_checked") is False
        assert "placement or proportion" in result["priority"]["message"]


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
