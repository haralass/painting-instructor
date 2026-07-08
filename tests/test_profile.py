"""Adaptive painter profile tests — deterministic, no network, no ML."""
import json

import pytest

from backend.critique.profile import (
    METRIC_KEYS,
    record_critique,
    recompute_profile,
    load_profile,
    _profile_path,
    _history_path,
)


def _result(errors: dict, *, medium: str = "oil", align: float = 1.0) -> dict:
    """Minimal critique-result stub carrying the fields the profile consumes."""
    full = {k: 0.0 for k in METRIC_KEYS}
    full.update(errors)
    weights = {k: 1.0 for k in METRIC_KEYS}
    return {
        "medium": medium,
        "alignment_confidence": align,
        "errors": full,
        "weights": weights,
    }


@pytest.fixture
def user(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUTS_DIR", str(tmp_path))
    return "student-a"


class TestProfile:
    def test_consistent_warm_bias_is_high_consistency_weakness(self, user):
        # five critiques all warm to a similar degree
        for _ in range(5):
            record_critique(user, _result({"temp_bias": 0.6}))
        profile = recompute_profile(user)

        temp = profile["metrics"]["temp_bias"]
        assert temp["is_weakness"] is True
        assert temp["consistency"] >= 0.6
        assert temp["signed_mean"] > 0            # warm direction preserved
        # it should be the top-ranked weakness and read as "too warm"
        assert profile["weaknesses"], "expected at least one weakness"
        assert profile["weaknesses"][0]["metric"] == "temp_bias"
        assert "warm" in profile["weaknesses"][0]["direction"]

    def test_scattered_errors_are_not_a_weakness(self, user):
        # chroma error flips sign each time and averages out to ~0
        for i in range(6):
            sign = 1.0 if i % 2 == 0 else -1.0
            record_critique(user, _result({"chroma_bias": 0.6 * sign}))
        profile = recompute_profile(user)

        chroma = profile["metrics"]["chroma_bias"]
        # magnitude is large but it is NOT one-sided → not a habit
        assert chroma["magnitude"] > 0.2
        assert chroma["consistency"] < 0.6
        assert chroma["is_weakness"] is False
        assert all(w["metric"] != "chroma_bias" for w in profile["weaknesses"])

    def test_trend_detects_improvement(self, user):
        # a habit that steadily shrinks over time
        for mag in (0.9, 0.7, 0.5, 0.3, 0.1):
            record_critique(user, _result({"temp_bias": mag}))
        profile = recompute_profile(user)

        temp = profile["metrics"]["temp_bias"]
        assert temp["trend"] == "improving"
        assert temp["trend_slope"] < 0

    def test_trend_detects_worsening(self, user):
        for mag in (0.1, 0.3, 0.5, 0.7, 0.9):
            record_critique(user, _result({"edge_hardness": mag}))
        profile = recompute_profile(user)
        assert profile["metrics"]["edge_hardness"]["trend"] == "worsening"

    def test_per_medium_breakdown(self, user):
        for _ in range(3):
            record_critique(user, _result({"temp_bias": 0.6}, medium="oil"))
        for _ in range(3):
            record_critique(user, _result({"temp_bias": -0.6}, medium="watercolor"))
        profile = recompute_profile(user)

        assert set(profile["by_medium"]) == {"oil", "watercolor"}
        assert profile["by_medium"]["oil"]["temp_bias"]["signed_mean"] > 0
        assert profile["by_medium"]["watercolor"]["temp_bias"]["signed_mean"] < 0

    def test_json_round_trips(self, user):
        for _ in range(4):
            record_critique(user, _result({"temp_bias": 0.5}))
        recompute_profile(user)

        # profile.json + history.jsonl are on disk and valid JSON
        assert _profile_path(user).exists()
        assert _history_path(user).exists()
        on_disk = json.loads(_profile_path(user).read_text())
        loaded = load_profile(user)
        assert loaded == on_disk
        assert loaded["n_critiques"] == 4
        # history is one valid JSON object per line
        lines = [l for l in _history_path(user).read_text().splitlines() if l.strip()]
        assert len(lines) == 4
        assert all(json.loads(l)["errors"]["temp_bias"] == 0.5 for l in lines)

    def test_load_profile_default_when_missing(self, user):
        prof = load_profile("nobody")
        assert prof["n_critiques"] == 0
        assert prof["weaknesses"] == []

    def test_low_alignment_confidence_still_records(self, user):
        for _ in range(4):
            record_critique(user, _result({"temp_bias": 0.6}, align=0.0))
        profile = recompute_profile(user)
        # resize-only critiques (align=0) still contribute via the floor
        assert profile["metrics"]["temp_bias"]["count"] == 4
        assert profile["metrics"]["temp_bias"]["is_weakness"] is True
