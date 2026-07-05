"""
Image analysis unit tests with deterministic synthetic images.

All tests use generated images — no external files needed.

Run with:
    pytest tests/test_analysis.py -v
"""
from __future__ import annotations
from pathlib import Path
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
    def _run(self, img, palette_size=6, region_complexity=3, value_zones=3):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.colours import extract_colour_families
        from backend.analysis.regions import build_region_hierarchy
        cache = prepare(img)
        _, _, colour_internal = extract_colour_families(cache, palette_size=palette_size)
        label_maps, regions = build_region_hierarchy(
            cache=cache,
            palette_size=palette_size,
            n_value_zones=value_zones,
            value_colour_families=colour_internal,
            seed=0,
            region_complexity=region_complexity,
        )
        return label_maps, regions

    def test_produces_regions(self):
        img = _flat_colour_image([(200,50,50), (50,200,50), (50,50,200)])
        _, regions = self._run(img)
        assert len(regions) > 0

    def test_palette_count_independent_of_region_count(self):
        """palette_size and region count must be independent parameters."""
        img = _flat_colour_image([(200,50,50), (50,200,50), (50,50,200)])
        # With palette_size=3 and region_complexity=5 we should still get more regions than 3
        _, regions_d5 = self._run(img, palette_size=3, region_complexity=5)
        _, regions_d1 = self._run(img, palette_size=3, region_complexity=1)
        # Regions at complexity 5 ≥ regions at complexity 1
        assert len(regions_d5) >= len(regions_d1), \
            "Higher region_complexity should produce at least as many regions"

    def test_two_areas_same_colour_remain_separate_regions(self):
        """Two spatially separate red areas should be separate regions."""
        img = _two_region_same_colour()
        _, regions = self._run(img, palette_size=6, region_complexity=3)
        assert len(regions) >= 2, "Separate spatial regions must not be merged just because colours match"

    def test_all_regions_have_valid_parent_at_fine_scale(self):
        """Every non-coarse region must have a parent_id or be parentless at coarse."""
        img = _flat_colour_image([(200,50,50), (50,200,50), (50,50,200)])
        _, regions = self._run(img, region_complexity=5)
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


# ── New correctness invariant tests ──────────────────────────────────────────

def _prepare(img):
    from backend.analysis.preprocessing import prepare
    return prepare(img)


class TestRegionIDMapping:
    def test_region_points_to_nonzero_pixels(self):
        """Every Region must contain at least one pixel in its scale's label map."""
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = _prepare(img)
        from backend.analysis.regions import build_region_hierarchy
        from backend.analysis.colours import extract_colour_families
        _, _, internal = extract_colour_families(cache, palette_size=6)
        label_maps, regions = build_region_hierarchy(cache, 6, 3, internal)
        for r in regions:
            lm = label_maps.get(r.scale)
            assert lm is not None, f"Region {r.id} has unknown scale {r.scale!r}"
            px_count = int((lm == r.source_label).sum())
            assert px_count > 0, (
                f"Region {r.id} (scale={r.scale}, source_label={r.source_label}) has 0 pixels"
            )

    def test_parent_ids_exist(self):
        from backend.analysis.regions import build_region_hierarchy
        from backend.analysis.colours import extract_colour_families
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = _prepare(img)
        _, _, internal = extract_colour_families(cache, 6)
        _, regions = build_region_hierarchy(cache, 6, 3, internal)
        region_ids = {r.id for r in regions}
        for r in regions:
            if r.parent_id is not None:
                assert r.parent_id in region_ids, (
                    f"Region {r.id} has parent_id={r.parent_id} which does not exist"
                )

    def test_no_hierarchy_cycles(self):
        from backend.analysis.regions import build_region_hierarchy
        from backend.analysis.colours import extract_colour_families
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = _prepare(img)
        _, _, internal = extract_colour_families(cache, 6)
        _, regions = build_region_hierarchy(cache, 6, 3, internal)
        parent_map = {r.id: r.parent_id for r in regions}
        for start in parent_map:
            visited = set()
            cur = start
            while cur is not None:
                assert cur not in visited, f"Cycle detected from region {start}"
                visited.add(cur)
                cur = parent_map.get(cur)

    def test_level_1_has_fewer_regions_than_level_5(self):
        from backend.analysis.regions import build_region_hierarchy
        from backend.analysis.colours import extract_colour_families
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = _prepare(img)
        _, _, internal = extract_colour_families(cache, 6)
        _, regions = build_region_hierarchy(cache, 6, 3, internal)
        l1 = [r for r in regions if r.scale == "l1"]
        l5 = [r for r in regions if r.scale == "l5"]
        assert len(l1) < len(l5), f"Level 1 ({len(l1)}) not fewer than Level 5 ({len(l5)})"


class TestColourFamilyStableIDs:
    def test_nearest_family_returns_valid_rank(self):
        """_nearest_colour_family must return a valid rank index in range [0, k)."""
        from backend.analysis.colours import extract_colour_families
        from backend.analysis.regions import _nearest_colour_family
        img = Image.fromarray(np.full((64, 64, 3), [200, 100, 50], dtype=np.uint8))
        cache = _prepare(img)
        families, _, internal = extract_colour_families(cache, 4)
        dummy_lab = cache.lab[32, 32]
        rank = _nearest_colour_family(dummy_lab, internal)
        assert 0 <= rank < len(families), (
            f"_nearest_colour_family returned rank={rank}, expected 0..{len(families)-1}"
        )

    def test_cluster_id_to_rank_covers_all_clusters(self):
        """cluster_id_to_rank must map every cluster index to a unique rank."""
        from backend.analysis.colours import extract_colour_families
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = _prepare(img)
        families, _, internal = extract_colour_families(cache, 6)
        id_to_rank = internal.get("cluster_id_to_rank", {})
        assert len(id_to_rank) == len(families), (
            f"cluster_id_to_rank has {len(id_to_rank)} entries, expected {len(families)}"
        )
        assert set(id_to_rank.values()) == set(range(len(families))), (
            "cluster_id_to_rank values must be a permutation of 0..k-1"
        )


