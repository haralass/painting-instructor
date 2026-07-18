"""Composition-first lesson engine (Phase 4)."""
from __future__ import annotations

import pytest

from backend.teaching.lesson_engine import generate_lesson, SKILL_TO_GUIDANCE
from backend.schemas.lesson import Lesson

DRAWING = {
    "canvas_ratio": 0.75,
    "subject_bounds": {"margins": {"top": 0.1, "bottom": 0.02, "left": 0.05, "right": 0.05},
                       "source": "subject_mask"},
    "landmarks": [{"id": f"lm{i}"} for i in range(12)],
}
VALUE_ZONES = [{"label": "shadow"}, {"label": "mid"}, {"label": "light"}]
PALETTE = [{"name": "Titanium White"}, {"name": "Ultramarine"}, {"name": "Burnt Umber"}]
BRIEF = {"masses": [{"colour_name": "blue", "value_label": "shadow", "location": "centre"}],
         "focal": {"location": "centre"}, "dark_fraction": 0.4,
         "warmest_colour": "Yellow Ochre", "coolest_colour": "Ultramarine"}


def _gen(medium="oil", guidance="full"):
    return generate_lesson(DRAWING, VALUE_ZONES, PALETTE, BRIEF, medium, guidance,
                           assets={"value_zones_map": "j/value_zones.png"})


def test_produces_a_valid_lesson():
    L = _gen()
    assert isinstance(L, Lesson)
    assert L.validate_graph() == []
    assert Lesson.model_validate_json(L.model_dump_json()) == L


def test_phases_are_in_the_correct_order():
    L = _gen()
    # The real painting order: plan small studies -> place -> draw ALL the
    # outlines -> block-in (value+colour together) -> develop -> render focal
    # -> finish. Whole-to-part, never property-by-property.
    phase_order = ["plan", "composition", "drawing", "block_in", "develop", "render", "finish"]
    seen = [s.phase for s in L.steps]
    last = -1
    for ph in seen:
        idx = phase_order.index(ph)
        assert idx >= last, f"phase {ph} out of order"
        last = max(last, idx)
    # nothing gets painted before the drawing checkpoint
    draw_cp = next(i for i, s in enumerate(L.steps) if s.checkpoint_id == "cp_silhouette")
    for s in L.steps[:draw_cp]:
        assert s.phase in ("plan", "composition", "drawing"), \
            f"{s.title} paints before the drawing checkpoint"


def test_drawing_checkpoint_gates_before_values():
    L = _gen()
    cps = {c.type for c in L.checkpoints}
    assert "silhouette" in cps                      # the drawing checkpoint
    silhouette_cp = next(c for c in L.checkpoints if c.type == "silhouette")
    assert silhouette_cp.required
    # it comes before the first value step
    draw_cp_order = next(s.order for s in L.steps if s.checkpoint_id == "cp_silhouette")
    first_paint_order = next((s.order for s in L.steps if s.phase == "block_in"), 1e9)
    assert draw_cp_order < first_paint_order


def test_shadow_line_is_drawn_before_the_checkpoint_and_any_paint():
    """User requirement: outlines — including TONAL outlines — are drawing
    steps, before any paint."""
    L = _gen()
    titles = [s.title for s in L.steps]
    shadow = next(i for i, t in enumerate(titles) if "shadow line" in t.lower())
    checkpoint = next(i for i, s in enumerate(L.steps) if s.checkpoint_id == "cp_silhouette")
    first_paint = next(i for i, s in enumerate(L.steps) if s.phase == "block_in")
    assert shadow < checkpoint < first_paint
    assert L.steps[shadow].phase == "drawing"


def test_block_in_combines_value_and_colour_in_one_pass():
    """Whole-to-part: value and colour go down together as masses — not one
    property across the canvas, then the next."""
    L = _gen()
    block = next(s for s in L.steps if s.phase == "block_in" and s.title.startswith("Block in"))
    assert "value and colour" in block.title.lower() or "value and colour" in block.objective.lower()
    assert "whole" in (block.objective + block.action).lower()
    # no step teaches colour as a separate whole-canvas phase after values
    assert not any(s.phase in ("value", "colour") for s in L.steps)


