"""
Image analysis unit tests with deterministic synthetic images.

All tests use generated images — no external files needed.

Run with:
    pytest tests/test_analysis.py -v
"""
from __future__ import annotations
import numpy as np
import pytest
from PIL import Image
from skimage import color as skcolor

# ── Synthetic image factories ────────────────────────────────────────────────

def _flat_colour_image(colours: list[tuple[int,int,int]], w: int = 300, h: int = 100) -> Image.Image:
    """Horizontal bands, each a flat colour."""
    band_w = w // len(colours)
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    for i, c in enumerate(colours):
        arr[:, i*band_w:(i+1)*band_w] = c
    return Image.fromarray(arr)


def _gradient_brightness(w: int = 200, h: int = 200) -> Image.Image:
    """Left=dark, right=bright gradient."""
    x = np.linspace(0, 255, w, dtype=np.uint8)
    arr = np.tile(x, (h, 1))
    return Image.fromarray(np.stack([arr]*3, axis=-1))


def _warm_cool_neutral(w: int = 300, h: int = 100) -> Image.Image:
    """Orange (warm) | Blue (cool) | Grey (neutral)."""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[:, :w//3]      = [230, 130,  30]   # orange/warm
    arr[:, w//3:2*w//3] = [ 30,  80, 220]  # blue/cool
    arr[:, 2*w//3:]    = [128, 128, 128]   # neutral grey
    return Image.fromarray(arr)


def _two_region_same_colour(w: int = 200, h: int = 200) -> Image.Image:
    """Same red colour appears top-left and bottom-right (separated by white)."""
    arr = np.full((h, w, 3), 255, dtype=np.uint8)
    arr[:h//3, :w//3]               = [200, 50, 50]   # top-left red
    arr[2*h//3:, 2*w//3:]           = [200, 50, 50]   # bottom-right red
    return Image.fromarray(arr)


def _contour_with_texture(w: int = 200, h: int = 200) -> Image.Image:
    """Large black circle (contour) on white with fine noise texture."""
    arr = np.full((h, w, 3), 250, dtype=np.uint8)
    # Fine noise
    rng  = np.random.default_rng(0)
    noise = rng.integers(-8, 8, (h, w, 3), dtype=np.int8)
    arr  = np.clip(arr.astype(int) + noise, 0, 255).astype(np.uint8)
    # Large circle boundary
    cy, cx, r = h//2, w//2, min(h,w)//3
    for y in range(h):
        for x in range(w):
            d = ((y-cy)**2 + (x-cx)**2)**0.5
            if abs(d - r) < 3:
                arr[y, x] = [20, 20, 20]
    return Image.fromarray(arr)


# ── Value zone tests ──────────────────────────────────────────────────────────

class TestValueZones:
    def _zones(self, img, n):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.values import compute_value_zones
        cache = prepare(img)
        zone_map, zones = compute_value_zones(cache, n)
        return zone_map, zones

    def test_three_zones_produced(self):
        img = _gradient_brightness()
        _, zones = self._zones(img, 3)
        assert len(zones) == 3

    def test_five_zones_produced(self):
        img = _gradient_brightness()
        _, zones = self._zones(img, 5)
        assert len(zones) == 5

    def test_seven_zones_produced(self):
        img = _gradient_brightness()
        _, zones = self._zones(img, 7)
        assert len(zones) == 7

    def test_zones_sorted_dark_to_light(self):
        img = _gradient_brightness()
        _, zones = self._zones(img, 5)
        grey_values = [z.grey_value for z in zones]
        assert grey_values == sorted(grey_values), "Zones must progress shadow→highlight"

    def test_three_zones_cover_full_range(self):
        """Dark, midtone, and light zones should each cover some pixels."""
        img = _gradient_brightness()
        zone_map, zones = self._zones(img, 3)
        for z in zones:
            count = (zone_map == z.id).sum()
            assert count > 0, f"Zone {z.label!r} has zero pixels"

    def test_value_zones_are_dark_midtone_light(self):
        """3-zone: darkest zone grey < 100, lightest > 180."""
        img = _gradient_brightness()
        _, zones = self._zones(img, 3)
        assert zones[0].grey_value < 100, "First zone should be dark"
        assert zones[-1].grey_value > 180, "Last zone should be light"


# ── Colour temperature tests (LAB channel correctness) ───────────────────────

class TestColourTemperature:
    def _classify(self, rgb_pixel: tuple[int,int,int]) -> str:
        """Returns warm/cool/neutral for a single pixel colour."""
        arr = np.array([[list(rgb_pixel)]], dtype=np.float32) / 255.0
        lab = skcolor.rgb2lab(arr)
        b_star  = float(lab[0, 0, 2])   # b* — blue/yellow axis
        a_star  = float(lab[0, 0, 1])
        chroma  = (a_star**2 + b_star**2)**0.5
        if chroma < 8.0:
            return "neutral"
        if b_star > 4.0:
            return "warm"
        return "cool"

    def test_orange_is_warm(self):
        assert self._classify((230, 130, 30)) == "warm"

    def test_yellow_is_warm(self):
        assert self._classify((255, 220, 50)) == "warm"

    def test_blue_is_cool(self):
        assert self._classify((30, 80, 220)) == "cool"

    def test_cyan_is_cool(self):
        assert self._classify((30, 200, 220)) == "cool"

    def test_grey_is_neutral(self):
        assert self._classify((128, 128, 128)) == "neutral"

    def test_white_is_neutral(self):
        assert self._classify((250, 250, 250)) == "neutral"

    def test_lab_b_channel_index_is_2(self):
        """Confirm LAB channel index: 0=L*, 1=a*, 2=b*. This guards against the previous bug."""
        arr = np.array([[[230, 130, 30]]], dtype=np.float32) / 255.0   # orange
        lab = skcolor.rgb2lab(arr)
        b_star = lab[0, 0, 2]
        a_star = lab[0, 0, 1]
        assert b_star > 0,  "b* (index 2) must be positive for orange (warm)"
        assert b_star > abs(a_star), "b* should dominate for orange vs pure red"


# ── Region hierarchy tests ────────────────────────────────────────────────────

class TestRegionHierarchy:
    def _run(self, img, palette_size=6, detail_level=3, value_zones=3):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.colours import extract_colour_families
        from backend.analysis.regions import build_region_hierarchy
        cache = prepare(img)
        _, _, colour_internal = extract_colour_families(cache, palette_size=palette_size)
        label_maps, regions = build_region_hierarchy(
            cache=cache,
            palette_size=palette_size,
            detail_level=detail_level,
            n_value_zones=value_zones,
            value_colour_families=colour_internal,
            seed=0,
        )
        return label_maps, regions

    def test_produces_regions(self):
        img = _flat_colour_image([(200,50,50), (50,200,50), (50,50,200)])
        _, regions = self._run(img)
        assert len(regions) > 0

    def test_palette_count_independent_of_region_count(self):
        """palette_size and region count must be independent parameters."""
        img = _flat_colour_image([(200,50,50), (50,200,50), (50,50,200)])
        # With palette_size=3 and detail_level=5 we should still get more regions than 3
        _, regions_d5 = self._run(img, palette_size=3, detail_level=5)
        _, regions_d1 = self._run(img, palette_size=3, detail_level=1)
        # Regions at detail level 5 ≥ regions at level 1
        assert len(regions_d5) >= len(regions_d1), \
            "More detail levels should produce at least as many regions"

    def test_two_areas_same_colour_remain_separate_regions(self):
        """Two spatially separate red areas should be separate regions."""
        img = _two_region_same_colour()
        _, regions = self._run(img, palette_size=6, detail_level=3)
        assert len(regions) >= 2, "Separate spatial regions must not be merged just because colours match"

    def test_all_regions_have_valid_parent_at_fine_scale(self):
        """Every non-coarse region must have a parent_id or be parentless at coarse."""
        img = _flat_colour_image([(200,50,50), (50,200,50), (50,50,200)])
        _, regions = self._run(img, detail_level=5)
        # All parent_ids that are set should be non-negative integers
        for r in regions:
            if r.parent_id is not None:
                assert isinstance(r.parent_id, int)
                assert r.parent_id >= 0


# ── Edge hierarchy tests ──────────────────────────────────────────────────────

class TestEdgeHierarchy:
    def _run(self, img):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy, render_outline_levels
        cache = prepare(img)
        edges, maps = extract_edge_hierarchy(cache, None, None)
        outlines = render_outline_levels(maps)
        return edges, maps, outlines

    def test_primary_edges_are_subset_of_full(self):
        img = _contour_with_texture()
        _, maps, outlines = self._run(img)
        primary       = maps["primary"].astype(bool)
        full_combined = np.maximum.reduce([maps[k] for k in maps]).astype(bool)
        # Every pixel that is a primary edge must also appear in the full combined map
        assert np.all(full_combined[primary]), \
            "Primary edge pixels must all appear in the full combined edge map"

    def test_primary_secondary_adds_more_pixels(self):
        img = _contour_with_texture()
        _, maps, outlines = self._run(img)
        n_primary = int((maps["primary"] > 0).sum())
        n_ps      = int(
            np.maximum(maps["primary"], maps["secondary"]).astype(bool).sum()
        )
        assert n_ps >= n_primary, "primary+secondary must have >= pixels than primary alone"

    def test_four_composite_outline_images_exist(self):
        img = _contour_with_texture()
        _, _, outlines = self._run(img)
        expected = {"outlines_primary", "outlines_primary_secondary", "outlines_detailed", "outlines_full"}
        assert set(outlines.keys()) == expected

    def test_full_detail_does_not_lose_decorative_regions(self):
        """The full outline image must have at least as many edge pixels as outlines_detailed."""
        img = _contour_with_texture()
        _, _, outlines = self._run(img)
        n_detailed = int((outlines["outlines_detailed"] < 128).sum())   # dark px = edge
        n_full     = int((outlines["outlines_full"]     < 128).sum())
        assert n_full >= n_detailed


# ── Colour family tests ───────────────────────────────────────────────────────

class TestColourFamilies:
    def _run(self, img, palette_size=6):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.colours import extract_colour_families
        cache = prepare(img)
        return extract_colour_families(cache, palette_size=palette_size, seed=0)

    def test_palette_count_matches_requested(self):
        img = _flat_colour_image([(200,50,50), (50,200,50), (50,50,200), (200,200,50)])
        families, palette, _ = self._run(img, palette_size=4)
        assert len(families) == 4
        assert len(palette)  == 4

    def test_families_have_variations(self):
        img = _flat_colour_image([(200,50,50), (50,200,50)])
        families, _, _ = self._run(img, palette_size=2)
        for f in families:
            assert "shadow"    in f.variations
            assert "highlight" in f.variations

    def test_warm_cool_neutral_classified_distinctly(self):
        """orange/blue/grey image → 3 distinct colour families."""
        img = _warm_cool_neutral()
        families, _, _ = self._run(img, palette_size=3)
        base_labs = [f.base_lab for f in families]
        # All b* values should differ (warm has high b*, cool has low b*, grey near 0)
        b_stars = sorted(lab[2] for lab in base_labs)
        assert b_stars[-1] - b_stars[0] > 20, "warm/cool families must differ in b* by >20 LAB units"


# ── Notan tests ───────────────────────────────────────────────────────────────

class TestNotan:
    def _notan(self, img, zones=3):
        from backend.pipeline.artist_breakdown.processor import notan
        return notan(img, zones=zones)

    def test_three_zones_returns_image(self):
        img = _gradient_brightness()
        result = self._notan(img, zones=3)
        assert isinstance(result, Image.Image)

    def test_five_zones_returns_image(self):
        img = _gradient_brightness()
        result = self._notan(img, zones=5)
        assert isinstance(result, Image.Image)

    def test_three_zones_uses_full_value_range(self):
        """With 3 zones, should use full range from near-black to near-white."""
        img = _gradient_brightness()
        result = self._notan(img, zones=3)
        arr    = np.array(result.convert("L"))
        assert arr.min() < 80,  "Darkest zone should be dark"
        assert arr.max() > 180, "Lightest zone should be near-white"

    def test_zones_correct_count_of_grey_values(self):
        img    = _gradient_brightness()
        result = self._notan(img, zones=5)
        arr    = np.array(result.convert("L"))
        unique = np.unique(arr)
        assert len(unique) == 5, f"Expected 5 unique grey values for 5 zones, got {len(unique)}: {unique}"


class TestEdgeSVGExport:
    def _setup(self):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy
        img   = _contour_with_texture()
        cache = prepare(img)
        edges, maps = extract_edge_hierarchy(cache, None)
        return edges, cache

    def test_svg_starts_with_svg_tag(self):
        from backend.analysis.edges import export_edges_svg
        edges, cache = self._setup()
        svg = export_edges_svg(edges, cache.W, cache.H)
        assert svg.strip().startswith("<svg "), "SVG must start with <svg"

    def test_svg_closes_correctly(self):
        from backend.analysis.edges import export_edges_svg
        edges, cache = self._setup()
        svg = export_edges_svg(edges, cache.W, cache.H)
        assert "</svg>" in svg

    def test_svg_has_correct_dimensions(self):
        from backend.analysis.edges import export_edges_svg
        edges, cache = self._setup()
        svg = export_edges_svg(edges, cache.W, cache.H)
        assert f'width="{cache.W}"' in svg
        assert f'height="{cache.H}"' in svg

    def test_texture_detail_false_zeros_texture_map(self):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy
        img   = _contour_with_texture()
        cache = prepare(img)
        _, maps_without = extract_edge_hierarchy(cache, None, include_texture=False)
        assert maps_without["texture"].sum() == 0, \
            "texture map must be all-zero when include_texture=False"

    def test_include_texture_true_may_have_texture_edges(self):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy
        img   = _contour_with_texture()
        cache = prepare(img)
        edges_with, _ = extract_edge_hierarchy(cache, None, include_texture=True)
        # At least some edges should exist (texture or otherwise)
        assert len(edges_with) > 0
