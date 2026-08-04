"""
Prioritised progress critique — turn the flat bag of findings into ONE clearly
ranked correction the student should make next.

Components are compared *independently* (placement, proportion/silhouette, value
family, colour/temperature, edges) and ordered so a structural mistake — where
things sit and how big they are — is fixed before value, colour before detail.
The single most important correction becomes ``priority``; the rest become an
ordered ``secondary`` list the UI can collapse.

Geometry is measured in the analysis-pixel grid shared by regions.json /
drawing.json, expressed as [0,1] fractions of the frame so it is resolution
independent. All strings are plain painting language — no CV jargon.
"""
from __future__ import annotations

import numpy as np

try:  # cv2 is always present in this backend, but keep the import defensive
    import cv2
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore


# Alignment must be at least this trustworthy before we dare assert a
# *structural* (placement / proportion) error — otherwise the shapes we compare
# might just be mis-registered, and we fall back to value/colour.
MIN_ALIGN_FOR_STRUCTURE = 0.35

# Component ordering: lower rank is fixed first.
_RANK = {
    "placement":  0,
    "proportion": 1,
    "value":      2,
    "colour":     3,
    "edges":      4,
}

# A candidate correction is only worth surfacing above these severities.
_MIN_SEVERITY = {
    "placement":  0.18,
    "proportion": 0.18,
    "value":      0.15,
    "colour":     0.15,
    "edges":      0.22,
}

_ALL_GOOD = ("Values, colour and structure all track the reference well — "
             "push the focal point further.")

_STRUCTURE_UNCERTAIN_NOTE = (
    " (The photo and the reference didn't line up clearly enough to judge "
    "placement or proportion this time — focus on value and colour for now.)"
)


# ── geometry helpers ─────────────────────────────────────────────────────────
def _ref_bounds_from_drawing(drawing: dict | None) -> dict | None:
    """Reference subject bounds as [0,1] fractions, taken from drawing.json's
    ``subject_bounds`` when it is a real mask (not the whole frame) and
    reasonably confident. Returns None when unusable."""
    if not drawing:
        return None
    sb = drawing.get("subject_bounds") or {}
    iw = drawing.get("image_width")
    ih = drawing.get("image_height")
    if not iw or not ih:
        return None
    if sb.get("source") == "whole_frame":
        return None
    if float(sb.get("confidence", 0.0)) < 0.3:
        return None
    try:
        x0 = float(sb["x_min"]) / (iw - 1)
        y0 = float(sb["y_min"]) / (ih - 1)
        x1 = float(sb["x_max"]) / (iw - 1)
        y1 = float(sb["y_max"]) / (ih - 1)
    except (KeyError, TypeError, ZeroDivisionError):
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x_min": x0, "y_min": y0, "x_max": x1, "y_max": y1}