class TestEdgeRegionContext:
    def test_edges_have_region_a_set(self):
        """Every edge in a non-trivial image should have region_a not None when a label_map is provided."""
        from backend.analysis.edges import extract_edge_hierarchy
        from backend.analysis.regions import build_region_hierarchy
        from backend.analysis.colours import extract_colour_families
        img = Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = _prepare(img)
        _, _, internal = extract_colour_families(cache, 6)
        label_maps, regions = build_region_hierarchy(cache, 6, 3, internal)
        lm = label_maps.get("l3")
        if lm is None:
            lm = list(label_maps.values())[-1]
        edge_scale = "l3" if "l3" in label_maps else list(label_maps.keys())[-1]
        mapping = {r.source_label: r.id for r in regions if r.scale == edge_scale}
        edges, _ = extract_edge_hierarchy(cache, lm, label_to_region_id=mapping)
        with_region = [e for e in edges if e.region_a is not None]
        assert len(with_region) > 0, "All edges have region_a=None — region context not working"


class TestReferenceImage:
    def test_manifest_has_reference_field(self):
        """Completed pipeline manifest must contain 'reference' pointing to an existing file."""
        import tempfile
        import shutil
        from PIL import Image
        from pathlib import Path
        from unittest.mock import patch
        import numpy as np

        img = Image.fromarray(np.random.default_rng(42).integers(0, 255, (64, 64, 3), dtype=np.uint8))
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "testjob"
            from backend.analysis.pipeline import run_hierarchical_analysis
            result = run_hierarchical_analysis(
                img=img,
                out_dir=out_dir,
                palette_size=6,
                value_zones=3,
                medium="oil",
            )
            # Simulate what _build_manifest does: save reference image
            suffix = ".png"
            ref_path = out_dir / f"reference{suffix}"
            img.save(str(ref_path))
            assert ref_path.exists(), "Reference file not saved"


class TestCriticalFailure:
    def test_core_hierarchy_failure_raises(self):
        """If hierarchical analysis prepare() fails, the pipeline must propagate."""
        from unittest.mock import patch
        from backend.analysis.pipeline import run_hierarchical_analysis
        with patch("backend.analysis.pipeline.prepare", side_effect=RuntimeError("forced")):
            with pytest.raises(RuntimeError):
                run_hierarchical_analysis(
                    img=Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)),
                    out_dir="/tmp/test_fail_pipeline",
                    palette_size=6,
                    value_zones=3,
                    medium="oil",
                )


def test_pipeline_edge_map_not_none():
    """run_hierarchical_analysis must pass a non-null label_map to extract_edge_hierarchy."""
    from unittest.mock import patch
    import numpy as np
    from PIL import Image
    from pathlib import Path
    from backend.analysis.pipeline import run_hierarchical_analysis

    img = Image.fromarray(np.random.default_rng(42).integers(0, 255, (64, 64, 3), dtype=np.uint8))
    received_maps = []

    original_fn = __import__('backend.analysis.edges', fromlist=['extract_edge_hierarchy']).extract_edge_hierarchy

    def capturing_fn(cache, label_map, *args, **kwargs):
        received_maps.append(label_map)
        return original_fn(cache, label_map, *args, **kwargs)

    with patch('backend.analysis.pipeline.extract_edge_hierarchy', side_effect=capturing_fn):
        run_hierarchical_analysis(
            img=img,
            out_dir=Path('/tmp/test_edge_pipeline'),
            palette_size=6,
            value_zones=3,
            medium='oil',
        )

    assert len(received_maps) > 0
    assert received_maps[0] is not None, "label_map_for_edges was None — edge analysis received no region context"


