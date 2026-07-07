"""Unit tests for the image-specific lesson planner — pure functions, no I/O."""
import pytest

from backend.teaching.planner import (
    build_image_brief,
    attach_image_notes,
    _loc_word,
    _light_words,
)
from backend.teaching.lesson import build_lesson_plan
from backend.teaching.mediums import get_medium

W, H = 900, 600

PALETTE = [
    {"id": 0, "name": "burnt sienna", "base_rgb": (140, 70, 40),  "area_fraction": 0.4},
    {"id": 1, "name": "sky blue",     "base_rgb": (110, 150, 210), "area_fraction": 0.3},
    {"id": 2, "name": "ivory",        "base_rgb": (235, 228, 210), "area_fraction": 0.3},
]

ZONES = [
    {"id": 0, "label": "shadow",  "grey_value": 40},
    {"id": 1, "label": "midtone", "grey_value": 128},
    {"id": 2, "label": "light",   "grey_value": 220},
]


def _region(rid, scale, cx, cy, area, rgb=(128, 128, 128), zone=1, importance=0.5, texture=0.1):
    return {
        "id": rid, "scale": scale, "level": int(scale[1]) if scale.startswith("l") else 1,
        "area": area, "centroid": (cx, cy), "bbox": (0, 0, 10, 10),
        "mean_lab": (50.0, 0.0, 0.0), "mean_rgb": rgb,
        "value_zone": zone, "colour_family_id": 0,
        "importance": importance, "texture_score": texture,
    }


@pytest.fixture
def regions():
    regs = [
        # 3 big masses at level 1: dark lower-left, light top, mid centre-right
        _region(1, "l1", W * 0.2, H * 0.8, int(W * H * 0.40), rgb=(120, 60, 35),  zone=0),
        _region(2, "l1", W * 0.5, H * 0.1, int(W * H * 0.35), rgb=(230, 225, 205), zone=2),
        _region(3, "l1", W * 0.8, H * 0.5, int(W * H * 0.25), rgb=(115, 145, 200), zone=1),
        # l3: focal region upper right with max importance
        _region(10, "l3", W * 0.75, H * 0.25, 5000, importance=0.95),
        _region(11, "l3", W * 0.3,  H * 0.6,  5000, importance=0.30),
    ]
    # l5: pile 30 tiny regions into the lower right to create a busy cell
    for i in range(30):
        regs.append(_region(100 + i, "l5", W * 0.85, H * 0.9, 50))
    # and a few scattered elsewhere
    for i in range(6):
        regs.append(_region(200 + i, "l5", W * (0.1 + 0.1 * i), H * 0.3, 50))
    return regs


class TestLocationAndLightWords:
    def test_grid_corners(self):
        assert _loc_word(0.05, 0.05) == "upper left"
        assert _loc_word(0.95, 0.95) == "lower right"
        assert _loc_word(0.5, 0.5) == "centre"

    def test_light_sectors(self):
        assert _light_words(90) == "above"
        assert _light_words(0) == "the right"
        assert _light_words(180) == "the left"
        assert _light_words(135) == "the upper left"


class TestImageBrief:
    def test_masses_sorted_by_area_with_locations(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, 135.0, W, H, "oil")
        masses = brief["masses"]
        assert [m["region_id"] for m in masses[:3]] == [1, 2, 3]
        assert masses[0]["location"] == "lower left"
        assert masses[0]["colour_name"] == "burnt sienna"
        assert masses[0]["value_label"] == "shadow"

    def test_block_in_order_dark_first_for_oil(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, None, W, H, "oil")
        assert brief["block_in_order"][0] == 1          # darkest mass first
        assert brief["block_in_light_first"] is False

    def test_block_in_order_light_first_for_watercolor(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, None, W, H, "watercolor")
        assert brief["block_in_order"][0] == 2          # lightest mass first
        assert brief["block_in_light_first"] is True

    def test_focal_is_max_importance_l3(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, None, W, H, "oil")
        assert brief["focal"]["location"] == "upper right"

    def test_busy_area_detected(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, None, W, H, "oil")
        assert brief["busy_areas"], "expected the lower-right l5 pile to be flagged"
        assert brief["busy_areas"][0]["location"] == "lower right"

    def test_overview_mentions_light_and_mass(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, 135.0, W, H, "oil")
        assert "upper left" in brief["overview"]        # light words
        assert "lower left" in brief["overview"]        # biggest mass location

    def test_empty_regions_do_not_crash(self):
        brief = build_image_brief([], PALETTE, ZONES, None, W, H, "oil")
        assert brief["masses"] == []
        assert isinstance(brief["overview"], str)


