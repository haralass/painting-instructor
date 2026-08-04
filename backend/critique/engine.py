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


def _orb_align(ref: np.ndarray, att: np.ndarray) -> tuple[np.ndarray, bool, float]:
    """
    ORB features + RANSAC homography warp the attempt onto the reference frame
    when enough reliable matches exist. Returns (warped, ok, confidence) where
    confidence is the RANSAC inlier fraction in [0,1].
    """
    H, W = ref.shape[:2]
    try:
        orb = cv2.ORB_create(nfeatures=3000)
        g_ref = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY)
        g_att = cv2.cvtColor(att, cv2.COLOR_RGB2GRAY)
        k1, d1 = orb.detectAndCompute(g_ref, None)
        k2, d2 = orb.detectAndCompute(g_att, None)
        if d1 is None or d2 is None or len(k1) < 30 or len(k2) < 30:
            return att, False, 0.0

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(matcher.match(d2, d1), key=lambda m: m.distance)[:400]
        if len(matches) < 25:
            return att, False, 0.0

        src = np.float32([k2[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst = np.float32([k1[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
        M, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        if M is None or inliers is None or int(inliers.sum()) < 20:
            return att, False, 0.0

        # sanity: reject degenerate/extreme warps
        det = float(np.linalg.det(M[:2, :2]))
        if not (0.25 < abs(det) < 4.0):
            return att, False, 0.0

        conf = float(np.clip(int(inliers.sum()) / max(len(matches), 1), 0.0, 1.0))
        warped = cv2.warpPerspective(att, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
        return warped, True, conf
    except Exception:
        log.warning("ORB alignment failed; comparing unaligned", exc_info=True)
        return att, False, 0.0


def _align_attempt(ref: np.ndarray, att: np.ndarray) -> tuple[np.ndarray, bool]:
    """Back-compatible wrapper: returns (aligned_attempt, was_aligned)."""
    warped, ok, _ = _orb_align(ref, att)
    return warped, ok


def _order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    pts = pts.astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.float32([
        pts[np.argmin(s)],   # tl: smallest x+y
        pts[np.argmin(d)],   # tr: smallest y-x
        pts[np.argmax(s)],   # br: largest x+y
        pts[np.argmax(d)],   # bl: largest y-x
    ])


def _canvas_rectify(att: np.ndarray, ref_shape: tuple[int, int]) -> tuple[np.ndarray | None, float]:
    """
    Detect the canvas as the largest near-full-frame convex 4-point quad
    (Canny -> findContours -> approxPolyDP) and warp it square-on onto the
    reference frame with getPerspectiveTransform/warpPerspective. Conservative:
    only accepts a quad that covers most of the frame, so it never fires on
    interior shapes. Returns (warped or None, confidence).
    """
    H, W = ref_shape[:2]
    try:
        ah, aw = att.shape[:2]
        img_area = float(ah * aw)
        g = cv2.GaussianBlur(cv2.cvtColor(att, cv2.COLOR_RGB2GRAY), (5, 5), 0)
        edges = cv2.Canny(g, 50, 150)
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best, best_area = None, 0.0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 0.55 * img_area:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) != 4 or not cv2.isContourConvex(approx):
                continue
            if area > best_area:
                best, best_area = approx, area
        if best is None:
            return None, 0.0
        pts = best.reshape(4, 2).astype(np.float32)
        xs, ys = pts[:, 0], pts[:, 1]
        # require the quad to span most of the frame in both axes
        if (xs.max() - xs.min()) < 0.7 * aw or (ys.max() - ys.min()) < 0.7 * ah:
            return None, 0.0
        src = _order_quad(pts)
        dst = np.float32([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]])
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(att, M, (W, H), borderMode=cv2.BORDER_REPLICATE)
        conf = float(np.clip(best_area / img_area, 0.0, 1.0))
        return warped, conf
    except Exception:
        log.warning("canvas rectify failed; falling back", exc_info=True)
        return None, 0.0


def _align_attempt_ex(ref: np.ndarray, att: np.ndarray) -> tuple[np.ndarray, str, float]:
    """
    Alignment with a fallback chain: canvas-quad rectify -> ORB homography ->
    resize-only. Returns (aligned_attempt, method, confidence).
    """
    warped, conf = _canvas_rectify(att, ref.shape)
    if warped is not None:
        return warped, "canvas_quad", round(conf, 3)
    warped, ok, conf = _orb_align(ref, att)
    if ok:
        return warped, "orb_homography", round(conf, 3)
    return att, "resize", 0.0


# Named metric keys, in the order the profile ranks them.
METRIC_KEYS = (
    "value_compression",   # + attempt's value range is compressed (too flat)
    "temp_bias",           # + attempt globally too warm, - too cool
    "temp_light_shadow",   # + attempt under-separates (lights not warm / shadows not cool)
    "hue_error",           # signed net hue rotation of the attempt vs reference
    "chroma_bias",         # + attempt globally oversaturated, - undersaturated
    "edge_hardness",       # + attempt's focal edges too hard, - too soft
)


def _primary_edge_mask(edges_path: str | Path | None, shape: tuple[int, int]) -> np.ndarray | None:
    """Rasterise primary/decorative (focal) edges from an edges.json into a mask."""
    try:
        data = json.loads(Path(edges_path).read_text())
    except Exception:
        return None
    h, w = shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    drawn = 0
    for e in data:
        if e.get("type") not in ("primary", "decorative"):
            continue
        pts = e.get("path") or []
        if len(pts) < 2:
            continue
        arr = np.array(pts, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(mask, [arr], False, 255, thickness=3)
        drawn += 1
    if drawn == 0:
        return None
    return mask > 0


def _signed_metrics(
    ref_gray: np.ndarray,
    att_gray: np.ndarray,
    ref_lab: np.ndarray,
    att_lab: np.ndarray,
    ref_chroma: np.ndarray,
    att_chroma: np.ndarray,
    edges_path: str | Path | None,
) -> tuple[dict, dict]:
    """
    Compute the signed diagnostic error vector + per-metric confidence weights.
    LAB channels follow OpenCV's convention (L,a,b in 0..255; a,b centred 128).
    Colour metrics are measured after a white-balance/exposure normalisation
    that removes the *global* cast only (local relationships are preserved).
    """
    eps = 1e-6
    errors: dict[str, float] = {}
    weights: dict[str, float] = {}

    ref_L = ref_lab[..., 0]
    att_L = att_lab[..., 0]
    ref_b = ref_lab[..., 2]
    att_b = att_lab[..., 2]

    # colour confidence scales with how much chroma the reference actually has
    colour_w = float(np.clip(np.mean(ref_chroma) / 20.0, 0.0, 1.0))

    # value_compression: p5–p95 L* range, + = attempt flatter than reference
    ref_rng = float(np.percentile(ref_L, 95) - np.percentile(ref_L, 5))
    att_rng = float(np.percentile(att_L, 95) - np.percentile(att_L, 5))
    errors["value_compression"] = float(np.clip((ref_rng - att_rng) / (ref_rng + eps), -1.0, 1.0))
    weights["value_compression"] = 1.0

    # temp_bias: the global b* cast that normalisation removes. + = warmer.
    temp_bias_raw = float(np.mean(att_b) - np.mean(ref_b))
    errors["temp_bias"] = float(np.clip(temp_bias_raw / 30.0, -1.0, 1.0))
    weights["temp_bias"] = colour_w

    # chroma_bias: global over/under-saturation. + = more saturated.
    chroma_bias_raw = float(np.mean(att_chroma) - np.mean(ref_chroma))
    errors["chroma_bias"] = float(np.clip(chroma_bias_raw / 40.0, -1.0, 1.0))
    weights["chroma_bias"] = colour_w

    # ── normalise the attempt to the reference (remove global cast only) ──────
    att_lab_n = att_lab.copy()
    try:
        from skimage.exposure import match_histograms
        att_lab_n[..., 0] = match_histograms(att_L, ref_L)
    except Exception:
        pass
    att_lab_n[..., 1] = att_lab_n[..., 1] - (np.mean(att_lab[..., 1]) - np.mean(ref_lab[..., 1]))
    att_lab_n[..., 2] = att_lab_n[..., 2] - (np.mean(att_lab[..., 2]) - np.mean(ref_lab[..., 2]))

    # temp_light_shadow: lights-warm / shadows-cool separation, measured after
    # cast removal. + = attempt UNDER-separates vs the reference (common habit).
    lo, hi = np.percentile(ref_L, [33, 66])
    shadow = ref_L <= lo
    light = ref_L >= hi

    def _mmean(img, mask):
        return float(np.mean(img[mask])) if bool(mask.any()) else 0.0

    ref_split = _mmean(ref_b, light) - _mmean(ref_b, shadow)
    att_split = _mmean(att_lab_n[..., 2], light) - _mmean(att_lab_n[..., 2], shadow)
    errors["temp_light_shadow"] = float(np.clip((ref_split - att_split) / 20.0, -1.0, 1.0))
    weights["temp_light_shadow"] = colour_w

    # hue_error: chroma-weighted net hue rotation, after cast removal.
    ref_h = np.arctan2(ref_lab[..., 2] - 128.0, ref_lab[..., 1] - 128.0)
    att_h = np.arctan2(att_lab_n[..., 2] - 128.0, att_lab_n[..., 1] - 128.0)
    dh = np.arctan2(np.sin(att_h - ref_h), np.cos(att_h - ref_h))
    wgt = ref_chroma
    hshift = float(np.sum(dh * wgt) / (np.sum(wgt) + eps))
    errors["hue_error"] = float(np.clip(hshift / np.pi, -1.0, 1.0))
    weights["hue_error"] = colour_w

    # edge_hardness: gradient across the reference's focal edges, attempt vs
    # reference. + = attempt's edges are too hard, - = too soft.
    grad_ref = cv2.magnitude(
        cv2.Sobel(ref_gray, cv2.CV_32F, 1, 0, ksize=3),
        cv2.Sobel(ref_gray, cv2.CV_32F, 0, 1, ksize=3),
    )
    grad_att = cv2.magnitude(
        cv2.Sobel(att_gray, cv2.CV_32F, 1, 0, ksize=3),
        cv2.Sobel(att_gray, cv2.CV_32F, 0, 1, ksize=3),
    )
    band = cv2.dilate(cv2.Canny(ref_gray, 60, 140), np.ones((3, 3), np.uint8), iterations=2) > 0
    focal = _primary_edge_mask(edges_path, ref_gray.shape)
    if focal is not None:
        inter = band & focal
        if int(inter.sum()) >= 50:
            band = inter
    n_band = int(band.sum())
    if n_band >= 25:
        ref_e = float(np.mean(grad_ref[band]))
        att_e = float(np.mean(grad_att[band]))
        ratio = (att_e + eps) / (ref_e + eps)
        errors["edge_hardness"] = float(np.clip(np.tanh(np.log(ratio)), -1.0, 1.0))
        weights["edge_hardness"] = float(np.clip(ref_e / 50.0, 0.0, 1.0))
    else:
        errors["edge_hardness"] = 0.0
        weights["edge_hardness"] = 0.0

    errors = {k: round(errors[k], 4) for k in METRIC_KEYS}
    weights = {k: round(weights[k], 4) for k in METRIC_KEYS}
    return errors, weights


def critique_attempt(
    reference_path: str | Path,
    attempt_path: str | Path,
    out_dir: str | Path,
    n_value_bands: int = 5,
    medium: str = "oil",
    edges_path: str | Path | None = None,
    drawing: dict | None = None,
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

    # Drawing analysis (subject bounds / silhouette) for structural comparison.
    # The API passes it explicitly; when it doesn't, try to locate it next to
    # the job outputs (works for both the real critique/attempt_N layout and the
    # flat test layout).
    if drawing is None:
        for cand in (out_dir.parent / "drawing.json",
                     out_dir.parent.parent / "drawing.json"):
            if cand.exists():
                try:
                    drawing = json.loads(cand.read_text())
                except Exception:
                    drawing = None
                break

    ref = _load_rgb(reference_path)
    h, w = ref.shape[:2]
    att = _load_rgb(attempt_path, size=(w, h))
    att, alignment_method, alignment_confidence = _align_attempt_ex(ref, att)
    aligned = alignment_method != "resize"

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

    # ── 4. Signed diagnostic metrics (additive) ─────────────────────────────
    #   Every metric is a signed error in ~[-1, 1] (0 = matches the reference),
    #   a named 0–100 score, and a confidence weight in [0, 1]. These do NOT
    #   change the existing scores/feedback; they feed the adaptive profile.
    if edges_path is None:
        cand = out_dir.parent.parent / "edges.json"
        edges_path = cand if cand.exists() else None
    errors, weights = _signed_metrics(
        ref_gray, att_gray, ref_lab, att_lab, ref_chroma, att_chroma, edges_path,
    )
    metric_scores = {k: round(100.0 * (1.0 - min(abs(v), 1.0)), 1) for k, v in errors.items()}

    overall = round(0.45 * value_score + 0.3 * colour_score + 0.25 * structure_score, 1)

    # Rank worst-first; the student should fix values before colour.
    _KIND_PRIORITY = {"value": 0, "structure": 1, "temperature": 2, "saturation": 3}
    feedback.sort(key=lambda f: (_KIND_PRIORITY.get(f["kind"], 9), -f["severity"]))

    # ── 5. Prioritised correction — ONE thing to fix first, then the rest ────
    #   Components are compared independently (placement/proportion → value →
    #   colour → edges). Structural findings only win when the alignment is
    #   confident enough to trust the geometry.
    from .priority import build_priority
    priority, secondary = build_priority(
        ref_rgb=ref,
        att_rgb=att,
        ref_gray=ref_gray,
        ref_bands=ref_bands,
        att_bands=att_bands,
        alignment_confidence=alignment_confidence,
        value_score=value_score,
        colour_score=colour_score,
        errors=errors,
        drawing=drawing,
    )

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
        "priority": priority,
        "secondary": secondary,
        "first_fix": priority["message"],
        "assets": {
            "overlay":      str(overlay_path),
            "side_by_side": str(side_path),
        },
        "medium": medium,
        "n_value_bands": n_value_bands,
        "aligned": aligned,
        "alignment_method": alignment_method,
        "alignment_confidence": alignment_confidence,
        "errors": errors,
        "weights": weights,
        "metric_scores": metric_scores,
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
