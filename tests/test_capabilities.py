"""
Capability-registry invariants.

These tests exist to kill the recurring bug class where a new study/step
shipped in the backend but was missing from one of the hand-maintained
frontend catalogues (PRs #15, #16, #17). The registry is now the only
catalogue; these tests keep it internally consistent and keep every other
surface derived from it.
"""
from __future__ import annotations

from pathlib import Path

from backend.capabilities import (
    CAPABILITIES, CAPABILITY_BY_ID, DETAIL_LEVELS, LEVEL_LABELS, MIGRATIONS,
    STEP_INFO, registry_payload, resolve_capability_id, validate_registry,
)

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / "frontend" / "public" / "samples" / "demo1"


def test_registry_is_valid():
    assert validate_registry() == []


def test_capability_ids_unique_and_ordered():
    ids = [c.id for c in CAPABILITIES]
    assert len(ids) == len(set(ids))
    orders = [c.order for c in sorted(CAPABILITIES, key=lambda c: c.order)]
    assert orders == sorted(orders)


def test_every_pipeline_step_reference_resolves():
    for c in CAPABILITIES:
        if c.pipeline_step is not None:
            assert c.pipeline_step in STEP_INFO, c.id


def test_step_percentages_monotonic_enough():
    # Lifecycle ordering: loading first, completed last, all within 0-100.
    assert STEP_INFO["loading"].pct < STEP_INFO["hierarchical"].pct
    assert STEP_INFO["hierarchical"].pct < STEP_INFO["manifest"].pct
    assert STEP_INFO["completed"].pct == 100
    for name, info in STEP_INFO.items():
        assert 0 < info.pct <= 100, name
        assert 0 <= info.stage <= 5, name
        assert info.message and info.message != name, f"{name} needs a human message"


def test_detail_levels_are_1_to_5_and_never_claim_to_be_the_reference():
    assert [d.level for d in DETAIL_LEVELS] == [1, 2, 3, 4, 5]
    for d in DETAIL_LEVELS:
        assert "reference" not in d.label.lower(), (
            "'Reference' is reserved for the untouched original image"
        )
    assert LEVEL_LABELS[5] == "Full Detail"


def test_advertised_image_capabilities_have_samples_on_disk():
    """The gallery/landing must never advertise a study without a real sample."""
    for c in CAPABILITIES:
        if c.advertised and any(o.kind == "image" for o in c.outputs) and c.category != "internal":
            assert c.sample, f"{c.id} is advertised but declares no sample asset"
            assert (SAMPLES / c.sample).exists(), (
                f"{c.id}: sample {c.sample} missing from {SAMPLES}"
            )


def test_workspace_capabilities_have_teaching_copy():
    for c in CAPABILITIES:
        if c.workspace:
            assert c.why.strip(), f"{c.id} shown in workspace without a WHY explanation"
            assert c.tip.strip(), f"{c.id} shown in workspace without a tip"


def test_migrations_resolve():
    for m in MIGRATIONS:
        resolved = resolve_capability_id(m.old_id)
        if m.action in ("merge", "rename"):
            assert resolved == m.new_id, m.old_id
        elif m.action == "retire":
            assert resolved is None, m.old_id
    # Current ids resolve to themselves.
    for c in CAPABILITIES:
        assert resolve_capability_id(c.id) == c.id


def test_payload_shape():
    payload = registry_payload()
    assert set(payload) == {"capabilities", "steps", "detail_levels", "migrations"}
    assert len(payload["capabilities"]) == len(CAPABILITIES)
    # Sorted by display order for direct consumption by the frontend.
    orders = [c["order"] for c in payload["capabilities"]]
    assert orders == sorted(orders)


def test_modes_reflect_reality_no_overpromising():
    """No capability may claim a lesson/check mode that isn't implemented.
    Lesson mode is limited to the capabilities the Phase-4 engine actually
    teaches; check mode is still only the critique."""
    from backend.capabilities import LESSON_TAUGHT_CAPABILITIES
    for c in CAPABILITIES:
        if c.modes.lesson:
            assert c.id in LESSON_TAUGHT_CAPABILITIES, f"{c.id} claims an unimplemented lesson mode"
        if c.modes.check:
            assert c.id == "critique", f"{c.id} claims an unimplemented check mode"


def test_lesson_engine_only_teaches_registered_capabilities():
    """Every capability_id the lesson engine emits must be a real capability
    with lesson mode declared — the registry and engine cannot drift."""
    from backend.capabilities import LESSON_TAUGHT_CAPABILITIES, CAPABILITY_BY_ID
    from backend.teaching.lesson_engine import generate_lesson
    lesson = generate_lesson(
        drawing={"canvas_ratio": 0.75, "subject_bounds": {"margins": {}}, "landmarks": []},
        value_zones=[{"label": "shadow"}, {"label": "light"}],
        palette=[{"name": "Ultramarine"}], image_brief={"masses": [{"colour_name": "blue"}]},
        medium="oil", guidance="full",
    )
    step_caps = {s.capability_id for s in lesson.steps}
    for cid in step_caps:
        assert cid in CAPABILITY_BY_ID, f"lesson step references unknown capability {cid}"
    # capabilities the engine teaches (minus critique, which is check not lesson)
    assert step_caps - {"critique"} <= LESSON_TAUGHT_CAPABILITIES


def test_tasks_progress_derived_from_registry():
    from backend.workers.tasks import _PROGRESS
    assert _PROGRESS == {k: v.pct for k, v in STEP_INFO.items()}


def test_renderer_labels_derived_from_registry():
    from backend.analysis.renderer import _LEVEL_LABELS
    assert _LEVEL_LABELS is LEVEL_LABELS
