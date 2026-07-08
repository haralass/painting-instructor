"""
Adaptive Painter Profile — a deterministic, no-LLM model of a student's
recurring habits, learned from their critique history.

Every critique contributes a signed error vector (see engine._signed_metrics):
each metric is ~[-1, 1] where 0 means "matched the reference". Over many
critiques a *habit* is a metric whose error is both large (magnitude) and
one-sided (consistency) — e.g. "always paints too warm". A one-off mistake, or
errors that scatter around zero, are not habits and are not surfaced.

Storage is flat JSON under outputs_root():
    outputs/profiles/{user_id}/history.jsonl   append-only, one record/critique
    outputs/profiles/{user_id}/profile.json    recomputed digest
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..utils.paths import outputs_root

# The metrics we track, in a stable order. Mirrors engine.METRIC_KEYS but kept
# local so the profile module has no import-time dependency on the engine.
METRIC_KEYS = (
    "value_compression",
    "temp_bias",
    "temp_light_shadow",
    "hue_error",
    "chroma_bias",
    "edge_hardness",
)

DEFAULT_USER = "local"

# ── Tunables ──────────────────────────────────────────────────────────────────
EWMA_DECAY = 0.3          # weight retained by the running estimate each step
WEAKNESS_MAGNITUDE = 0.2  # a habit must be at least this strong on average
WEAKNESS_CONSISTENCY = 0.6  # …and this one-sided (|signed| / mean_abs)
WEAKNESS_MIN_COUNT = 3    # …seen at least this many times
TREND_WINDOW = 5          # magnitudes considered for the improvement trend
TREND_EPS = 0.02          # |slope| below this reads as "stable"
_EPS = 1e-6


# ── Paths ─────────────────────────────────────────────────────────────────────
def _profile_dir(user_id: str) -> Path:
    return outputs_root() / "profiles" / user_id


def _history_path(user_id: str) -> Path:
    return _profile_dir(user_id) / "history.jsonl"


def _profile_path(user_id: str) -> Path:
    return _profile_dir(user_id) / "profile.json"


# ── Recording ─────────────────────────────────────────────────────────────────
def record_critique(user_id: str | None, result: dict) -> dict:
    """
    Append one critique's signed errors + weights + alignment confidence to the
    user's append-only history. Returns the stored record. Safe to call with a
    result that lacks the new metric fields (records an empty errors map).
    """
    user_id = user_id or DEFAULT_USER
    errors = {k: float(result.get("errors", {}).get(k, 0.0)) for k in METRIC_KEYS} \
        if result.get("errors") else {}
    weights = {k: float(result.get("weights", {}).get(k, 0.0)) for k in METRIC_KEYS} \
        if result.get("weights") else {}
    record = {
        "ts": time.time(),
        "medium": result.get("medium", "oil"),
        "alignment_confidence": float(result.get("alignment_confidence", 0.0) or 0.0),
        "errors": errors,
        "weights": weights,
    }
    path = _history_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def _read_history(user_id: str) -> list[dict]:
    path = _history_path(user_id)
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# ── Analysis primitives ───────────────────────────────────────────────────────
def _effective_conf(rec: dict, metric: str) -> float:
    """Combine per-metric signal weight with alignment confidence into [0,1].

    Alignment confidence is floored so an un-rectified (resize-only) critique
    still contributes, just with less pull than a cleanly aligned one.
    """
    w = float(rec.get("weights", {}).get(metric, 0.0))
    align = float(rec.get("alignment_confidence", 0.0) or 0.0)
    return w * (0.3 + 0.7 * max(0.0, min(align, 1.0)))


def _slope(ys: list[float]) -> float:
    """Least-squares slope of ys against index 0..n-1 (0.0 for <2 points)."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den > _EPS else 0.0


