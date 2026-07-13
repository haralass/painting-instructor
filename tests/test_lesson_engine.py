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
    phase_order = ["composition", "drawing", "value", "colour", "form", "edges", "detail"]
    seen = [s.phase for s in L.steps]
    # each phase's first appearance is monotonically non-decreasing in the canonical order
    last = -1
    for ph in seen:
        idx = phase_order.index(ph)
        assert idx >= last - 0, f"phase {ph} out of order"
        last = max(last, idx)
    # no value/colour/form/edge step before the drawing checkpoint
    draw_cp = next(i for i, s in enumerate(L.steps) if s.checkpoint_id == "cp_silhouette")
    for s in L.steps[:draw_cp]:
        assert s.phase in ("composition", "drawing"), f"{s.title} paints before the drawing checkpoint"


def test_drawing_checkpoint_gates_before_values():
    L = _gen()
    cps = {c.type for c in L.checkpoints}
    assert "silhouette" in cps                      # the drawing checkpoint
    silhouette_cp = next(c for c in L.checkpoints if c.type == "silhouette")
    assert silhouette_cp.required
    # it comes before the first value step
    draw_cp_order = next(s.order for s in L.steps if s.checkpoint_id == "cp_silhouette")
    first_value_order = next((s.order for s in L.steps if s.phase == "value"), 1e9)
    assert draw_cp_order < first_value_order


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
    # same phase sequence
    assert [s.phase for s in oil.steps] == [s.phase for s in wc.steps]
    # different surface-prep execution
    oil_surface = next(s.action for s in oil.steps if s.title == "Prepare the surface")
    wc_surface = next(s.action for s in wc.steps if s.title == "Prepare the surface")
    assert oil_surface != wc_surface
    assert "white" in wc_surface.lower() or "paper" in wc_surface.lower()


def test_skill_maps_to_guidance():
    assert SKILL_TO_GUIDANCE["beginner"] == "full"
    assert SKILL_TO_GUIDANCE["advanced"] == "autonomy"


def test_grounded_in_image_facts():
    L = _gen()
    text = " ".join(s.action + s.objective for s in L.steps)
    assert "0.75" in text                       # canvas ratio from the drawing
    assert "Ultramarine" in text or "Titanium White" in text   # real palette names