class TestAttachImageNotes:
    def _steps(self, medium="oil", skill="intermediate"):
        cfg = get_medium(medium)
        return build_lesson_plan(
            medium_cfg=cfg, medium=medium,
            detail_levels={str(i): {"values": f"l{i}v.png", "colours": f"l{i}c.png",
                                    "outlines": f"l{i}o.png", "regions": f"l{i}r.png"}
                           for i in range(1, 6)},
            outline_composites={k: f"{k}.png" for k in
                                ("outlines_primary", "outlines_primary_secondary",
                                 "outlines_detailed", "outlines_full")},
            value_zones_map="zones.png",
            classic_pages=["j/notan.png", "j/color_temperature.png", "j/color_by_number.png"],
            skill_level=skill,
        )

    def test_every_step_gets_notes_field(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, 135.0, W, H, "oil")
        steps = attach_image_notes(self._steps(), brief, "oil")
        assert all("image_notes" in s for s in steps)
        assert any(s["image_notes"] for s in steps)

    def test_first_step_names_actual_masses(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, 135.0, W, H, "oil")
        steps = attach_image_notes(self._steps(), brief, "oil")
        first = next(s for s in steps if 1 <= s["order"] < 90)
        joined = " ".join(first["image_notes"])
        assert "burnt sienna" in joined and "lower left" in joined
        assert "the upper left" in joined  # light direction

    def test_detail_step_warns_about_busy_area(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, None, W, H, "oil")
        steps = attach_image_notes(self._steps(), brief, "oil")
        last = max(steps, key=lambda s: s["order"] if s["order"] < 90 else -1)
        joined = " ".join(last["image_notes"])
        assert "lower right" in joined and "simplify" in joined.lower()

    def test_image_notes_still_present_alongside_micro_steps(self, regions):
        brief = build_image_brief(regions, PALETTE, ZONES, 135.0, W, H, "oil")
        steps = attach_image_notes(self._steps(), brief, "oil")
        # both fields exist on every step; image_notes behaviour unchanged
        assert all("image_notes" in s for s in steps)
        assert all("image_micro_steps" in s for s in steps)
        first = next(s for s in steps if 1 <= s["order"] < 90)
        assert "burnt sienna" in " ".join(first["image_notes"])


# ── 5+ masses so every mass must surface as its own ordered micro-step ────────

ZONES5 = [
    {"id": 0, "label": "shadow",     "grey_value": 30},
    {"id": 1, "label": "dark",       "grey_value": 80},
    {"id": 2, "label": "midtone",    "grey_value": 128},
    {"id": 3, "label": "light",      "grey_value": 185},
    {"id": 4, "label": "highlight",  "grey_value": 235},
]


@pytest.fixture
def regions5():
    """Five level-1 masses at distinct value zones and locations."""
    return [
        _region(1, "l1", W * 0.15, H * 0.85, int(W * H * 0.30), rgb=(110, 55, 35),  zone=0),
        _region(2, "l1", W * 0.50, H * 0.10, int(W * H * 0.24), rgb=(235, 228, 205), zone=4),
        _region(3, "l1", W * 0.85, H * 0.50, int(W * H * 0.18), rgb=(120, 150, 205), zone=2),
        _region(4, "l1", W * 0.40, H * 0.45, int(W * H * 0.14), rgb=(90, 115, 70),   zone=1),
        _region(5, "l1", W * 0.10, H * 0.20, int(W * H * 0.10), rgb=(200, 180, 150), zone=3),
    ]