def _metric_stats(records: list[dict], metric: str) -> dict:
    """Confidence-weighted EWMA signed mean + mean-abs magnitude + trend."""
    signed = None          # EWMA of the signed error
    mag_sum = 0.0          # confidence-weighted sum of |error|
    conf_sum = 0.0
    count = 0
    mags: list[float] = []  # per-critique magnitudes, oldest -> newest

    for rec in records:  # history is stored oldest-first (append-only)
        errs = rec.get("errors", {})
        if metric not in errs:
            continue
        x = float(errs[metric])
        conf = _effective_conf(rec, metric)
        count += 1
        mags.append(abs(x))
        # confidence-weighted EWMA: a low-confidence observation moves the
        # running estimate less; decay keeps the estimate biased to recency.
        if signed is None:
            signed = x
        else:
            alpha = (1.0 - EWMA_DECAY) * max(conf, 0.0)
            alpha = max(0.0, min(alpha, 1.0))
            signed = signed + alpha * (x - signed)
        mag_sum += conf * abs(x)
        conf_sum += conf

    if count == 0:
        return {
            "signed_mean": 0.0, "magnitude": 0.0, "consistency": 0.0,
            "count": 0, "trend": "stable", "trend_slope": 0.0,
            "is_weakness": False, "severity": 0.0,
        }

    signed_mean = float(signed if signed is not None else 0.0)
    magnitude = float(mag_sum / conf_sum) if conf_sum > _EPS else float(sum(mags) / count)
    consistency = float(min(abs(signed_mean) / (magnitude + _EPS), 1.0))

    trend_slope = _slope(mags[-TREND_WINDOW:])
    if trend_slope < -TREND_EPS:
        trend = "improving"          # magnitudes shrinking over time
    elif trend_slope > TREND_EPS:
        trend = "worsening"
    else:
        trend = "stable"

    is_weakness = (
        magnitude >= WEAKNESS_MAGNITUDE
        and count >= WEAKNESS_MIN_COUNT
        and consistency >= WEAKNESS_CONSISTENCY
    )
    severity = float(magnitude * consistency)

    return {
        "signed_mean": round(signed_mean, 4),
        "magnitude": round(magnitude, 4),
        "consistency": round(consistency, 4),
        "count": count,
        "trend": trend,
        "trend_slope": round(trend_slope, 5),
        "is_weakness": is_weakness,
        "severity": round(severity, 4),
    }


# ── Recompute + load ──────────────────────────────────────────────────────────
def recompute_profile(user_id: str | None) -> dict:
    """Rebuild and persist the profile digest from the full history."""
    user_id = user_id or DEFAULT_USER
    records = _read_history(user_id)

    metrics = {m: _metric_stats(records, m) for m in METRIC_KEYS}

    weaknesses = [
        {
            "metric": m,
            "signed_mean": s["signed_mean"],
            "magnitude": s["magnitude"],
            "consistency": s["consistency"],
            "trend": s["trend"],
            "severity": s["severity"],
            "direction": _direction(m, s["signed_mean"]),
        }
        for m, s in metrics.items() if s["is_weakness"]
    ]
    weaknesses.sort(key=lambda w: w["severity"], reverse=True)

    by_medium: dict[str, dict] = {}
    for medium in sorted({r.get("medium", "oil") for r in records}):
        subset = [r for r in records if r.get("medium", "oil") == medium]
        by_medium[medium] = {
            m: {
                "signed_mean": _metric_stats(subset, m)["signed_mean"],
                "magnitude": _metric_stats(subset, m)["magnitude"],
                "count": _metric_stats(subset, m)["count"],
            }
            for m in METRIC_KEYS
        }

    profile = {
        "user_id": user_id,
        "n_critiques": len(records),
        "updated_at": time.time(),
        "metrics": metrics,
        "weaknesses": weaknesses,
        "by_medium": by_medium,
        "summary": _summary(weaknesses, len(records)),
    }

    path = _profile_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2))
    return profile


def load_profile(user_id: str | None) -> dict:
    """Load the persisted profile digest, or an empty default if none yet."""
    user_id = user_id or DEFAULT_USER
    path = _profile_path(user_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "user_id": user_id, "n_critiques": 0, "updated_at": None,
        "metrics": {}, "weaknesses": [], "by_medium": {},
        "summary": "No critiques recorded yet.",
    }


# ── Human-readable helpers ────────────────────────────────────────────────────
_DIRECTIONS = {
    "value_compression": ("compresses the value range (not enough dark/light)", "over-extends contrast"),
    "temp_bias": ("paints too warm", "paints too cool"),
    "temp_light_shadow": ("under-separates light/shadow temperature", "over-separates light/shadow temperature"),
    "hue_error": ("shifts hues one way", "shifts hues the other way"),
    "chroma_bias": ("oversaturates", "undersaturates / greys colours"),
    "edge_hardness": ("makes focal edges too hard", "makes focal edges too soft"),
}


def _direction(metric: str, signed_mean: float) -> str:
    pos, neg = _DIRECTIONS.get(metric, ("high", "low"))
    return pos if signed_mean >= 0 else neg


def _summary(weaknesses: list[dict], n: int) -> str:
    if n == 0:
        return "No critiques recorded yet."
    if not weaknesses:
        return f"After {n} critique(s), no consistent habit stands out yet — keep painting."
    top = weaknesses[0]
    return (
        f"After {n} critique(s), the clearest habit is that this painter "
        f"{top['direction']} (metric '{top['metric']}', "
        f"severity {top['severity']:.2f}, trend {top['trend']})."
    )
