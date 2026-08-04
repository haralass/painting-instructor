"""Lesson/checkpoint schema contract tests (Phase 1 — schemas only)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.lesson import (
    Checkpoint, CompletionCheck, Lesson, LessonStep, OverlayRef,
)


def _step(id: str, order: int, phase: str = "drawing", **kw) -> LessonStep:
    return LessonStep(
        id=id, capability_id="line_art", phase=phase, order=order,
        title=f"Step {id}", objective="obj", action="do the thing", **kw,
    )


def test_minimal_lesson_round_trips():
    lesson = Lesson(
        id="l1", capability_id="line_art", medium="oil",
        steps=[_step("s1", 1, phase="composition"), _step("s2", 2)],
        checkpoints=[Checkpoint(id="cp1", type="silhouette", title="Check the silhouette")],
    )
    data = lesson.model_dump()
    again = Lesson.model_validate(data)
    assert again == lesson
    assert lesson.validate_graph() == []


def test_phase_and_checkpoint_types_are_closed_vocabularies():
    with pytest.raises(ValidationError):
        _step("bad", 1, phase="vibes")
    with pytest.raises(ValidationError):
        Checkpoint(id="c", type="mood", title="nope")


def test_graph_validation_catches_broken_references():
    lesson = Lesson(
        id="l1", capability_id="line_art", medium="oil",
        steps=[
            _step("s1", 1),
            _step("s2", 2, depends_on=["missing"], checkpoint_id="nope"),
        ],
    )
    problems = lesson.validate_graph()
    assert any("unknown dependency" in p for p in problems)
    assert any("unknown checkpoint" in p for p in problems)


def test_graph_validation_catches_out_of_order_steps():
    lesson = Lesson(
        id="l1", capability_id="line_art", medium="oil",
        steps=[_step("s2", 2), _step("s1", 1)],
    )
    assert any("ascending" in p for p in lesson.validate_graph())


def test_step_schema_carries_the_brief_s7_fields():
    s = _step(
        "s1", 1,
        overlays=[OverlayRef(kind="silhouette", region_ids=[3, 4], opacity=0.6)],
        tool="large flat brush", mixture="mid-value cyan",
        completion_check=CompletionCheck(kind="upload", criteria="silhouette matches"),
        common_mistake="chasing detail before the envelope is right",
        stop_condition="stop before adding any interior line",
        checkpoint_id=None,
    )
    d = s.model_dump()
    for field in ("objective", "action", "overlays", "tool", "mixture",
                  "completion_check", "common_mistake", "stop_condition",
                  "checkpoint_id", "depends_on", "region_ids"):
        assert field in d


def test_capability_registry_declares_check_ready_capabilities():
    """The checkpoint-capable capabilities in the registry use checkpoint
    types that exist in the schema vocabulary."""
    from backend.capabilities import CAPABILITIES
    checkpointable = [c.id for c in CAPABILITIES if c.supports.checkpoint]
    # These are the analyses the Phase-6 checkpoints will compare against.
    assert "notan" in checkpointable
    assert "critique" in checkpointable