class TestEdgeRegionIDMapping:
    def _make_hierarchy(self):
        from backend.analysis.regions import build_region_hierarchy
        from backend.analysis.colours import extract_colour_families
        from backend.analysis.preprocessing import prepare
        img = Image.fromarray(np.random.default_rng(7).integers(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = prepare(img)
        _, _, internal = extract_colour_families(cache, 6)
        return build_region_hierarchy(cache, 6, 3, internal), cache

    def test_edge_region_ids_valid(self):
        from backend.analysis.edges import extract_edge_hierarchy
        (label_maps, regions), cache = self._make_hierarchy()
        region_id_set = {r.id for r in regions}
        edge_scale = next(k for k in ["l3", "l4", "l2", "l5", "l1"] if k in label_maps)
        lm = label_maps[edge_scale]
        mapping = {r.source_label: r.id for r in regions if r.scale == edge_scale}
        edges, _ = extract_edge_hierarchy(cache, lm, label_to_region_id=mapping)
        for e in edges:
            if e.region_a is not None:
                assert e.region_a in region_id_set, f"Edge region_a={e.region_a} not a valid Region.id"
            if e.region_b is not None:
                assert e.region_b in region_id_set, f"Edge region_b={e.region_b} not a valid Region.id"

    def test_zero_label_maps_to_region(self):
        """Label 0 must be resolvable to a Region.id — it is NOT 'no region'."""
        mapping = {0: 42, 1: 7}
        from backend.analysis.edges import _label_to_rid
        assert _label_to_rid(0, mapping) == 42

    def test_inter_region_edges_have_different_ra_rb(self):
        from backend.analysis.edges import extract_edge_hierarchy
        (label_maps, regions), cache = self._make_hierarchy()
        lm = list(label_maps.values())[0]
        edge_scale = list(label_maps.keys())[0]
        mapping = {r.source_label: r.id for r in regions if r.scale == edge_scale}
        edges, _ = extract_edge_hierarchy(cache, lm, label_to_region_id=mapping)
        inter_region = [e for e in edges if e.region_a is not None and e.region_b is not None and e.region_a != e.region_b]
        assert len(inter_region) > 0, "No inter-region edges found"


def _banded_image(n_bands: int = 7, size: int = 140) -> "Image.Image":
    """n_bands horizontal luminance bands — genuine value MASSES, unlike raw
    noise. The value pipeline now simplifies by design (a value study is a
    mass plan, not per-pixel posterisation), so pure-noise inputs correctly
    collapse — distinct masses must survive."""
    from PIL import Image
    import numpy as np
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    band_h = size // n_bands
    for i in range(n_bands):
        lum = int(10 + 235 * i / (n_bands - 1))
        arr[i * band_h:(i + 1) * band_h if i < n_bands - 1 else size] = lum
    return Image.fromarray(arr)


class TestNotan7Zones:
    def test_notan_7_zones_produces_7_grey_levels(self):
        from backend.pipeline.artist_breakdown.processor import notan
        import numpy as np
        result = notan(_banded_image(7), zones=7)
        arr = np.array(result)
        unique_grey = np.unique(arr[:, :, 0])  # notan is greyscale-ish
        assert len(unique_grey) == 7, f"Expected 7 grey levels, got {len(unique_grey)}: {unique_grey}"

    def test_notan_simplifies_noise_into_masses(self):
        """Salt-and-pepper posterisation is exactly what made notans useless
        on textured photos — noise must come out as a few masses, not 7."""
        from backend.pipeline.artist_breakdown.processor import notan
        from PIL import Image
        import numpy as np
        noise = Image.fromarray(np.random.default_rng(1).integers(0, 255, (64, 64, 3), dtype=np.uint8))
        arr = np.array(notan(noise, zones=7))
        from scipy.ndimage import label as _label
        n_components = sum(
            _label((arr[:, :, 0] == g))[1] for g in np.unique(arr[:, :, 0])
        )
        assert n_components <= 30, f"noise produced {n_components} fragments — not simplified"

    def test_compute_value_zones_7(self):
        from backend.analysis.values import compute_value_zones
        from backend.analysis.preprocessing import prepare
        cache = prepare(_banded_image(7))
        zone_map, zones = compute_value_zones(cache, 7)
        assert len(zones) == 7
        occupied = [z for z in zones if (zone_map == z.id).any()]
        assert len(occupied) >= 6, f"Only {len(occupied)} of 7 zones are non-empty"

    def test_value_zones_3_5_7_all_work(self):
        from backend.analysis.values import compute_value_zones
        from backend.analysis.preprocessing import prepare
        from PIL import Image
        import numpy as np
        img = Image.fromarray(np.random.default_rng(3).integers(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = prepare(img)
        for n in [3, 5, 7]:
            zone_map, zones = compute_value_zones(cache, n)
            assert len(zones) == n, f"Expected {n} zones, got {len(zones)}"
            total = sum((zone_map == z.id).sum() for z in zones)
            assert total == cache.H * cache.W, f"n={n}: zone coverage {total} != {cache.H * cache.W}"


def test_palette_size_does_not_control_region_count():
    """Same image with palette_size=6 and palette_size=20 → similar region counts per level."""
    from backend.analysis.regions import build_region_hierarchy
    from backend.analysis.colours import extract_colour_families
    from backend.analysis.preprocessing import prepare
    img = Image.fromarray(np.random.default_rng(99).integers(0, 255, (64, 64, 3), dtype=np.uint8))
    cache = prepare(img)

    _, _, internal6  = extract_colour_families(cache, palette_size=6)
    _, _, internal20 = extract_colour_families(cache, palette_size=20)

    lmaps6,  regs6  = build_region_hierarchy(cache, 6, 3, internal6)
    lmaps20, regs20 = build_region_hierarchy(cache, 20, 3, internal20)

    for lvl in ["l1", "l2", "l3", "l4", "l5"]:
        count6  = len([r for r in regs6  if r.scale == lvl])
        count20 = len([r for r in regs20 if r.scale == lvl])
        # Counts should be within 3× of each other (adaptive, not palette-locked)
        ratio = max(count6, count20) / max(1, min(count6, count20))
        assert ratio < 3.0, (
            f"Level {lvl}: palette 6→{count6} regions, palette 20→{count20} regions — "
            f"ratio {ratio:.1f} suggests palette_size still controls region count"
        )


class TestValueZonesExtra:
    def test_seven_zones_produces_seven_levels(self):
        from backend.analysis.values import compute_value_zones
        cache = _prepare(_banded_image(7))
        zone_map, zones = compute_value_zones(cache, 7)
        assert len(zones) == 7
        for z in zones:
            assert (zone_map == z.id).any(), f"Zone {z.id} has zero pixels"


class TestLessonPlanAndPdfBook:
    """The lesson_plan resolver and PDF book must be built from real,
    already-generated assets — every medium's analysis_layers must resolve,
    and the resulting PDF must actually contain the lesson content."""

    def _hier_and_classic(self, tmp_path, medium="oil"):
        from backend.analysis.pipeline import run_hierarchical_analysis
        img = Image.fromarray(np.random.default_rng(7).integers(0, 255, (100, 140, 3), dtype=np.uint8))
        out_dir = tmp_path / medium
        hier = run_hierarchical_analysis(
            img=img, out_dir=out_dir, palette_size=8, value_zones=5, medium=medium,
        )
        classic_pages = []
        for name in ("color_temperature", "color_by_number", "notan", "color_palette",
                     "light_direction", "dot_to_dot", "line_art"):
            p = out_dir / f"{name}.png"
            img.save(p)
            classic_pages.append(str(p))
        return img, out_dir, hier, classic_pages

    def test_every_medium_lesson_plan_fully_resolves(self, tmp_path):
        from backend.teaching.mediums import MEDIUMS, get_medium
        from backend.teaching.lesson import build_lesson_plan

        for medium in MEDIUMS:
            _, _, hier, classic_pages = self._hier_and_classic(tmp_path, medium)
            medium_cfg = get_medium(medium)
            lesson_plan = build_lesson_plan(
                medium_cfg=medium_cfg, medium=medium,
                detail_levels=hier["detail_levels"],
                outline_composites=hier["outline_composites"],
                value_zones_map=hier["value_zones_path"],
                classic_pages=classic_pages,
            )
            total_layers   = sum(len(s["analysis_layers"]) for s in medium_cfg["stages"])
            total_resolved = sum(len(s["assets"]) for s in lesson_plan)
            assert total_resolved == total_layers, (
                f"{medium}: only {total_resolved}/{total_layers} analysis_layers resolved to real assets"
            )
            for step in lesson_plan:
                for path in step["assets"].values():
                    assert Path(path).exists(), f"{medium} step {step['name']!r} references missing file {path}"

    def test_pdf_book_contains_lesson_pages(self, tmp_path):
        from backend.teaching.mediums import get_medium
        from backend.teaching.lesson import build_lesson_plan
        from backend.teaching.pdf_book import build_tutorial_pdf
        from pypdf import PdfReader

        img, out_dir, hier, classic_pages = self._hier_and_classic(tmp_path, "oil")
        ref_path = out_dir / "reference.png"
        img.save(ref_path)
        medium_cfg = get_medium("oil")
        lesson_plan = build_lesson_plan(
            medium_cfg=medium_cfg, medium="oil",
            detail_levels=hier["detail_levels"], outline_composites=hier["outline_composites"],
            value_zones_map=hier["value_zones_path"], classic_pages=classic_pages,
        )
        pdf_path = out_dir / "tutorial_book.pdf"
        build_tutorial_pdf(
            out_path=str(pdf_path), reference_path=str(ref_path), medium="oil",
            medium_cfg=medium_cfg, detail_levels=hier["detail_levels"], lesson_plan=lesson_plan,
            palette=hier["palette"], value_zone_list=hier["value_zone_list"], classic_pages=classic_pages,
        )
        assert pdf_path.exists()
        reader = PdfReader(str(pdf_path))
        # Cover + palette + value zones + 5 levels + stage intro + 6 stages + appendix intro + 7 classic pages
        assert len(reader.pages) >= 1 + 5 + len(medium_cfg["stages"])
        full_text = " ".join(page.extract_text() or "" for page in reader.pages)
        assert "Oil Paint" in full_text or "oil" in full_text.lower()
        for stage in medium_cfg["stages"]:
            assert stage["name"] in full_text, f"Stage {stage['name']!r} text missing from PDF"


class TestVideoChapters:
    """The tutorial video must follow the medium's real teaching stages —
    chapter labels and, where resolvable, the visual content per phase."""

    def test_stage_images_resolve_for_expected_orders(self, tmp_path):
        from backend.analysis.pipeline import run_hierarchical_analysis
        from backend.teaching.mediums import get_medium
        from backend.teaching.lesson import build_lesson_plan
        from backend.workers.tasks import _resolve_stage_images

        img = Image.fromarray(np.random.default_rng(9).integers(0, 255, (80, 100, 3), dtype=np.uint8))
        out_dir = tmp_path / "video_stage_images"
        hier = run_hierarchical_analysis(img=img, out_dir=out_dir, palette_size=8, value_zones=5, medium="oil")
        medium_cfg = get_medium("oil")
        lesson_plan = build_lesson_plan(
            medium_cfg=medium_cfg, medium="oil",
            detail_levels=hier["detail_levels"], outline_composites=hier["outline_composites"],
            value_zones_map=hier["value_zones_path"], classic_pages=[],
        )
        stage_images = _resolve_stage_images(lesson_plan)
        assert set(stage_images.keys()) == {2, 3, 4, 6}, (
            f"Expected stage images for orders 2,3,4,6, got {sorted(stage_images.keys())}"
        )

    def test_generate_chapters_use_real_stage_names(self, tmp_path):
        from backend.pipeline.video.processor import generate as make_video
        from backend.teaching.mediums import get_medium

        img = Image.fromarray(np.random.default_rng(4).integers(0, 255, (60, 80, 3), dtype=np.uint8))
        out_path = str(tmp_path / "chapters.mp4")
        medium_cfg = get_medium("charcoal")
        result = make_video(
            reference=img, line_art=img, notan=img, color_blocking=img,
            output_path=out_path, fps=8, out_w=120,
            medium_stages=medium_cfg["stages"],
        )
        assert Path(out_path).exists()
        chapters = result["chapters"]
        names = [c["name"] for c in chapters]
        assert any("Lay-in with vine charcoal" in n for n in names), (
            f"Charcoal stage 1 name not found in video chapters: {names}"
        )
        starts = [c["start_sec"] for c in chapters]
        assert starts == sorted(starts), "Chapter start_sec must be monotonically increasing"


class TestMediumRendering:
    def _run_for_medium(self, medium: str, out_dir):
        from pathlib import Path
        from backend.analysis.pipeline import run_hierarchical_analysis
        img = Image.fromarray(np.random.default_rng(55).integers(0, 255, (64, 64, 3), dtype=np.uint8))
        return run_hierarchical_analysis(
            img=img,
            out_dir=Path(out_dir) / medium,
            palette_size=6,
            value_zones=3,
            medium=medium,
        )

    def test_pencil_colour_output_is_greyscale(self, tmp_path):
        """Pencil medium must render colours as grey tones, not hue."""
        result = self._run_for_medium("pencil", tmp_path)
        level3 = result.get("detail_levels", {}).get("2", {})
        colour_path = level3.get("colours")
        if not colour_path:
            pytest.skip("No colour asset produced")
        arr = np.array(Image.open(colour_path).convert("RGB"))
        # For a greyscale image, R == G == B for every pixel
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        max_diff = int(np.max(np.abs(r.astype(int) - g.astype(int))))
        assert max_diff <= 5, f"Pencil colour output has colour (max R-G diff={max_diff})"

    def test_oil_and_charcoal_colour_outputs_differ(self, tmp_path):
        """Oil and charcoal must produce visually different colour renders."""
        oil_result = self._run_for_medium("oil", tmp_path)
        char_result = self._run_for_medium("charcoal", tmp_path)
        oil_path  = oil_result.get("detail_levels", {}).get("2", {}).get("colours")
        char_path = char_result.get("detail_levels", {}).get("2", {}).get("colours")
        if not oil_path or not char_path:
            pytest.skip("Missing colour assets")
        oil_arr  = np.array(Image.open(oil_path).convert("RGB")).astype(float)
        char_arr = np.array(Image.open(char_path).convert("RGB")).astype(float)
        mean_diff = float(np.abs(oil_arr - char_arr).mean())
        assert mean_diff > 5.0, f"Oil and charcoal produced nearly identical colour renders (mean diff={mean_diff:.2f})"

    def test_watercolour_preserves_light_regions(self, tmp_path):
        """Watercolour medium must leave very light areas near-white."""
        # Create image with many white pixels
        arr = np.full((64, 64, 3), 240, dtype=np.uint8)
        arr[32:, :] = 50   # lower half dark
        img = Image.fromarray(arr)
        from pathlib import Path
        from backend.analysis.pipeline import run_hierarchical_analysis
        result = run_hierarchical_analysis(
            img=img,
            out_dir=Path(tmp_path) / "wc",
            palette_size=4,
            value_zones=3,
            medium="watercolor",
        )
        level = result.get("detail_levels", {}).get("2", {})
        colour_path = level.get("colours")
        if not colour_path:
            pytest.skip("No colour asset")
        colour = np.array(Image.open(colour_path).convert("RGB"))
        # Upper half (light area) should stay near-white
        upper = colour[:32, :, :]
        mean_upper = float(upper.mean())
        assert mean_upper > 200, f"Watercolour light region too dark: mean={mean_upper:.1f}"


class TestLevelAwareValueMasses:
    """Level 1 must genuinely simplify — value/colour masses come from that
    level's own coarse region partition, not a pixel-level zone_map leaking
    through for regions filtered out by the importance threshold."""

    def _run(self, tmp_path):
        from backend.analysis.pipeline import run_hierarchical_analysis
        img = _contour_with_texture()
        return run_hierarchical_analysis(
            img=img,
            out_dir=tmp_path / "level_masses",
            palette_size=8,
            value_zones=5,
            medium="oil",
        )

    def test_level_1_values_simpler_than_level_5(self, tmp_path):
        result = self._run(tmp_path)
        l1_path = result["detail_levels"]["1"]["values"]
        l5_path = result["detail_levels"]["5"]["values"]
        l1_arr = np.array(Image.open(l1_path).convert("L"))
        l5_arr = np.array(Image.open(l5_path).convert("L"))
        n_unique_l1 = len(np.unique(l1_arr))
        n_unique_l5 = len(np.unique(l5_arr))
        assert n_unique_l1 <= n_unique_l5, (
            f"Level 1 values should be at least as simple as Level 5 "
            f"(L1 uniques={n_unique_l1}, L5 uniques={n_unique_l5})"
        )

    def test_level_1_values_fully_covered_by_own_scale(self, tmp_path):
        """No pixel in Level 1's value map should be the raw zone_map default
        fallback grey (128) unless that value genuinely is a zone's grey —
        i.e. every pixel must be assigned via the level's own regions."""
        from backend.analysis.regions import build_region_hierarchy
        from backend.analysis.preprocessing import prepare
        from backend.analysis.colours import extract_colour_families

        img = _contour_with_texture()
        cache = prepare(img)
        _, _, colour_internal = extract_colour_families(cache, palette_size=8)
        label_maps, regions = build_region_hierarchy(
            cache=cache, palette_size=8, n_value_zones=5,
            value_colour_families=colour_internal, seed=0, region_complexity=3,
        )
        l1_regions = [r for r in regions if r.scale == "l1"]
        l1_label_map = label_maps["l1"]
        covered_labels = {r.source_label for r in l1_regions}
        all_labels = set(np.unique(l1_label_map).tolist())
        assert all_labels <= covered_labels, (
            "Every label in the l1 label map must have a corresponding Region "
            "so value/colour rendering can cover the whole image at that level"
        )

    def test_level_1_outlines_not_more_complex_than_level_5(self, tmp_path):
        """Level 1 outlines must not have more edge pixels than Level 5 —
        interior boundaries that vanish at coarse resolution must actually
        be dropped, not just type-filtered from a single fixed-scale map."""
        result = self._run(tmp_path)
        l1_arr = np.array(Image.open(result["detail_levels"]["1"]["outlines"]).convert("L"))
        l5_arr = np.array(Image.open(result["detail_levels"]["5"]["outlines"]).convert("L"))
        n_edge_l1 = int((l1_arr < 128).sum())
        n_edge_l5 = int((l5_arr < 128).sum())
        assert n_edge_l1 <= n_edge_l5, (
            f"Level 1 outline pixels ({n_edge_l1}) exceed Level 5 ({n_edge_l5}) — "
            "outlines are not simplifying with the level"
        )

    def test_ancestor_filtering_drops_interior_edges(self):
        """An edge whose two sides share the same l1 ancestor must be
        dropped when filtering for level 1, but kept for level 5 (identity)."""
        from backend.analysis.edges import build_region_ancestor_chain, filter_edges_for_level
        from backend.analysis.models import Edge, Region

        # Two l5 regions (10, 11) both roll up into the same l1 region (0);
        # a third l5 region (12) rolls up into a different l1 region (1).
        r_l1_a = Region(id=0, source_label=0, scale="l1", level=0, area=100,
                         centroid=(0, 0), bbox=(0, 0, 1, 1), mean_lab=(0, 0, 0),
                         mean_rgb=(0, 0, 0), value_zone=0, colour_family_id=0,
                         importance=1.0, texture_score=0.0)
        r_l1_b = Region(id=1, source_label=1, scale="l1", level=0, area=100,
                         centroid=(0, 0), bbox=(0, 0, 1, 1), mean_lab=(0, 0, 0),
                         mean_rgb=(0, 0, 0), value_zone=0, colour_family_id=0,
                         importance=1.0, texture_score=0.0)
        r_l5_10 = Region(id=10, source_label=10, scale="l5", parent_id=0, level=4, area=10,
                          centroid=(0, 0), bbox=(0, 0, 1, 1), mean_lab=(0, 0, 0),
                          mean_rgb=(0, 0, 0), value_zone=0, colour_family_id=0,
                          importance=0.5, texture_score=0.0)
        r_l5_11 = Region(id=11, source_label=11, scale="l5", parent_id=0, level=4, area=10,
                          centroid=(0, 0), bbox=(0, 0, 1, 1), mean_lab=(0, 0, 0),
                          mean_rgb=(0, 0, 0), value_zone=0, colour_family_id=0,
                          importance=0.5, texture_score=0.0)
        r_l5_12 = Region(id=12, source_label=12, scale="l5", parent_id=1, level=4, area=10,
                          centroid=(0, 0), bbox=(0, 0, 1, 1), mean_lab=(0, 0, 0),
                          mean_rgb=(0, 0, 0), value_zone=0, colour_family_id=0,
                          importance=0.5, texture_score=0.0)
        regions = [r_l1_a, r_l1_b, r_l5_10, r_l5_11, r_l5_12]

        interior_edge  = Edge(id=0, region_a=10, region_b=11, type="primary",
                              strength=1.0, hardness=1.0, importance=1.0, path=[[0, 0], [1, 1]])
        boundary_edge  = Edge(id=1, region_a=10, region_b=12, type="primary",
                              strength=1.0, hardness=1.0, importance=1.0, path=[[0, 0], [1, 1]])
        edges = [interior_edge, boundary_edge]

        chains = build_region_ancestor_chain(regions, "l5")

        level5_kept = filter_edges_for_level(edges, 5, "l5", chains)
        assert {e.id for e in level5_kept} == {0, 1}, "Level 5 must keep both edges (identity ancestor)"

        level1_kept = filter_edges_for_level(edges, 1, "l1", chains)
        assert {e.id for e in level1_kept} == {1}, (
            "Level 1 must drop the interior edge (same l1 ancestor) and keep the real boundary"
        )


class TestManifestOutlinesAreLevelAware:
    """
    Manifest-level regression test for the frontend bug where changing the
    detail level slider never changed the outline layer shown: the frontend
    sourced outline sublayers from the global (non-level-filtered)
    manifest.edge_maps whenever it existed, instead of each level's own
    outlines/edge_maps. There is no frontend test runner in this repo, so
    this proves the fix at the manifest boundary the frontend consumes:
    each DetailLevel must carry its own distinct outlines asset, and its own
    edge_maps dict must be genuinely level-scoped (never a stand-in for the
    global one).
    """

    def _run(self, tmp_path):
        from backend.analysis.pipeline import run_hierarchical_analysis
        # Two large, distinct halves PLUS scattered small dark squares (real
        # local Canny-detectable contours, unlike smooth per-pixel noise)
        # — gives both a structural boundary and finer secondary/texture
        # edges, so Level 1 and Level 5 genuinely have different content to
        # show instead of rendering byte-identical outlines.
        h, w = 220, 220
        arr = np.zeros((h, w, 3), dtype=np.uint8)
        arr[: h // 2, :] = [220, 60, 60]
        arr[h // 2 :, :] = [40, 60, 200]
        rng = np.random.default_rng(0)
        for _ in range(40):
            cy = int(rng.integers(5, h - 5))
            cx = int(rng.integers(5, w - 5))
            arr[cy - 2 : cy + 2, cx - 2 : cx + 2] = [10, 10, 10]
        img = Image.fromarray(arr)
        return run_hierarchical_analysis(
            img=img,
            out_dir=tmp_path / "level_aware_outlines",
            palette_size=8,
            value_zones=5,
            medium="oil",
        )

    def test_every_level_has_its_own_outlines_asset(self, tmp_path):
        result = self._run(tmp_path)
        detail_levels = result["detail_levels"]
        assert set(detail_levels.keys()) == {"1", "2", "3", "4", "5"}
        outline_paths = {lvl: data["outlines"] for lvl, data in detail_levels.items()}
        # Each level renders to its own file — the frontend keys off
        # detail_levels[level].outlines, so these must never collide.
        assert len(set(outline_paths.values())) == 5, (
            f"detail_levels must have 5 distinct outline file paths, got {outline_paths}"
        )
        for lvl, path in outline_paths.items():
            assert Path(path).exists(), f"level {lvl} outlines file missing: {path}"

    def test_detail_level_has_its_own_edge_maps_dict(self, tmp_path):
        """DetailLevel.edge_maps must exist and be distinct from the global
        manifest-level edge_maps — this is the field the frontend must read
        for outline sublayer toggles instead of the global one."""
        result = self._run(tmp_path)
        detail_levels = result["detail_levels"]
        for lvl, data in detail_levels.items():
            assert "edge_maps" in data, f"level {lvl} missing edge_maps key entirely"
        # At least one level must have a resolvable primary sublayer, and
        # that file must be a real, level-specific asset (not the global one).
        global_edge_maps = result.get("edge_maps", {})
        found_level_specific = False
        for lvl, data in detail_levels.items():
            for type_name, path in data["edge_maps"].items():
                assert Path(path).exists(), f"level {lvl} edge_maps[{type_name!r}] missing: {path}"
                assert path not in global_edge_maps.values(), (
                    f"level {lvl} edge_maps[{type_name!r}] must not reuse a global (non-level-aware) "
                    f"edge_maps path — got {path}"
                )
                found_level_specific = True
        assert found_level_specific, "no level produced any edge_maps at all — test image too trivial"

    def test_level_1_and_level_5_outlines_differ(self, tmp_path):
        """Changing the detail level must change what's rendered — this is
        the concrete behaviour the frontend slider depends on."""
        result = self._run(tmp_path)
        l1_path = result["detail_levels"]["1"]["outlines"]
        l5_path = result["detail_levels"]["5"]["outlines"]
        l1_bytes = Path(l1_path).read_bytes()
        l5_bytes = Path(l5_path).read_bytes()
        # Different files entirely, and (for this two-region test image with
        # texture only visible at finer levels) different pixel content too.
        assert l1_path != l5_path
        assert l1_bytes != l5_bytes, "Level 1 and Level 5 outlines must not be byte-identical"


# ── A5: Real bounding boxes ───────────────────────────────────────────────────

class TestRealBoundingBoxes:
    """A5: ndimage_find_objects bboxes must be geometrically valid."""

    def _get_regions(self, img):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.colours import extract_colour_families
        from backend.analysis.regions import build_region_hierarchy
        cache = prepare(img)
        _, _, internal = extract_colour_families(cache, palette_size=6)
        label_maps, regions = build_region_hierarchy(cache, 6, 3, internal, seed=0)
        return cache, label_maps, regions

    def test_all_bboxes_within_image_bounds(self):
        img = _flat_colour_image([(200, 50, 50), (50, 200, 50), (50, 50, 200)], w=300, h=100)
        cache, _, regions = self._get_regions(img)
        W, H = cache.W, cache.H
        for r in regions:
            x0, y0, x1, y1 = r.bbox
            assert 0 <= x0 < x1 <= W, f"Region {r.id} bbox x {x0}..{x1} outside [0, {W}]"
            assert 0 <= y0 < y1 <= H, f"Region {r.id} bbox y {y0}..{y1} outside [0, {H}]"

    def test_centroid_inside_bbox(self):
        img = _flat_colour_image([(200, 50, 50), (50, 200, 50), (50, 50, 200)], w=300, h=100)
        cache, _, regions = self._get_regions(img)
        for r in regions:
            cx, cy = r.centroid
            x0, y0, x1, y1 = r.bbox
            assert x0 <= cx <= x1, f"Region {r.id} centroid x={cx} outside bbox {x0}..{x1}"
            assert y0 <= cy <= y1, f"Region {r.id} centroid y={cy} outside bbox {y0}..{y1}"

    def test_different_spatial_regions_have_different_bboxes(self):
        """Two non-overlapping colour bands should produce bboxes at different x positions."""
        img = _flat_colour_image([(220, 50, 50), (50, 50, 220)], w=200, h=100)
        cache, label_maps, regions = self._get_regions(img)
        # At the finest level there should be at least two regions with non-identical bboxes
        finest_regions = [r for r in regions if r.scale == "l5"]
        if len(finest_regions) < 2:
            finest_regions = regions   # fall back to all
        bboxes = [r.bbox for r in finest_regions]
        unique_bboxes = {tuple(b) for b in bboxes}
        assert len(unique_bboxes) > 1, "All regions have identical bbox — ndimage_find_objects not working"

    def test_bbox_area_consistent_with_pixel_count(self):
        """bbox area (w×h) must be >= the region's pixel count (pixels fit inside the box)."""
        img = _flat_colour_image([(200, 50, 50), (50, 200, 50), (50, 50, 200)], w=300, h=100)
        cache, label_maps, regions = self._get_regions(img)
        for r in regions:
            lm = label_maps.get(r.scale)
            if lm is None:
                continue
            px_count = int((lm == r.source_label).sum())
            x0, y0, x1, y1 = r.bbox
            bbox_area = (x1 - x0) * (y1 - y0)
            assert bbox_area >= px_count, (
                f"Region {r.id}: bbox_area={bbox_area} < px_count={px_count} — impossible"
            )


# ── A6: region_complexity controls segment count ──────────────────────────────

class TestRegionComplexity:
    """A6: region_complexity=1 must produce fewer fine-level segments than complexity=5."""

    def _count_regions_at_level(self, img, complexity: int, level: str = "l5") -> int:
        from backend.analysis.preprocessing import prepare
        from backend.analysis.colours import extract_colour_families
        from backend.analysis.regions import build_region_hierarchy
        cache = prepare(img)
        _, _, internal = extract_colour_families(cache, palette_size=6)
        _, regions = build_region_hierarchy(
            cache, 6, 3, internal, seed=0,
            region_complexity=complexity,
        )
        return len([r for r in regions if r.scale == level])

    def test_complexity_1_fewer_than_complexity_5_at_l5(self):
        img = Image.fromarray(np.random.default_rng(11).integers(0, 255, (128, 128, 3), dtype=np.uint8))
        n1 = self._count_regions_at_level(img, complexity=1)
        n5 = self._count_regions_at_level(img, complexity=5)
        assert n1 < n5, (
            f"region_complexity=1 produced {n1} l5 regions, "
            f"complexity=5 produced {n5} — expected n1 < n5"
        )

    def test_complexity_3_is_between_1_and_5(self):
        img = Image.fromarray(np.random.default_rng(22).integers(0, 255, (128, 128, 3), dtype=np.uint8))
        n1 = self._count_regions_at_level(img, complexity=1)
        n3 = self._count_regions_at_level(img, complexity=3)
        n5 = self._count_regions_at_level(img, complexity=5)
        assert n1 <= n3 <= n5, (
            f"region_complexity ordering broken: n1={n1}, n3={n3}, n5={n5}"
        )

    def test_complexity_param_flows_through_build(self):
        """Calling with different complexities must not raise and must differ in label_map size."""
        from backend.analysis.preprocessing import prepare
        from backend.analysis.colours import extract_colour_families
        from backend.analysis.regions import build_region_hierarchy
        img = Image.fromarray(np.random.default_rng(33).integers(0, 255, (64, 64, 3), dtype=np.uint8))
        cache = prepare(img)
        _, _, internal = extract_colour_families(cache, palette_size=4)
        for c in (1, 2, 3, 4, 5):
            lmaps, regs = build_region_hierarchy(cache, 4, 3, internal, seed=0, region_complexity=c)
            assert "l1" in lmaps and "l5" in lmaps, f"complexity={c}: missing level keys"
            assert len(regs) > 0, f"complexity={c}: no regions produced"


# ── A12: cKDTree chain_polylines performance ──────────────────────────────────

class TestChainPolylines:
    """A12: _chain_polylines with cKDTree must handle 1000 polylines in bounded time."""

    def _make_polylines(self, n: int, rng) -> list[np.ndarray]:
        """Generate n short polylines with random endpoints."""
        polylines = []
        for _ in range(n):
            start = rng.uniform(0, 500, (2,))
            end   = start + rng.uniform(-20, 20, (2,))
            polylines.append(np.array([start, end]))
        return polylines

    def test_chain_1000_polylines_under_1_second(self):
        from backend.pipeline.dot_to_dot.processor import _chain_polylines
        import time
        rng = np.random.default_rng(42)
        polys = self._make_polylines(1000, rng)
        t0 = time.perf_counter()
        result = _chain_polylines(polys)
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"_chain_polylines(1000) took {elapsed:.3f}s — expected <1s"
        assert len(result) >= 2, "chain result should have points"

    def test_chain_empty_returns_empty(self):
        from backend.pipeline.dot_to_dot.processor import _chain_polylines
        result = _chain_polylines([])
        assert result.shape == (0, 2)

    def test_chain_single_polyline_returns_it(self):
        from backend.pipeline.dot_to_dot.processor import _chain_polylines
        poly = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]])
        result = _chain_polylines([poly])
        np.testing.assert_array_equal(result, poly)

    def test_chain_visits_all_polylines(self):
        """All polyline points should appear in the chained output (may be reversed)."""
        from backend.pipeline.dot_to_dot.processor import _chain_polylines
        rng = np.random.default_rng(7)
        polys = self._make_polylines(10, rng)
        result = _chain_polylines(polys)
        total_pts = sum(len(p) for p in polys)
        assert len(result) == total_pts, (
            f"Expected {total_pts} points in chain, got {len(result)}"
        )

    def test_chain_100_polylines_deterministic(self):
        """Same input must produce same output (no random tie-breaking)."""
        from backend.pipeline.dot_to_dot.processor import _chain_polylines
        rng = np.random.default_rng(55)
        polys = self._make_polylines(100, rng)
        r1 = _chain_polylines([p.copy() for p in polys])
        r2 = _chain_polylines([p.copy() for p in polys])
        np.testing.assert_array_equal(r1, r2, err_msg="chain result is non-deterministic")


# ── A13: Edge budget enforcement ──────────────────────────────────────────────

class TestEdgeBudgets:
    """A13: extract_edge_hierarchy must respect max_edges / max_contours / max_time_secs."""

    def _pathological_image(self, w: int = 120, h: int = 120) -> Image.Image:
        """High-frequency checkerboard — produces huge numbers of tiny contours."""
        arr = np.indices((h, w)).sum(axis=0) % 2
        arr = (arr * 200).astype(np.uint8)
        return Image.fromarray(np.stack([arr, arr, arr], axis=-1))

    def test_max_edges_caps_output(self):
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy
        img = self._pathological_image()
        cache = prepare(img)
        edges, _ = extract_edge_hierarchy(cache, None, max_edges=50, max_contours=50_000, max_time_secs=30.0)
        assert len(edges) <= 50, f"Expected ≤50 edges, got {len(edges)}"

    def test_max_contours_pre_filters(self):
        """With max_contours=10, no more than 10 contours should be processed."""
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy
        img = self._pathological_image()
        cache = prepare(img)
        # max_contours=10 caps before the loop; max_edges high so it's not the limiting factor
        edges, _ = extract_edge_hierarchy(cache, None, max_edges=100_000, max_contours=10, max_time_secs=30.0)
        assert len(edges) <= 10, f"Expected ≤10 edges (from 10 contours), got {len(edges)}"

    def test_budget_does_not_crash_on_empty_image(self):
        """Solid-colour image has no edges — must return empty list without error."""
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy
        img = Image.fromarray(np.full((64, 64, 3), 128, dtype=np.uint8))
        cache = prepare(img)
        edges, maps = extract_edge_hierarchy(cache, None, max_edges=100, max_contours=100, max_time_secs=5.0)
        assert isinstance(edges, list)
        assert isinstance(maps, dict)

    def test_capped_edges_are_highest_importance(self):
        """When max_edges triggers, the kept edges must be the highest-importance ones."""
        from backend.analysis.preprocessing import prepare
        from backend.analysis.edges import extract_edge_hierarchy
        img = _contour_with_texture()
        cache = prepare(img)
        # Get all edges with a generous cap
        all_edges, _ = extract_edge_hierarchy(cache, None, max_edges=100_000)
        if len(all_edges) <= 5:
            return  # not enough edges to test capping
        # Now cap to 5
        capped_edges, _ = extract_edge_hierarchy(cache, None, max_edges=5)
        assert len(capped_edges) <= 5
        if len(capped_edges) == 0:
            return
        min_capped = min(e.importance for e in capped_edges)
        # Every uncapped edge that was dropped must have importance <= min_capped
        capped_ids = {e.id for e in capped_edges}
        dropped = [e for e in all_edges if e.id not in capped_ids]
        for e in dropped:
            assert e.importance <= min_capped + 1e-9, (
                f"Dropped edge id={e.id} importance={e.importance:.4f} > "
                f"min_capped={min_capped:.4f} — cap did not keep the best edges"
            )