def test_every_step_carries_structured_teaching_data():
    L = _gen()
    for s in L.steps:
        assert s.objective and s.action
        assert s.completion_check is not None
        # pivotal/normal steps should name a common mistake
        assert s.common_mistake, f"{s.title} has no common_mistake"


def test_progressive_contour_lesson_order():
    """Envelope before silhouette before internal divisions (spec §8)."""
    L = _gen()
    titles = [s.title for s in L.steps]
    env = next(i for i, t in enumerate(titles) if "envelope" in t.lower())
    sil = next(i for i, t in enumerate(titles) if "silhouette" in t.lower())
    intl = next(i for i, t in enumerate(titles) if "internal divisions" in t.lower())
    assert env < sil < intl


def test_guidance_changes_granularity_not_geometry():
    full = _gen(guidance="full")
    balanced = _gen(guidance="balanced")
    autonomy = _gen(guidance="autonomy")
    assert len(full.steps) > len(balanced.steps) > len(autonomy.steps)
    # autonomy keeps only the two structural gates
    assert {c.type for c in autonomy.checkpoints} == {"silhouette", "final"}
    # the drawing checkpoint survives every guidance level (never simplified away)
    for L in (full, balanced, autonomy):
        assert any(c.type == "silhouette" for c in L.checkpoints)


def test_medium_changes_execution_not_order():
    oil = _gen("oil")
    wc = _gen("watercolor")
    # composition + drawing are medium-agnostic, so those step titles are
    # identical; watercolour may add extra *value*-phase steps (e.g. "Reserve
    # the whites"), so the canonical phase order — not the exact step list —
    # is the invariant that must hold across mediums.
    oil_structural = [s.title for s in oil.steps if s.phase in ("composition", "drawing")]
    wc_structural = [s.title for s in wc.steps if s.phase in ("composition", "drawing")]
    assert oil_structural == wc_structural
    phase_order = ["plan", "composition", "drawing", "block_in", "develop", "render", "finish"]
    for L in (oil, wc):
        idxs = [phase_order.index(s.phase) for s in L.steps]
        assert idxs == sorted(idxs), f"phase order broken for medium {L.medium}"
    # different surface-prep execution
    oil_surface = next(s.action for s in oil.steps if s.title == "Prepare the surface")
    wc_surface = next(s.action for s in wc.steps if s.title == "Prepare the surface")
    assert oil_surface != wc_surface
    assert "white" in wc_surface.lower() or "paper" in wc_surface.lower()


def test_watercolor_reserves_whites_oil_does_not():
    wc = _gen("watercolor")
    oil = _gen("oil")
    assert any(s.title == "Reserve the whites" for s in wc.steps)
    assert not any(s.title == "Reserve the whites" for s in oil.steps)
    reserve = next(s for s in wc.steps if s.title == "Reserve the whites")
    assert reserve.phase == "block_in"
    assert reserve.completion_check is not None and reserve.common_mistake
    # it comes before the block-in pass itself
    block = next(s for s in wc.steps if s.title.startswith("Block in"))
    prepare_surface = next(s for s in wc.steps if s.title == "Prepare the surface")
    assert prepare_surface.order < reserve.order < block.order


def test_watercolor_value_step_is_strictly_light_to_dark_and_dry_judged():
    wc = _gen("watercolor")
    value_step = next(s for s in wc.steps if s.title.startswith("Block in"))
    text = value_step.action.lower()
    assert "light-to-dark" in text or "light to dark" in text
    assert "dried" in text or "dry" in text
    assert "unrecoverable" in text or "can't lift" in text or "cannot lift" in text


def test_oil_keeps_imprimatura_and_notes_fat_over_lean():
    oil = _gen("oil")
    surface = next(s for s in oil.steps if s.title == "Prepare the surface")
    assert "imprimatura" in surface.action.lower()
    form = next(s for s in oil.steps if s.title == "Model the form")
    assert "fat over lean" in form.action.lower()


