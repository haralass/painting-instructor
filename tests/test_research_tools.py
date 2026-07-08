"""FDoG line art, vanishing-point detection, Kubelka-Munk mixing recipes."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from backend.pipeline.line_art.fdog import coherent_line_drawing
from backend.analysis.perspective import detect_vanishing_point
from backend.teaching.mixing import (
    mix_km, recipe_for, recipes_for_palette, list_brands, TUBES,
)
from backend.teaching import paint_brands


class TestFDoG:
    def test_draws_connected_ink_on_shapes(self):
        img = Image.new("L", (300, 240), 235)
        d = ImageDraw.Draw(img)
        d.ellipse([60, 40, 220, 190], fill=90)
        d.rectangle([120, 90, 180, 150], fill=180)
        out = coherent_line_drawing(np.array(img))
        ink = float((out < 128).mean())
        assert 0.005 < ink < 0.30, f"ink fraction {ink} not drawing-like"
        # the ellipse boundary must be inked: check a band around its top edge
        band = out[34:48, 100:180]
        assert (band < 128).any(), "shape contour not drawn"

    def test_flat_image_stays_blank(self):
        out = coherent_line_drawing(np.full((200, 200), 128, dtype=np.uint8))
        assert float((out < 128).mean()) < 0.01


class TestVanishingPoint:
    def test_converging_lines_found(self):
        # lines radiating from a known point (420, 150) drawn inside the frame
        img = Image.new("L", (640, 480), 255)
        d = ImageDraw.Draw(img)
        vp_true = (420, 150)
        for ang in np.linspace(-70, 70, 12):
            a = np.radians(ang + 200)
            x2 = vp_true[0] + 900 * np.cos(a)
            y2 = vp_true[1] + 900 * np.sin(a)
            d.line([vp_true, (x2, y2)], fill=0, width=3)
        vp = detect_vanishing_point(np.array(img))
        assert vp is not None, "convergence not detected"
        assert abs(vp["x"] - vp_true[0]) < 40 and abs(vp["y"] - vp_true[1]) < 40, vp

    def test_noise_yields_none(self):
        noise = np.random.default_rng(2).integers(0, 255, (300, 400), dtype=np.uint8)
        assert detect_vanishing_point(noise) is None

    def test_blank_yields_none(self):
        assert detect_vanishing_point(np.full((300, 400), 200, dtype=np.uint8)) is None


class TestKubelkaMunk:
    def test_white_black_mix_is_neutral_and_monotonic(self):
        # 1:1 white/black is genuinely DARK in real paint (black is a strong
        # tinter) — K-M models that. Assert neutrality + monotonic lightening
        # as white parts increase, not a naive RGB midpoint.
        m11 = mix_km([(245, 245, 240), (35, 33, 32)], [1, 1])
        m41 = mix_km([(245, 245, 240), (35, 33, 32)], [4, 1])
        m121 = mix_km([(245, 245, 240), (35, 33, 32)], [12, 1])
        for m in (m11, m41, m121):
            assert abs(m[0] - m[2]) < 25, f"not neutral: {m}"
        assert m11[0] < m41[0] < m121[0]
        assert m121[0] > 110, f"12:1 white:black should be a light grey, got {m121}"

    def test_blue_yellow_makes_green_not_grey(self):
        """The whole reason for K-M: paint blue+yellow is green; RGB says grey."""
        mixed = mix_km([(250, 205, 15), (25, 45, 130)], [1, 1])
        r, g, b = mixed
        assert g > r and g > b, f"expected green-dominant, got {mixed}"

    def test_pure_tube_recipe_is_itself(self):
        for name, rgb in TUBES[:4]:
            res = recipe_for(rgb)
            assert res["delta_e"] < 2.0
            assert len(res["recipe"]) == 1 and res["recipe"][0]["tube"] == name

    def test_common_targets_within_reach(self):
        for target in [(150, 120, 90), (90, 110, 140), (200, 170, 140), (60, 80, 60)]:
            res = recipe_for(target)
            assert res["delta_e"] < 14, f"{target}: ΔE {res['delta_e']} — palette can't reach it"
            assert 1 <= len(res["recipe"]) <= 3
            assert all(1 <= r["parts"] <= 24 for r in res["recipe"])

    def test_palette_enrichment_respects_medium(self):
        pal = [{"id": 0, "name": "x", "base_rgb": (150, 120, 90), "area_fraction": 0.5}]
        oil = recipes_for_palette(pal, "oil")
        assert "mixing" in oil[0] and "text" in oil[0]["mixing"]
        pencil = recipes_for_palette(pal, "pencil")
        assert "mixing" not in pencil[0]


class TestBrandRecipes:
    # One real brand reused across the heavier tests so its candidate mixtures
    # are built (and cached) only once.
    BRAND = "winsor_newton_oil"

    def test_list_brands_per_medium(self):
        all_brands = list_brands()
        assert len(all_brands) >= 6
        ids = {b["id"] for b in all_brands}
        assert self.BRAND in ids
        for b in all_brands:
            assert {"id", "name", "medium", "tube_count"} <= set(b)
            assert b["tube_count"] >= 12
        for medium in ("oil", "watercolor", "acrylic"):
            sub = list_brands(medium)
            assert len(sub) >= 2
            assert all(b["medium"] == medium for b in sub)
        # filtering actually narrows the set
        assert len(list_brands("oil")) < len(all_brands)

    def test_recipe_uses_only_that_brands_tubes(self):
        brand_tube_names = {name for name, _ in paint_brands.BRANDS[self.BRAND]["tubes"]}
        for target in [(150, 120, 90), (90, 110, 140), (200, 170, 140)]:
            res = recipe_for(target, brand_id=self.BRAND)
            assert res["reachable"] is True, f"{target}: {res}"
            used = {r["tube"] for r in res["recipe"]}
            assert used <= brand_tube_names, f"{used} not a subset of {self.BRAND}"

    def test_colour_outside_set_flagged_unreachable(self):
        # A fluorescent magenta no real tube masstone can reach.
        res = recipe_for((255, 0, 255), brand_id=self.BRAND)
        assert res["reachable"] is False
        assert res["delta_e"] > 14
        assert "note" in res and res["note"]

    def test_no_brand_path_unchanged(self):
        # Same recipe/text/ΔE as the historical default; new key is additive.
        for name, rgb in TUBES[:4]:
            res = recipe_for(rgb)
            assert res["recipe"][0]["tube"] == name and len(res["recipe"]) == 1
            assert res["delta_e"] < 2.0
            assert res["reachable"] is True
        earth = recipe_for((150, 120, 90))
        earth_explicit = recipe_for((150, 120, 90), brand_id=None)
        assert earth["text"] == earth_explicit["text"]
        assert earth["delta_e"] == earth_explicit["delta_e"]

    def test_unknown_brand_raises(self):
        with pytest.raises(KeyError):
            recipe_for((150, 120, 90), brand_id="no_such_brand")


class TestCritiqueAlignment:
    def test_skewed_attempt_is_aligned(self, tmp_path):
        import cv2
        from backend.critique.engine import critique_attempt
        # textured reference so ORB has features
        rng = np.random.default_rng(5)
        ref = rng.integers(40, 220, (240, 320, 3), dtype=np.uint8)
        ref = cv2.GaussianBlur(ref, (5, 5), 0)
        Image.fromarray(ref).save(tmp_path / "ref.png")

        # attempt = same image under a mild perspective warp
        H, W = ref.shape[:2]
        src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        dst = np.float32([[14, 8], [W - 6, 16], [W - 14, H - 10], [8, H - 4]])
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(ref, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
        Image.fromarray(warped).save(tmp_path / "att.png")

        res = critique_attempt(tmp_path / "ref.png", tmp_path / "att.png", tmp_path / "out")
        assert res["aligned"] is True
        assert res["scores"]["overall"] >= 85, res["scores"]