def _detect_foreground_bounds(rgb: np.ndarray) -> dict | None:
    """Estimate the subject's bounding box as [0,1] fractions by finding where
    the picture departs from its border/background colour. Returns None when the
    subject fills (or is absent from) the whole frame — nothing to say then."""
    if cv2 is None:
        return None
    h, w = rgb.shape[:2]
    img = rgb.astype(np.float32)
    b = max(2, min(h, w) // 40)
    border = np.concatenate([
        img[:b].reshape(-1, 3), img[-b:].reshape(-1, 3),
        img[:, :b].reshape(-1, 3), img[:, -b:].reshape(-1, 3),
    ])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((img - bg) ** 2).sum(axis=2))
    d8 = np.clip(dist, 0, 255).astype(np.uint8)
    _, mask = cv2.threshold(d8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if not bool((mask > 0).any()):
        return None
    # The subject is the dominant blob; ignore scattered background clutter by
    # keeping only the largest connected foreground region.
    n_lbl, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    if n_lbl <= 1:
        return None
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    frac = float(stats[biggest, cv2.CC_STAT_AREA]) / float(h * w)
    if frac < 0.004 or frac > 0.97:
        return None
    ys, xs = np.where(labels == biggest)
    x0 = float(np.percentile(xs, 1)) / (w - 1)
    x1 = float(np.percentile(xs, 99)) / (w - 1)
    y0 = float(np.percentile(ys, 1)) / (h - 1)
    y1 = float(np.percentile(ys, 99)) / (h - 1)
    if x1 <= x0 or y1 <= y0:
        return None
    return {"x_min": x0, "y_min": y0, "x_max": x1, "y_max": y1}


def _dims(b: dict) -> tuple[float, float, float, float]:
    """(width, height, centre_x, centre_y) of a normalised bounds dict."""
    w = b["x_max"] - b["x_min"]
    h = b["y_max"] - b["y_min"]
    cx = 0.5 * (b["x_min"] + b["x_max"])
    cy = 0.5 * (b["y_min"] + b["y_max"])
    return w, h, cx, cy


def _placement_candidate(ref_b: dict, att_b: dict) -> dict | None:
    """Is the whole subject shifted, or drawn too large/small, vs the reference?"""
    rw, rh, rcx, rcy = _dims(ref_b)
    aw, ah, acx, acy = _dims(att_b)
    dx, dy = acx - rcx, acy - rcy
    shift = float(np.hypot(dx, dy))
    sev_shift = float(np.clip(shift / 0.22, 0.0, 1.0))

    size_ratio = (aw * ah) / max(rw * rh, 1e-6)
    sev_size = float(np.clip(abs(np.log(max(size_ratio, 1e-6))) / np.log(1.6), 0.0, 1.0))

    if sev_shift >= sev_size:
        if abs(dx) >= abs(dy):
            where = "right" if dx > 0 else "left"
        else:
            where = "down the frame" if dy > 0 else "up the frame"
        toward = {
            "right": "left", "left": "right",
            "down the frame": "higher", "up the frame": "lower",
        }[where]
        msg = (f"Your subject sits too far {where} — move the whole shape "
               f"{toward} to match the reference before refining anything else.")
        severity = sev_shift
    else:
        too_big = size_ratio > 1.0
        msg = ("Your subject is drawn too large for the frame — shrink the whole "
               "shape to match the reference's placement before adding detail."
               if too_big else
               "Your subject is drawn too small for the frame — enlarge the whole "
               "shape to match the reference's placement before adding detail.")
        severity = sev_size

    return {"component": "placement", "severity": round(severity, 3), "message": msg}


def _proportion_candidate(ref_b: dict, att_b: dict) -> dict | None:
    """Is the subject too narrow/wide (or tall/short) vs the reference silhouette?"""
    rw, rh, _, _ = _dims(ref_b)
    aw, ah, _, _ = _dims(att_b)
    ref_aspect = rh / max(rw, 1e-6)
    att_aspect = ah / max(aw, 1e-6)
    ratio = att_aspect / max(ref_aspect, 1e-6)
    severity = float(np.clip(abs(np.log(max(ratio, 1e-6))) / np.log(1.35), 0.0, 1.0))
    if ratio > 1.0:
        msg = ("The subject is too narrow — widen the outer silhouette to match "
               "the reference before adjusting colour or detail.")
    else:
        msg = ("The subject is too wide — narrow the outer silhouette to match "
               "the reference before adjusting colour or detail.")
    return {"component": "proportion", "severity": round(severity, 3), "message": msg}


# ── value / colour / edge candidates from already-computed data ──────────────
def _value_candidate(
    ref_bands: np.ndarray,
    att_bands: np.ndarray,
    ref_gray: np.ndarray,
    value_score: float,
    value_compression: float,
) -> dict | None:
    severity = float(np.clip((100.0 - value_score) / 45.0, 0.0, 1.0))

    # shadow family = darkest third of the reference; is it reading too light/dark?
    lo = float(np.percentile(ref_gray, 33))
    shadow = ref_gray <= lo
    shadow_err = float(np.mean(att_bands[shadow] - ref_bands[shadow])) if bool(shadow.any()) else 0.0

    if abs(shadow_err) >= 0.4:
        if shadow_err > 0:
            msg = ("Your darkest areas are reading too light — deepen the shadow "
                   "family so the picture keeps its full range.")
        else:
            msg = ("Your darkest areas are reading too dark — lift the shadows a "
                   "little so they don't block up.")
        severity = max(severity, float(np.clip(abs(shadow_err) / 2.0, 0.0, 1.0)))
    elif value_compression > 0.25:
        msg = ("Your values are too close together — push the darks darker and "
               "the lights lighter to open up the range.")
        severity = max(severity, float(np.clip(value_compression, 0.0, 1.0)))
    else:
        msg = ("Some areas are off in value compared to the reference — match the "
               "big light and dark shapes before anything else.")

    return {"component": "value", "severity": round(severity, 3), "message": msg}


def _colour_candidate(errors: dict) -> dict | None:
    options = {
        "temp_bias":         errors.get("temp_bias", 0.0),
        "chroma_bias":       errors.get("chroma_bias", 0.0),
        "temp_light_shadow": errors.get("temp_light_shadow", 0.0),
        "hue_error":         errors.get("hue_error", 0.0),
    }
    key = max(options, key=lambda k: abs(options[k]))
    val = options[key]
    severity = float(np.clip(abs(val), 0.0, 1.0))

    if key == "temp_bias":
        msg = ("The whole picture leans too warm — cool it overall, especially in "
               "the shadows." if val > 0 else
               "The whole picture leans too cool — warm it overall, especially in "
               "the lit areas.")
    elif key == "chroma_bias":
        msg = ("Your colours are more intense than the reference — knock them back "
               "toward a matching grey." if val > 0 else
               "Your colours are greyer than the reference — mix them a little "
               "purer.")
    elif key == "temp_light_shadow":
        msg = ("Your lights and shadows are too similar in temperature — keep the "
               "lights warmer and the shadows cooler.")
    else:  # hue_error
        msg = ("Your colours have drifted in hue from the reference — re-check your "
               "mixtures against it.")

    return {"component": "colour", "severity": round(severity, 3), "message": msg}


def _edge_candidate(errors: dict) -> dict | None:
    val = errors.get("edge_hardness", 0.0)
    severity = float(np.clip(abs(val), 0.0, 1.0))
    msg = ("Your edges are too crisp — soften the transitions away from the focal "
           "point." if val > 0 else
           "Your edges are too soft — sharpen the key edges at the focal point.")
    return {"component": "edges", "severity": round(severity, 3), "message": msg}


# ── orchestration ────────────────────────────────────────────────────────────
def build_priority(
    *,
    ref_rgb: np.ndarray,
    att_rgb: np.ndarray,
    ref_gray: np.ndarray,
    ref_bands: np.ndarray,
    att_bands: np.ndarray,
    alignment_confidence: float,
    value_score: float,
    colour_score: float,
    errors: dict,
    drawing: dict | None,
) -> tuple[dict, list[dict]]:
    """Return (priority, secondary).

    ``priority`` is one {component, severity, message}. ``secondary`` is the
    remaining corrections, ordered structure → value → colour → edges.
    """
    structure_ok = alignment_confidence >= MIN_ALIGN_FOR_STRUCTURE

    candidates: list[dict] = []

    # Structural comparison only when the alignment is trustworthy.
    if structure_ok:
        ref_b = _ref_bounds_from_drawing(drawing) or _detect_foreground_bounds(ref_rgb)
        att_b = _detect_foreground_bounds(att_rgb)
        if ref_b is not None and att_b is not None:
            for cand in (_placement_candidate(ref_b, att_b),
                         _proportion_candidate(ref_b, att_b)):
                if cand and cand["severity"] >= _MIN_SEVERITY[cand["component"]]:
                    candidates.append(cand)

    val_c = _value_candidate(
        ref_bands, att_bands, ref_gray, value_score,
        float(errors.get("value_compression", 0.0)),
    )
    if val_c and val_c["severity"] >= _MIN_SEVERITY["value"]:
        candidates.append(val_c)

    col_c = _colour_candidate(errors)
    if col_c and col_c["severity"] >= _MIN_SEVERITY["colour"]:
        candidates.append(col_c)

    edge_c = _edge_candidate(errors)
    if edge_c and edge_c["severity"] >= _MIN_SEVERITY["edges"]:
        candidates.append(edge_c)

    # Order: component rank first, then severity within a component.
    candidates.sort(key=lambda c: (_RANK[c["component"]], -c["severity"]))

    if not candidates:
        priority = {"component": "overall", "severity": 0.0, "message": _ALL_GOOD}
        return priority, []

    priority = dict(candidates[0])
    secondary = [dict(c) for c in candidates[1:5]]

    # Honest about uncertainty: if alignment was poor we could not judge
    # structure — say so on the correction we DID surface.
    if not structure_ok and priority["component"] in ("value", "colour", "edges"):
        priority["message"] = priority["message"] + _STRUCTURE_UNCERTAIN_NOTE
        priority["structure_checked"] = False

    return priority, secondary