def test_acrylic_notes_sections_premixing_and_glazing():
    acrylic = _gen("acrylic")
    value_step = next(s for s in acrylic.steps if s.title.startswith("Block in"))
    text = value_step.action.lower()
    assert "section" in text
    assert "pre-mix" in text or "premix" in text
    form = next(s for s in acrylic.steps if s.title == "Model the form")
    assert "glaz" in form.action.lower()


def test_pencil_and_charcoal_replace_mixtures_with_value_range():
    for medium in ("pencil", "charcoal"):
        L = _gen(medium)
        titles = [s.title for s in L.steps]
        assert "Prepare the working mixtures" not in titles, f"{medium} should not mix paint"
        assert "Set your value range" in titles
        value_range = next(s for s in L.steps if s.title == "Set your value range")
        assert value_range.phase == "block_in"
        assert "3 value masses" in value_range.objective or "three value masses" in value_range.objective.lower()
    # every other medium still mixes real paint/colour
    for medium in ("oil", "watercolor", "acrylic", "digital"):
        titles = [s.title for s in _gen(medium).steps]
        assert "Prepare the working mixtures" in titles
        assert "Set your value range" not in titles


def test_charcoal_value_range_step_tones_then_lifts():
    charcoal = _gen("charcoal")
    step = next(s for s in charcoal.steps if s.title == "Set your value range")
    text = step.action.lower()
    assert "lift" in text
    assert "grey" in text or "gray" in text
    # the sheet-toning itself happens earlier, in "Prepare the surface"
    surface = next(s for s in charcoal.steps if s.title == "Prepare the surface")
    assert "tone" in surface.action.lower()
    assert surface.order < step.order


def test_digital_uses_selections_not_layer_per_object():
    digital = _gen("digital")
    value_step = next(s for s in digital.steps if s.title.startswith("Block in"))
    text = value_step.action.lower()
    assert "selection" in text or "mask" in text
    assert "layer per object" in text or "layer-per-object" in text
    mixtures = next(s for s in digital.steps if s.title == "Prepare the working mixtures")
    assert "non-destructive" in mixtures.action.lower() or "non-destructively" in mixtures.action.lower()
    assert "reference" in mixtures.action.lower()


def test_composition_and_drawing_phases_are_medium_agnostic():
    mediums = ["oil", "watercolor", "pencil"]
    lessons = {m: _gen(m) for m in mediums}
    reference = [s.title for s in lessons["oil"].steps if s.phase in ("composition", "drawing")]
    assert reference  # sanity: there really are structural steps to compare
    for m in mediums[1:]:
        titles = [s.title for s in lessons[m].steps if s.phase in ("composition", "drawing")]
        assert titles == reference, f"composition/drawing titles diverged for medium {m}"


def test_all_mediums_produce_a_valid_graph_at_every_guidance_level():
    for medium in ("oil", "watercolor", "acrylic", "pencil", "charcoal", "digital"):
        for guidance in ("full", "balanced", "autonomy"):
            L = generate_lesson(DRAWING, VALUE_ZONES, PALETTE, BRIEF, medium, guidance,
                                assets={"value_zones_map": "j/value_zones.png"})
            assert L.validate_graph() == [], f"{medium}/{guidance} graph invalid"
            # drawing checkpoint survives every guidance level, and still gates before values
            assert any(c.type == "silhouette" for c in L.checkpoints)
            draw_cp_order = next(s.order for s in L.steps if s.checkpoint_id == "cp_silhouette")
            first_paint_order = next((s.order for s in L.steps if s.phase == "block_in"), 1e9)
            assert draw_cp_order < first_paint_order


def test_skill_maps_to_guidance():
    assert SKILL_TO_GUIDANCE["beginner"] == "full"
    assert SKILL_TO_GUIDANCE["advanced"] == "autonomy"


def test_grounded_in_image_facts():
    L = _gen()
    text = " ".join(s.action + s.objective for s in L.steps)
    assert "0.75" in text                       # canvas ratio from the drawing
    assert "Ultramarine" in text or "Titanium White" in text   # real palette names
