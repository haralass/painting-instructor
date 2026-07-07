"""No-ML fallback behaviour: classical line art and honest light detection."""
import numpy as np
import pytest
from PIL import Image
from unittest.mock import patch


def _gradient_top_lit(w=200, h=160) -> Image.Image:
    """Smooth vertical gradient, bright at the top — light clearly from above."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        arr[y] = int(235 - 180 * y / h)
    return Image.fromarray(arr)


class TestClassicalLineArt:
    def test_fallback_produces_sketch_when_ml_missing(self):
        from backend.pipeline.line_art import processor
        from PIL import ImageDraw
        img = _gradient_top_lit()
        d = ImageDraw.Draw(img)
        d.ellipse([40, 40, 120, 120], fill=(50, 40, 35))     # something to draw
        d.rectangle([140, 90, 185, 150], fill=(200, 190, 60))
        with patch.object(processor, "_get_detector", side_effect=ImportError("no torch")):
            out, fg_mask = processor.process_with_mask(img)
        assert out.size == img.size
        arr = np.array(out.convert("L"))
        dark = float((arr < 128).mean())
        # A sketch has SOME ink but is mostly paper
        assert 0.0005 < dark < 0.5, f"dark fraction {dark} not sketch-like"

    def test_fallback_draws_the_structure(self):
        """A hard two-tone boundary must appear as a drawn line."""
        from backend.pipeline.line_art import processor
        arr = np.full((160, 200, 3), 230, dtype=np.uint8)
        arr[80:] = 60
        img = Image.fromarray(arr)
        with patch.object(processor, "_get_detector", side_effect=ImportError("no torch")):
            out, _ = processor.process_with_mask(img)
        band = np.array(out.convert("L"))[70:90, :]
        assert (band < 128).any(), "the boundary line is missing from the sketch"


class TestLightDirectionHonesty:
    def test_directional_light_reports_angle(self):
        from backend.pipeline.artist_breakdown.processor import light_direction_with_angle
        _, angle = light_direction_with_angle(_gradient_top_lit())
        assert angle is not None
        # bright top → gradient points up → angle around 90°
        assert 30 <= angle <= 150, f"expected ~90° (from above), got {angle}"

    def test_diffuse_light_reports_none(self):
        from backend.pipeline.artist_breakdown.processor import light_direction_with_angle
        noise = Image.fromarray(
            np.random.default_rng(7).integers(0, 255, (160, 200, 3), dtype=np.uint8)
        )
        _, angle = light_direction_with_angle(noise)
        assert angle is None, f"random noise has no light direction, got {angle}"


class TestPlannerDiffuseLight:
    def test_overview_teaches_diffuse_light(self):
        from backend.teaching.planner import build_image_brief
        brief = build_image_brief([], [], [], light_angle=None, img_w=100, img_h=100)
        assert "diffuse" in brief["overview"].lower()