class TestImageMicroSteps:
    def _steps(self, medium="oil"):
        cfg = get_medium(medium)
        return build_lesson_plan(
            medium_cfg=cfg, medium=medium,
            detail_levels={str(i): {"values": f"l{i}v.png", "colours": f"l{i}c.png",
                                    "outlines": f"l{i}o.png", "regions": f"l{i}r.png"}
                           for i in range(1, 6)},
            outline_composites={k: f"{k}.png" for k in
                                ("outlines_primary", "outlines_primary_secondary",
                                 "outlines_detailed", "outlines_full")},
            value_zones_map="zones.png",
            classic_pages=["j/notan.png", "j/color_temperature.png", "j/color_by_number.png"],
            skill_level="intermediate",
        )

    def _all_micro(self, steps):
        return [ms for s in steps for ms in s["image_micro_steps"]]

    def test_every_step_has_micro_steps_field(self, regions5):
        brief = build_image_brief(regions5, PALETTE, ZONES5, 135.0, W, H, "oil")
        steps = attach_image_notes(self._steps("oil"), brief, "oil")
        assert all(isinstance(s.get("image_micro_steps"), list) for s in steps)

    def test_every_mass_appears_exactly_once(self, regions5):
        brief = build_image_brief(regions5, PALETTE, ZONES5, 135.0, W, H, "oil")
        steps = attach_image_notes(self._steps("oil"), brief, "oil")
        micro = self._all_micro(steps)
        ids = [m["region_id"] for m in micro]
        assert sorted(ids) == [1, 2, 3, 4, 5]
        assert len(ids) == len(set(ids)) == 5

    def test_order_is_sequential_within_the_step(self, regions5):
        brief = build_image_brief(regions5, PALETTE, ZONES5, 135.0, W, H, "oil")
        steps = attach_image_notes(self._steps("oil"), brief, "oil")
        # micro-steps land on exactly one step
        carriers = [s for s in steps if s["image_micro_steps"]]
        assert len(carriers) == 1
        orders = [m["order"] for m in carriers[0]["image_micro_steps"]]
        assert orders == [1, 2, 3, 4, 5]

    def test_dark_first_direction_for_oil(self, regions5):
        brief = build_image_brief(regions5, PALETTE, ZONES5, None, W, H, "oil")
        steps = attach_image_notes(self._steps("oil"), brief, "oil")
        micro = self._all_micro(steps)
        # darkest mass (zone 0, region 1) is blocked in first
        assert micro[0]["region_id"] == 1
        # strictly non-decreasing grey along the sequence (dark → light)
        greys = [_grey_of(m["region_id"]) for m in micro]
        assert greys == sorted(greys)

    def test_light_first_direction_for_watercolor(self, regions5):
        brief = build_image_brief(regions5, PALETTE, ZONES5, None, W, H, "watercolor")
        steps = attach_image_notes(self._steps("watercolor"), brief, "watercolor")
        micro = self._all_micro(steps)
        # lightest mass (zone 4, region 2) is washed in first
        assert micro[0]["region_id"] == 2
        greys = [_grey_of(m["region_id"]) for m in micro]
        assert greys == sorted(greys, reverse=True)

    def test_micro_step_shape_matches_contract(self, regions5):
        brief = build_image_brief(regions5, PALETTE, ZONES5, 135.0, W, H, "oil")
        steps = attach_image_notes(self._steps("oil"), brief, "oil")
        m = self._all_micro(steps)[0]
        assert set(m.keys()) == {
            "order", "region_id", "location", "value_label",
            "colour_name", "area_frac", "action", "mix_hint",
        }
        assert isinstance(m["order"], int) and m["order"] >= 1
        assert isinstance(m["region_id"], int)
        assert isinstance(m["location"], str) and m["location"]
        assert isinstance(m["value_label"], str) and m["value_label"]
        assert isinstance(m["colour_name"], str) and m["colour_name"]
        assert isinstance(m["area_frac"], float)
        assert isinstance(m["action"], str) and m["action"].endswith(".")
        assert m["mix_hint"] is None or isinstance(m["mix_hint"], str)

    def test_mix_hint_present_for_paint_medium_null_for_digital(self, regions5):
        oil_brief = build_image_brief(regions5, PALETTE, ZONES5, None, W, H, "oil")
        oil_steps = attach_image_notes(self._steps("oil"), oil_brief, "oil")
        assert any(m["mix_hint"] for m in self._all_micro(oil_steps))

        dig_brief = build_image_brief(regions5, PALETTE, ZONES5, None, W, H, "digital")
        dig_steps = attach_image_notes(self._steps("digital"), dig_brief, "digital")
        assert all(m["mix_hint"] is None for m in self._all_micro(dig_steps))

    def test_micro_steps_attached_to_early_block_in_not_ground_or_detail(self, regions5):
        brief = build_image_brief(regions5, PALETTE, ZONES5, None, W, H, "oil")
        steps = attach_image_notes(self._steps("oil"), brief, "oil")
        carrier = next(s for s in steps if s["image_micro_steps"])
        # oil: order 1 is the toned-ground, order >= 5 are edge/detail
        assert carrier["order"] == 2

    def test_empty_when_no_masses(self):
        brief = build_image_brief([], PALETTE, ZONES5, None, W, H, "oil")
        steps = attach_image_notes(
            build_lesson_plan(
                medium_cfg=get_medium("oil"), medium="oil",
                detail_levels={}, outline_composites={},
                value_zones_map="z.png", classic_pages=["j/notan.png"],
                skill_level="intermediate",
            ),
            brief, "oil",
        )
        assert all(s["image_micro_steps"] == [] for s in steps)


