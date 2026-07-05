"""Selective study overlay + art-book dot-to-dot — the 'teacher's eye' tools."""
import numpy as np
import pytest
from PIL import Image

from backend.analysis.renderer import render_study_overlay, render_smart_dot_to_dot

W, H = 400, 300


def _map_with_square(x0=100, y0=70, size=140) -> np.ndarray:
    """Label map: background region 0 + one square region 1."""
    lm = np.zeros((H, W), dtype=np.int32)
    lm[y0:y0 + size, x0:x0 + size] = 1
    return lm


class TestSmartDotToDot:
    def test_slivers_contribute_no_dots(self, tmp_path):
        lm = _map_with_square()
        # pepper the map with tiny sliver regions — the noise that used to
        # drown the page in useless dots
        rng = np.random.default_rng(1)
        for i in range(40):
            cx, cy = int(rng.uniform(10, W - 10)), int(rng.uniform(10, H - 10))
            lm[cy:cy + 3, cx:cx + 3] = 100 + i

        res = render_smart_dot_to_dot(lm, W, H, tmp_path / "dots.png")
        assert res is not None
        # dots may trace the background or the square — but never a sliver
        for x, y, _g in res["dots"]:
            on_border = x <= 6 or y <= 6 or x >= W - 7 or y >= H - 7
            on_square = (
                (abs(x - 100) < 10 or abs(x - 240) < 10) and 60 <= y <= 220
            ) or (
                (abs(y - 70) < 10 or abs(y - 210) < 10) and 90 <= x <= 250
            )
            assert on_border or on_square, f"dot ({x},{y}) sits on noise"

    def test_dots_are_sequential_along_the_loop(self, tmp_path):
        res = render_smart_dot_to_dot(_map_with_square(), W, H, tmp_path / "dots.png")
        groups = {}
        for x, y, g in res["dots"]:
            groups.setdefault(g, []).append((x, y))
        # A long STRAIGHT side (e.g. the full width of the background frame)
        # is legitimate; only a cross-image teleport would exceed ~0.85 diag.
        diag = float(np.hypot(W, H))
        for pts in groups.values():
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                assert np.hypot(x1 - x0, y1 - y0) < diag * 0.85, "random jump between consecutive dots"

    def test_square_is_simplified_to_few_dots(self, tmp_path):
        res = render_smart_dot_to_dot(_map_with_square(), W, H, tmp_path / "dots.png")
        # background frame + square = two simple shapes; corners, not confetti
        assert res["n_dots"] <= 24, f"{res['n_dots']} dots for two rectangles — not simplified"

    def test_max_dots_respected(self, tmp_path):
        lm = np.zeros((H, W), dtype=np.int32)
        tile = 0
        for ty in range(5):
            for tx in range(7):
                lm[ty * 60:(ty + 1) * 60, tx * 57:(tx + 1) * 57] = tile
                tile += 1
        res = render_smart_dot_to_dot(lm, W, H, tmp_path / "dots.png", max_dots=60)
        assert res["n_dots"] <= 60


class TestSelectiveStudyOverlay:
    def test_fine_tracing_only_where_detail_exists(self, tmp_path):
        # coarse: left | right halves. fine: left half is an 8x6 grid of tiles
        # (designed detail), right half stays one flat region.
        lm_coarse = np.zeros((H, W), dtype=np.int32)
        lm_coarse[:, W // 2:] = 1
        lm_fine = np.zeros((H, W), dtype=np.int32)
        tile = 0
        for ty in range(6):
            for tx in range(8):
                lm_fine[ty * 50:(ty + 1) * 50, tx * 25:(tx + 1) * 25] = tile
                tile += 1
        lm_fine[:, W // 2:] = 999   # right half: one region, no fine detail

        ref = np.full((H, W, 3), 90, dtype=np.uint8)
        out_path = tmp_path / "study.png"
        assert render_study_overlay(
            {"l2": lm_coarse, "l5": lm_fine}, ref, out_path
        ) is not None

        arr = np.array(Image.open(out_path).convert("L")).astype(int)
        bright = arr > 180   # the white tracing
        margin = 12          # keep clear of the coarse centre boundary
        left  = bright[:, : W // 2 - margin].mean()
        right = bright[:, W // 2 + margin:].mean()
        assert left > right * 5, f"fine tracing not selective: left={left:.4f} right={right:.4f}"
