"""
Critique engine — compares a student's painting attempt against the reference
photo and produces specific, localised, actionable feedback.

Deterministic CV only (no ML downloads): value-band comparison, LAB colour
temperature/saturation comparison, and edge-density (structure) comparison,
all on an aligned grid so every finding names a *place* in the picture. An
optional Claude vision narrative is layered on top when ANTHROPIC_API_KEY is
configured (same graceful-degradation contract as teaching/observations.py).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# Analysis grid — coarse enough that a cell is a paintable "area", fine
# enough to localise a mistake. 4x4 keeps messages human ("upper left").
GRID = 4

# A cell must deviate by at least this many value bands (out of n_bands-1)
# before we call it a mistake — painting is not photocopying.
VALUE_BAND_TOLERANCE = 0.6

# LAB b*-channel mean shift (warm/cool) per cell before we flag temperature.
TEMPERATURE_TOLERANCE = 9.0

# LAB chroma mean shift per cell before we flag saturation.
CHROMA_TOLERANCE = 12.0

# Relative edge-density difference before we flag structure.
EDGE_DENSITY_TOLERANCE = 0.5
# Cells with almost no reference edges can't produce meaningful structure
# feedback (density ratios explode) — require some real structure first.
EDGE_MIN_REFERENCE_DENSITY = 0.02

_COL_NAMES = ["left", "centre-left", "centre-right", "right"]
_ROW_NAMES = ["top", "upper", "lower", "bottom"]


def _cell_name(row: int, col: int) -> str:
    return f"{_ROW_NAMES[row]} {_COL_NAMES[col]}"


def _load_rgb(path: str | Path, size: tuple[int, int] | None = None) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    if size is not None and img.size != size:
        img = img.resize(size, Image.LANCZOS)
    return np.asarray(img)


def _value_bands(gray: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """Quantize a grayscale image into bands using precomputed thresholds."""
    return np.digitize(gray, thresholds).astype(np.int16)


def _cell_means(arr: np.ndarray) -> np.ndarray:
    """Mean of `arr` over each cell of the GRID x GRID partition."""
    h, w = arr.shape[:2]
    out = np.zeros((GRID, GRID), dtype=np.float64)
    for r in range(GRID):
        for c in range(GRID):
            ys = slice(r * h // GRID, (r + 1) * h // GRID)
            xs = slice(c * w // GRID, (c + 1) * w // GRID)
            out[r, c] = float(np.mean(arr[ys, xs]))
    return out


def _cell_centre(row: int, col: int) -> tuple[float, float]:
    """Normalised (cx, cy) of a grid cell centre, in [0,1]."""
    return ((col + 0.5) / GRID, (row + 0.5) / GRID)


def _align_attempt(ref: np.ndarray, att: np.ndarray) -> tuple[np.ndarray, bool]:
    """
    Photos of a painting are rarely taken square-on; a perspective-skewed
    attempt shifts every grid cell and the localised feedback blames the
    wrong areas. ORB features + RANSAC homography warp the attempt onto the
    reference frame when enough reliable matches exist; otherwise the
    resized attempt is used as-is. Returns (aligned_attempt, was_aligned).
    """
    H, W = ref.shape[:2]
    try:
        orb = cv2.ORB_create(nfeatures=3000)
        g_ref = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY)
        g_att = cv2.cvtColor(att, cv2.COLOR_RGB2GRAY)
        k1, d1 = orb.detectAndCompute(g_ref, None)
        k2, d2 = orb.detectAndCompute(g_att, None)
        if d1 is None or d2 is None or len(k1) < 30 or len(k2) < 30:
            return att, False

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(matcher.match(d2, d1), key=lambda m: m.distance)[:400]
        if len(matches) < 25:
            return att, False

        src = np.float32([k2[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst = np.float32([k1[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        M, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if M is None or inliers is None or int(inliers.sum()) < 20:
            return att, False

        # sanity: reject degenerate/extreme warps
        det = float(np.linalg.det(M[:2, :2]))
        if not (0.25 < abs(det) < 4.0):
            return att, False

        warped = cv2.warpPerspective(att, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
        return warped, True
    except Exception:
        log.warning("attempt alignment failed; comparing unaligned", exc_info=True)
        return att, False


def critique_attempt(
    reference_path: str | Path,
    attempt_path: str | Path,
    out_dir: str | Path,
    n_value_bands: int = 5,
    medium: str = "oil",
) -> dict:
    """
    Compare a student attempt against the reference and write:
      - critique_overlay.png  (value-error heatmap + circles on worst areas)
      - side_by_side.png      (attempt | reference)
    Returns a JSON-safe dict with per-dimension scores (0-100), localised
    feedback items, and the output asset paths (absolute).
    """
    t0 = time.perf_counter()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ref = _load_rgb(reference_path)
    h, w = ref.shape[:2]
    att = _load_rgb(attempt_path, size=(w, h))
    att, aligned = _align_attempt(ref, att)

    ref_gray = cv2.GaussianBlur(cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY), (5, 5), 0)
    att_gray = cv2.GaussianBlur(cv2.cvtColor(att, cv2.COLOR_RGB2GRAY), (5, 5), 0)

    feedback: list[dict] = []

    # ── 1. Values — the reference's own percentiles define the bands, so the
    #      comparison is about *relationships*, not absolute exposure ─────────
    qs = np.linspace(0, 100, n_value_bands + 1)[1:-1]
    thresholds = np.percentile(ref_gray, qs)
    ref_bands = _value_bands(ref_gray, thresholds)
    att_bands = _value_bands(att_gray, thresholds)

    band_diff = att_bands.astype(np.float64) - ref_bands.astype(np.float64)
    cell_value_err = _cell_means(band_diff)          # signed: + = too light
    cell_value_abs = _cell_means(np.abs(band_diff))  # magnitude

    for r in range(GRID):
        for c in range(GRID):
            err = cell_value_err[r, c]
            if abs(err) < VALUE_BAND_TOLERANCE:
                continue
            direction = "too light" if err > 0 else "too dark"
            fix = (
                "glaze or scumble a darker mixture over it — squint at the reference until the area merges with its neighbours"
                if err > 0 else
                "lift it with a lighter value — mix up, don't just add white, or the colour will go chalky"
            )
            cx, cy = _cell_centre(r, c)
            feedback.append({
                "kind":     "value",
                "area":     _cell_name(r, c),
                "cx": cx, "cy": cy, "r": 0.5 / GRID,
                "severity": round(min(abs(err) / (n_value_bands - 1) * 2, 1.0), 2),
                "message":  f"The {_cell_name(r, c)} area is {direction} by about "
                            f"{abs(err):.1f} value band{'s' if abs(err) >= 1.5 else ''} compared to the reference.",
                "tip":      fix,
            })

    value_score = float(np.clip(100 * (1 - np.mean(np.abs(band_diff)) / (n_value_bands - 1) * 2), 0, 100))

    # ── 2. Colour — LAB temperature (b*) and chroma per cell ────────────────
    ref_lab = cv2.cvtColor(ref, cv2.COLOR_RGB2LAB).astype(np.float64)
    att_lab = cv2.cvtColor(att, cv2.COLOR_RGB2LAB).astype(np.float64)

    temp_diff = _cell_means(att_lab[..., 2] - ref_lab[..., 2])  # b*: + = warmer
    ref_chroma = np.hypot(ref_lab[..., 1] - 128, ref_lab[..., 2] - 128)
    att_chroma = np.hypot(att_lab[..., 1] - 128, att_lab[..., 2] - 128)
    chroma_diff = _cell_means(att_chroma - ref_chroma)          # + = more saturated

    for r in range(GRID):
        for c in range(GRID):
            cx, cy = _cell_centre(r, c)
            t = temp_diff[r, c]
            if abs(t) >= TEMPERATURE_TOLERANCE:
                warm = t > 0
                feedback.append({
                    "kind":     "temperature",
                    "area":     _cell_name(r, c),
                    "cx": cx, "cy": cy, "r": 0.5 / GRID,
                    "severity": round(min(abs(t) / 30, 1.0), 2),
                    "message":  f"The {_cell_name(r, c)} area reads {'warmer' if warm else 'cooler'} than the reference.",
                    "tip":      ("Cool it with a touch of its complement or a blue-grey — shadows especially should lean cool."
                                 if warm else
                                 "Warm it slightly — lit areas usually want a touch of yellow/orange, not more white."),
                })
            s = chroma_diff[r, c]
            if abs(s) >= CHROMA_TOLERANCE:
                over = s > 0
                feedback.append({
                    "kind":     "saturation",
                    "area":     _cell_name(r, c),
                    "cx": cx, "cy": cy, "r": 0.5 / GRID,
                    "severity": round(min(abs(s) / 40, 1.0), 2),
                    "message":  f"Colour in the {_cell_name(r, c)} area is "
                                f"{'more intense' if over else 'greyer'} than the reference.",
                    "tip":      ("Neutralise with a grey of the same value — straight-from-the-tube colour rarely exists in nature."
                                 if over else
                                 "Push the chroma a little — mix in the pure pigment rather than adding more layers."),
                })

    colour_score = float(np.clip(
        100 - (np.mean(np.abs(temp_diff)) / TEMPERATURE_TOLERANCE * 25
               + np.mean(np.abs(chroma_diff)) / CHROMA_TOLERANCE * 25),
        0, 100,
    ))

    # ── 3. Structure — edge density per cell (composition drift) ────────────
    scale = 512 / max(h, w)
    small = (max(int(w * scale), 32), max(int(h * scale), 32))
    ref_edges = cv2.Canny(cv2.resize(ref_gray, small), 60, 140) / 255.0
    att_edges = cv2.Canny(cv2.resize(att_gray, small), 60, 140) / 255.0
    ref_density = _cell_means(ref_edges)
    att_density = _cell_means(att_edges)

    structure_flags = 0
    for r in range(GRID):
        for c in range(GRID):
            rd, ad = ref_density[r, c], att_density[r, c]
            if rd < EDGE_MIN_REFERENCE_DENSITY:
                continue
            rel = (ad - rd) / rd
            if abs(rel) < EDGE_DENSITY_TOLERANCE:
                continue
            structure_flags += 1
            cx, cy = _cell_centre(r, c)
            over = rel > 0
            feedback.append({
                "kind":     "structure",
                "area":     _cell_name(r, c),
                "cx": cx, "cy": cy, "r": 0.5 / GRID,
                "severity": round(min(abs(rel), 1.0), 2),
                "message":  (f"The {_cell_name(r, c)} area looks overworked — more edges and detail than the reference has."
                             if over else
                             f"Structure is missing in the {_cell_name(r, c)} area — key edges from the reference aren't there yet."),
                "tip":      ("Soften or paint over the busiest passages; keep detail for the focal point only."
                             if over else
                             "Re-check the drawing before adding more paint — compare the big shapes against the outline guide."),
            })

    denom = max(int(np.sum(ref_density >= EDGE_MIN_REFERENCE_DENSITY)), 1)
    structure_score = float(np.clip(100 * (1 - structure_flags / denom), 0, 100))

    overall = round(0.45 * value_score + 0.3 * colour_score + 0.25 * structure_score, 1)

    # Rank worst-first; the student should fix values before colour.
    _KIND_PRIORITY = {"value": 0, "structure": 1, "temperature": 2, "saturation": 3}
    feedback.sort(key=lambda f: (_KIND_PRIORITY.get(f["kind"], 9), -f["severity"]))

    # ── Visual outputs ───────────────────────────────────────────────────────
    overlay_path = out_dir / "critique_overlay.png"
    _write_overlay(att, np.abs(band_diff) / max(n_value_bands - 1, 1), feedback, overlay_path)

    side_path = out_dir / "side_by_side.png"
    side = np.concatenate([att, ref], axis=1)
    Image.fromarray(side).save(side_path)

    return {
        "scores": {
            "overall":   overall,
            "values":    round(value_score, 1),
            "colour":    round(colour_score, 1),
            "structure": round(structure_score, 1),
        },
        "feedback": feedback,
        "first_fix": feedback[0]["message"] if feedback else
                     "Values, colour and structure all track the reference well — push the focal point further.",
        "assets": {
            "overlay":      str(overlay_path),
            "side_by_side": str(side_path),
        },
        "medium": medium,
        "n_value_bands": n_value_bands,
        "aligned": aligned,
        "elapsed_sec": round(time.perf_counter() - t0, 2),
    }


def _write_overlay(attempt: np.ndarray, err01: np.ndarray, feedback: list[dict], path: Path) -> None:
    """Heat-tint the attempt where values are wrong and circle the worst areas."""
    h, w = attempt.shape[:2]
    err = np.clip(err01, 0, 1)[..., None]
    # Warm amber → crimson tint, matching the app's palette
    heat = np.array([220, 100, 60], dtype=np.float64)[None, None, :]
    blended = attempt.astype(np.float64) * (1 - 0.55 * err) + heat * (0.55 * err)
    out = blended.astype(np.uint8).copy()

    for f in feedback[:6]:
        if f["kind"] != "value":
            continue
        centre = (int(f["cx"] * w), int(f["cy"] * h))
        radius = int(f["r"] * min(w, h) * 0.9)
        cv2.circle(out, centre, radius, (242, 192, 120), thickness=max(2, w // 400))

    Image.fromarray(out).save(path)


def save_critique(result: dict, out_dir: str | Path) -> Path:
    """Persist the critique JSON next to its images; returns the JSON path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "critique.json"
    path.write_text(json.dumps(result, indent=2))
    return path