def _grey_of(region_id: int) -> int:
    """Grey value for a regions5 region id, via its zone mapping."""
    zone_by_region = {1: 0, 2: 4, 3: 2, 4: 1, 5: 3}
    grey_by_zone = {z["id"]: z["grey_value"] for z in ZONES5}
    return grey_by_zone[zone_by_region[region_id]]


class TestNoSilentResolutionFailures:
    """Every stage of every medium must resolve to at least one real asset —
    guards against the color_temperature drop (and any future layer that fails
    to resolve like it)."""

    def _detail_levels(self):
        return {str(i): {"values": f"l{i}v.png", "colours": f"l{i}c.png",
                         "outlines": f"l{i}o.png", "regions": f"l{i}r.png"}
                for i in range(1, 6)}

    def _outline_composites(self):
        return {k: f"{k}.png" for k in
                ("outlines_primary", "outlines_primary_secondary",
                 "outlines_detailed", "outlines_full")}

    @pytest.mark.parametrize(
        "medium", ["oil", "watercolor", "acrylic", "pencil", "charcoal", "digital"]
    )
    def test_every_stage_yields_non_empty_assets(self, medium):
        steps = build_lesson_plan(
            medium_cfg=get_medium(medium), medium=medium,
            detail_levels=self._detail_levels(),
            outline_composites=self._outline_composites(),
            value_zones_map="zones.png",
            # NOTE: color_temperature / color_by_number pages deliberately
            # absent — they must still resolve via the canonical sibling path.
            classic_pages=["j/notan.png"],
            skill_level="intermediate",
        )
        for s in steps:
            if 1 <= s["order"] < 90:  # skip inserted warm-up/critique steps
                assert s["assets"], (
                    f"{medium} stage {s['order']} ({s['name']}) resolved no assets"
                )


class TestSkillLevels:
    def _steps(self, skill):
        cfg = get_medium("oil")
        return build_lesson_plan(
            medium_cfg=cfg, medium="oil",
            detail_levels={}, outline_composites={}, value_zones_map="zones.png",
            classic_pages=["j/notan.png"], skill_level=skill,
        )

    def test_beginner_gets_warmup_step_order_zero(self):
        steps = self._steps("beginner")
        assert steps[0]["order"] == 0
        assert "value" in steps[0]["name"].lower()
        # medium stage orders untouched (video mapping depends on them)
        assert [s["order"] for s in steps[1:]] == [1, 2, 3, 4, 5, 6]

    def test_advanced_gets_self_critique_step(self):
        steps = self._steps("advanced")
        assert steps[-1]["order"] == 99
        assert "critique" in steps[-1]["name"].lower()

    def test_intermediate_unchanged(self):
        steps = self._steps("intermediate")
        assert [s["order"] for s in steps] == [1, 2, 3, 4, 5, 6]

    def test_every_step_has_why(self):
        for skill in ("beginner", "intermediate", "advanced"):
            for s in self._steps(skill):
                assert s.get("why"), f"step {s['name']} ({skill}) is missing its why"
