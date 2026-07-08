"""
Closing the adaptive-teaching loop: a returning student's Adaptive Painter
Profile (backend/critique/profile.py) reshapes their NEXT lesson via three
deterministic, no-LLM levers — emphasis, per-user watch-out notes, and a
session goal. A missing/empty profile must leave the lesson byte-identical.
"""
import json

import pytest

from backend.teaching.lesson import build_lesson_plan
from backend.teaching.mediums import get_medium


DETAIL_LEVELS = {
    str(i): {"values": f"l{i}v.png", "colours": f"l{i}c.png",
             "outlines": f"l{i}o.png", "regions": f"l{i}r.png"}
    for i in range(1, 6)
}
OUTLINE_COMPOSITES = {
    k: f"{k}.png" for k in
    ("outlines_primary", "outlines_primary_secondary", "outlines_detailed", "outlines_full")
}
CLASSIC_PAGES = ["j/notan.png", "j/color_temperature.png", "j/color_by_number.png"]


def _plan(profile=None, skill="intermediate", medium="oil"):
    return build_lesson_plan(
        medium_cfg=get_medium(medium), medium=medium,
        detail_levels=DETAIL_LEVELS,
        outline_composites=OUTLINE_COMPOSITES,
        value_zones_map="zones.png",
        classic_pages=CLASSIC_PAGES,
        skill_level=skill,
        profile=profile,
    )


def _weakness(metric, signed_mean, direction):
    return {
        "metric": metric, "signed_mean": signed_mean, "magnitude": abs(signed_mean),
        "consistency": 0.9, "trend": "stable", "severity": abs(signed_mean) * 0.9,
        "direction": direction,
    }


def _profile(*weaknesses, n=6):
    return {
        "user_id": "u", "n_critiques": n, "updated_at": 1.0,
        "metrics": {}, "weaknesses": list(weaknesses), "by_medium": {},
        "summary": "test",
    }


VALUE_PROFILE = _profile(
    _weakness("value_compression", 0.42, "compresses the value range (not enough dark/light)")
)
CHROMA_PROFILE = _profile(
    _weakness("chroma_bias", 0.5, "oversaturates")
)


class TestByteIdenticalWithoutProfile:
    def test_none_profile_matches_no_profile(self):
        assert json.dumps(_plan(None)) == json.dumps(_plan())

    def test_empty_profile_matches_no_profile(self):
        empty = {"user_id": "u", "n_critiques": 0, "metrics": {},
                 "weaknesses": [], "by_medium": {}, "summary": "none"}
        assert json.dumps(_plan(empty)) == json.dumps(_plan())

    def test_empty_dict_matches_no_profile(self):
        assert json.dumps(_plan({})) == json.dumps(_plan())

    def test_profile_with_unmapped_only_weakness_is_noop(self):
        # a metric with no teaching-category mapping -> no lever fires
        prof = _profile({"metric": "not_a_metric", "signed_mean": 0.9,
                         "magnitude": 0.9, "consistency": 0.9, "trend": "stable",
                         "severity": 0.8, "direction": "does something"})
        assert json.dumps(_plan(prof)) == json.dumps(_plan())


class TestValueCompressionLever:
    def test_value_stage_is_emphasized(self):
        plan = _plan(VALUE_PROFILE)
        emphasized = [s for s in plan if s.get("emphasis")]
        assert len(emphasized) == 1
        # oil's value stage is "Value masses" at order 3
        assert emphasized[0]["order"] == 3
        assert "value" in emphasized[0]["name"].lower()

    def test_value_stage_gets_a_profile_note(self):
        plan = _plan(VALUE_PROFILE)
        stage = next(s for s in plan if s["order"] == 3)
        assert isinstance(stage.get("profile_notes"), list) and stage["profile_notes"]
        note = stage["profile_notes"][0]
        assert "6" in note              # n_critiques templated in
        assert "value range" in note

    def test_forces_value_warmup_for_non_beginner(self):
        plan = _plan(VALUE_PROFILE, skill="intermediate")
        assert plan[0]["order"] == 0
        assert "value" in plan[0]["name"].lower()
        # medium stage orders untouched
        assert [s["order"] for s in plan if 1 <= s["order"] < 90] == [1, 2, 3, 4, 5, 6]

    def test_lesson_goal_on_first_step(self):
        plan = _plan(VALUE_PROFILE)
        assert "15%" in plan[0].get("lesson_goal", "")

    def test_beginner_does_not_double_insert_warmup(self):
        plan = _plan(VALUE_PROFILE, skill="beginner")
        assert sum(1 for s in plan if s["order"] == 0) == 1


class TestChromaLever:
    def test_colour_stage_gets_watch_out(self):
        plan = _plan(CHROMA_PROFILE)
        # oil's colour stage is "Colour modelling" at order 4
        stage = next(s for s in plan if s["order"] == 4)
        assert stage.get("emphasis") is True
        assert stage.get("profile_notes")
        assert "neutral" in stage["profile_notes"][0].lower()

    def test_chroma_does_not_force_value_warmup(self):
        plan = _plan(CHROMA_PROFILE, skill="intermediate")
        assert all(s["order"] != 0 for s in plan)
        assert plan[0].get("lesson_goal")  # goal still attached to first real step

    def test_only_top_weakness_stage_emphasized(self):
        # value ranked below chroma -> only the colour stage is touched
        prof = _profile(
            _weakness("chroma_bias", 0.6, "oversaturates"),
            _weakness("value_compression", 0.3, "compresses the value range"),
        )
        plan = _plan(prof)
        emphasized = [s for s in plan if s.get("emphasis")]
        assert [s["order"] for s in emphasized] == [4]
