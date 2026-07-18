"""
Drawing-construction analysis (Phase 3).

Turns the signals already produced for a job — the U²-Net subject mask, the
merge-tree regions, the classified edge paths, depth planes and value zones —
into a stored, structured account of HOW the drawing is built: bounds,
landmarks, main axis, dominant slopes, a simplified envelope, negative
spaces, proportion references, the refined silhouette and the internal
structural lines, ordered pedagogically (spec §2, not left-to-right).

No new edge detection, no new model. All coordinates are analysis pixels
(the same grid as regions.json), so the Phase-2 viewer rescales everything
onto the untouched original.

Honesty rules (spec §3/§16): edge-cause attribution is a soft distribution
with a confidence, never a hard claim; when the subject can't be isolated we
say so via `SubjectBounds.source` rather than inventing a subject.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np

from ..schemas.drawing import (
    Axis, ConstructionStage, DrawingAnalysis, EdgeCauseEstimate, Envelope,
    Landmark, NegativeSpace, ProportionCheck, SubjectBounds, VectorPath,
)

log = logging.getLogger(__name__)


# ── Subject isolation ─────────────────────────────────────────────────────────

def _subject_mask_binary(
    subj_mask: np.ndarray | None, regions: list, H: int, W: int,
) -> tuple[np.ndarray, str, float]:
    """Return (binary subject mask, source, confidence).

    Prefer the real U²-Net mask. Fall back to the union of high-importance,
    non-border merge-tree regions (an honest "best guess"). Last resort: the
    whole frame, flagged as such so no instruction pretends a subject was
    found."""
    if subj_mask is not None and subj_mask.shape == (H, W):
        m = (subj_mask > 0.5).astype(np.uint8)
        if m.sum() > 0.01 * H * W:
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
            return m, "subject_mask", 0.85

    # Region fallback: coarse regions not touching the border, above-median importance.
    coarse = [r for r in regions if r.scale in ("l1", "l2")]
    if coarse:
        imps = sorted(r.importance for r in coarse)
        med = imps[len(imps) // 2]
        m = np.zeros((H, W), np.uint8)
        used = 0
        for r in coarse:
            x0, y0, x1, y1 = r.bbox
            touches = x0 <= 1 or y0 <= 1 or x1 >= W - 2 or y1 >= H - 2
            if r.importance >= med and not touches:
                m[y0:y1, x0:x1] = 1
                used += 1
        if used and m.sum() > 0.02 * H * W:
            return m, "region_fallback", 0.4

    return np.ones((H, W), np.uint8), "whole_frame", 0.15


def _largest_contour(mask: np.ndarray) -> np.ndarray | None:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    return max(cnts, key=cv2.contourArea).reshape(-1, 2).astype(np.float32)


# ── Small helpers ─────────────────────────────────────────────────────────────

def _nid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _norm(x: float, y: float, W: int, H: int) -> tuple[float, float]:
    return (round(x / W, 5), round(y / H, 5))


def _orientation_deg(p0, p1) -> float:
    ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    return round(ang % 180.0, 1)   # undirected line orientation, 0..180


def _polygon(cnt: np.ndarray) -> list[tuple[float, float]]:
    return [(round(float(x), 1), round(float(y), 1)) for x, y in cnt]


def _min_spacing(points: np.ndarray, d_min: float) -> np.ndarray:
    """Drop points closer than d_min to the previously kept one, so busy
    contours come out with readable, drawable spacing (the user's ask: on
    detailed photos, INCREASE the distances so the outline reads)."""
    if len(points) <= 3:
        return points
    kept = [points[0]]
    for p in points[1:]:
        if math.hypot(p[0] - kept[-1][0], p[1] - kept[-1][1]) >= d_min:
            kept.append(p)
    if len(kept) < 3:
        return points
    return np.array(kept, dtype=points.dtype)


def _busyness(cache) -> float:
    """0..1 — how cluttered the photo is (fraction of strong-gradient pixels).
    Busy photos get MORE simplification so contours stay readable."""
    g = cache.grad
    return float((g > max(1e-6, float(g.mean())) * 1.5).mean())


# Artistic contour levels → (epsilon fraction of perimeter, min spacing
# fraction of max side). Busy photos scale both up (see _busy_mult).
_CONTOUR_LEVELS: dict[str, tuple[float, float]] = {
    "simple":   (0.020, 0.030),
    "standard": (0.008, 0.015),
    "refined":  (0.003, 0.006),
}


def _busy_mult(busy: float) -> float:
    """1.0 for clean photos up to ~2.2 for very cluttered ones."""
    return 1.0 + 2.0 * max(0.0, busy - 0.10)


# ── Main entry point ──────────────────────────────────────────────────────────

def build_drawing_analysis(
    cache,
    regions: list,
    edges: list,
    subj_mask: np.ndarray | None,
    depth_lbl: np.ndarray | None,
    zone_map: np.ndarray | None,
    job_id: str | None = None,
    project_id: str | None = None,
) -> DrawingAnalysis:
    """Build the structured drawing construction for one image."""
    H, W = cache.H, cache.W
    mask, source, conf = _subject_mask_binary(subj_mask, regions, H, W)

    # ── Subject bounds + margins + occupied area ──────────────────────────────
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        xs = np.array([0, W - 1]); ys = np.array([0, H - 1])
    x0, x1 = float(xs.min()), float(xs.max())
    y0, y1 = float(ys.min()), float(ys.max())
    margins = {
        "top": round(y0 / H, 4), "bottom": round((H - y1) / H, 4),
        "left": round(x0 / W, 4), "right": round((W - x1) / W, 4),
    }
    occupied_fraction = round(float(mask.sum()) / (H * W), 4)
    bounds = SubjectBounds(
        x_min=x0, y_min=y0, x_max=x1, y_max=y1, margins=margins,
        occupied_fraction=occupied_fraction, source=source, confidence=conf,
    )

    contour = _largest_contour(mask)
    hull_poly: list[tuple[float, float]] = []
    if contour is not None and len(contour) >= 3:
        hull = cv2.convexHull(contour.astype(np.int32)).reshape(-1, 2).astype(np.float32)
        hull_poly = _polygon(cv2.approxPolyDP(hull.astype(np.int32),
                                              0.01 * cv2.arcLength(hull.astype(np.int32), True),
                                              True).reshape(-1, 2))

    landmarks: list[Landmark] = []
    axes: list[Axis] = []
    order = 0

    def add_landmark(cat, x, y, imp=0.6, c=0.6, vis=1, region_ids=None) -> str:
        nonlocal order
        order += 1
        lm = Landmark(
            id=_nid("lm"), category=cat, x=round(float(x), 1), y=round(float(y), 1),
            normalized=_norm(x, y, W, H), importance=imp, confidence=c,
            visibility_level=vis, lesson_order=order,
            related_region_ids=region_ids or [],
        )
        landmarks.append(lm)
        return lm.id

    # ── 1. The four limits (top/bottom/left/right extreme points) ─────────────
    if len(xs):
        top_x = float(xs[ys.argmin()]); bot_x = float(xs[ys.argmax()])
        left_y = float(ys[xs.argmin()]); right_y = float(ys[xs.argmax()])
        add_landmark("subject_top", top_x, y0, imp=0.9, c=conf, vis=1)
        add_landmark("subject_bottom", bot_x, y1, imp=0.9, c=conf, vis=1)
        add_landmark("subject_left", x0, left_y, imp=0.85, c=conf, vis=1)
        add_landmark("subject_right", x1, right_y, imp=0.85, c=conf, vis=1)

    # ── 2. Widest / narrowest points (row-width scan along the vertical span) ──
    if len(xs):
        rows = np.arange(int(y0), int(y1) + 1)
        widths = []
        for ry in rows:
            row = np.nonzero(mask[ry])[0]
            widths.append((row.max() - row.min()) if row.size else 0)
        widths = np.array(widths)
        if widths.size and widths.max() > 0:
            wy = int(rows[int(widths.argmax())])
            row = np.nonzero(mask[wy])[0]
            add_landmark("widest_point", (row.min() + row.max()) / 2, wy, imp=0.7, vis=2)
            inner = widths[(widths > 0)]
            if inner.size:
                ny_idx = int(np.argmin(np.where(widths > 0, widths, widths.max() + 1)))
                ny = int(rows[ny_idx])
                nrow = np.nonzero(mask[ny])[0]
                if nrow.size:
                    add_landmark("narrowest_point", (nrow.min() + nrow.max()) / 2, ny, imp=0.55, vis=3)

    # ── 3. Main axis (PCA of the subject pixels) ──────────────────────────────
    main_axis = None
    if len(xs) > 10:
        pts = np.column_stack([xs, ys]).astype(np.float32)
        mean = pts.mean(axis=0)
        cov = np.cov((pts - mean).T)
        evals, evecs = np.linalg.eigh(cov)
        major = evecs[:, int(np.argmax(evals))]
        half = math.sqrt(max(evals)) * 2.0
        a = (mean[0] - major[0] * half, mean[1] - major[1] * half)
        b = (mean[0] + major[0] * half, mean[1] + major[1] * half)
        # clamp to bounds
        a = (float(np.clip(a[0], x0, x1)), float(np.clip(a[1], y0, y1)))
        b = (float(np.clip(b[0], x0, x1)), float(np.clip(b[1], y0, y1)))
        la = add_landmark("axis_endpoint", a[0], a[1], imp=0.65, vis=2)
        lb = add_landmark("axis_endpoint", b[0], b[1], imp=0.65, vis=2)
        main_axis = Axis(
            id=_nid("ax"), start=(round(a[0], 1), round(a[1], 1)),
            end=(round(b[0], 1), round(b[1], 1)),
            orientation_deg=_orientation_deg(a, b), role="main_axis",
            related_landmark_ids=[la, lb], importance=0.8, visibility_level=2,
            lesson_order=order,
        )

    # ── 4. Silhouette (3 artistic levels) + envelope ──────────────────────────
    # Busy photos get more simplification + bigger point spacing automatically,
    # so the contour "comes out" readable instead of a tangle (user feedback).
    busy = _busyness(cache)
    mult = _busy_mult(busy)
    max_side = float(max(H, W))
    silhouette = None
    silhouette_levels: dict[str, VectorPath] = {}
    envelope = None
    if contour is not None and len(contour) >= 4:
        peri = cv2.arcLength(contour.astype(np.int32), True)
        for level, (eps_frac, spacing_frac) in _CONTOUR_LEVELS.items():
            approx = cv2.approxPolyDP(
                contour.astype(np.int32), eps_frac * mult * peri, True
            ).reshape(-1, 2).astype(np.float32)
            approx = _min_spacing(approx, spacing_frac * mult * max_side)
            silhouette_levels[level] = VectorPath(
                id=_nid("path"), category="silhouette", points=_polygon(approx),
                closed=True, hierarchy_level=1, importance=1.0, persistence=1.0,
                stage="silhouette", lesson_order=0,
            )
        silhouette = silhouette_levels["standard"]
        # Envelope: coarse epsilon (few big segments), stored separately.
        coarse = cv2.approxPolyDP(contour.astype(np.int32), 0.03 * peri, True).reshape(-1, 2)
        env_verts = _polygon(coarse)
        env_landmarks = []
        for vx, vy in env_verts:
            env_landmarks.append(add_landmark("major_corner", vx, vy, imp=0.75, vis=1))
        envelope = Envelope(
            id=_nid("env"), vertices=env_verts, segment_count=len(env_verts),
            landmark_ids=env_landmarks,
        )

    # ── 4b. Tonal outlines — the "shadow line" (user feedback: outlines for
    #    the tones were missing). Value-zone boundaries inside the subject,
    #    simplified with the same busy-aware spacing, so the block-in fills
    #    ready-drawn shapes. ────────────────────────────────────────────────
    tonal_paths: list[VectorPath] = []
    if zone_map is not None and zone_map.shape == (H, W):
        eps_frac, spacing_frac = _CONTOUR_LEVELS["standard"]
        min_area = 0.005 * H * W
        for zone_id in np.unique(zone_map):
            zmask = ((zone_map == zone_id) & (mask > 0)).astype(np.uint8)
            if zmask.sum() < min_area:
                continue
            zmask = cv2.morphologyEx(zmask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            cnts, _ = cv2.findContours(zmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:3]
            for c in cnts:
                if cv2.contourArea(c) < min_area:
                    continue
                approx = cv2.approxPolyDP(
                    c, eps_frac * mult * cv2.arcLength(c, True), True
                ).reshape(-1, 2).astype(np.float32)
                approx = _min_spacing(approx, spacing_frac * mult * max_side)
                if len(approx) < 3:
                    continue
                tonal_paths.append(VectorPath(
                    id=_nid("path"), category="tonal_boundary", points=_polygon(approx),
                    closed=True, hierarchy_level=2,
                    importance=round(min(1.0, cv2.contourArea(c) / (H * W) * 4), 3),
                    stage="shadow_line", lesson_order=0, value_zone=int(zone_id),
                ))
        tonal_paths.sort(key=lambda p: p.importance, reverse=True)
        tonal_paths = tonal_paths[:10]   # the big tonal shapes, not confetti

    # ── 5. Negative spaces (bbox ∩ ¬subject connected components) ─────────────
    negative_spaces: list[NegativeSpace] = []
    bbox_area = max(1.0, (x1 - x0) * (y1 - y0))
    if contour is not None:
        sub = np.zeros((H, W), np.uint8)
        sub[int(y0):int(y1) + 1, int(x0):int(x1) + 1] = 1
        neg = (sub & (1 - mask)).astype(np.uint8)
        ncnts, _ = cv2.findContours(neg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        ncnts = sorted(ncnts, key=cv2.contourArea, reverse=True)[:4]
        for i, nc in enumerate(ncnts):
            area = cv2.contourArea(nc)
            if area < 0.01 * bbox_area:
                continue
            poly = cv2.approxPolyDP(nc, 0.02 * cv2.arcLength(nc, True), True).reshape(-1, 2)
            nx0, ny0, nw, nh = cv2.boundingRect(nc)
            touches = []
            if nx0 <= x0 + 2: touches.append("left")
            if nx0 + nw >= x1 - 2: touches.append("right")
            if ny0 <= y0 + 2: touches.append("top")
            if ny0 + nh >= y1 - 2: touches.append("bottom")
            order += 1
            negative_spaces.append(NegativeSpace(
                id=_nid("neg"), polygon=_polygon(poly), touches_edges=touches,
                area_fraction=round(area / bbox_area, 4), importance=round(min(1.0, area / bbox_area * 3), 3),
                visibility_level=2, lesson_order=order,
            ))

    # ── 6. Proportion references (thirds of the bbox + height/width ratio) ────
    proportion_checks: list[ProportionCheck] = []
    if x1 > x0 and y1 > y0:
        ratio = round((y1 - y0) / (x1 - x0), 3)
        proportion_checks.append(ProportionCheck(
            id=_nid("prop"), kind="ratio",
            label=f"The subject is {ratio:.2f}× as tall as it is wide — check this before refining.",
            value=ratio, reference_points=[(round(x0, 1), round(y0, 1)), (round(x1, 1), round(y1, 1))],
        ))
        for frac, name in ((1 / 3, "upper third"), (2 / 3, "lower third")):
            ty = y0 + (y1 - y0) * frac
            lm = add_landmark("proportion_reference", (x0 + x1) / 2, ty, imp=0.5, vis=2)
            proportion_checks.append(ProportionCheck(
                id=_nid("prop"), kind="thirds",
                label=f"Mark the {name}: a horizontal at {int(frac*100)}% down the subject height.",
                reference_points=[(round(x0, 1), round(ty, 1)), (round(x1, 1), round(ty, 1))],
                landmark_ids=[lm],
            ))

    # ── 7. Internal structural paths (primary/secondary edges inside subject) ─
    internal_paths: list[VectorPath] = []
    dominant_slopes: list[Axis] = []
    region_by_id = {r.id: r for r in regions}
    for e in edges:
        if e.type not in ("primary", "secondary") or len(e.path) < 2:
            continue
        pts = np.array(e.path, dtype=np.float32)
        # inside test: sample a few points, keep if the majority fall on the subject
        idx = np.linspace(0, len(pts) - 1, min(9, len(pts))).astype(int)
        inside = 0
        for px, py in pts[idx]:
            ix, iy = int(np.clip(px, 0, W - 1)), int(np.clip(py, 0, H - 1))
            inside += int(mask[iy, ix] > 0)
        if inside < 0.6 * len(idx):
            continue
        simplified = cv2.approxPolyDP(pts.astype(np.int32), 2.0, False).reshape(-1, 2)
        if len(simplified) < 2:
            continue
        cat = "internal_division" if e.type == "primary" else "secondary_structure"
        stage = "internal_divisions" if e.type == "primary" else "secondary_structure"
        rids = [r for r in (e.region_a, e.region_b) if r is not None and r in region_by_id]
        internal_paths.append(VectorPath(
            id=_nid("path"), category=cat, points=_polygon(simplified), closed=False,
            region_ids=rids, hierarchy_level=1 if e.type == "primary" else 3,
            importance=round(float(e.importance), 3), persistence=round(float(e.importance), 3),
            stage=stage, lesson_order=0,
        ))
        # dominant slope: the principal direction of a long-enough primary edge
        # (PCA extent, not endpoint distance — the path may curve back on itself)
        if e.type == "primary" and len(simplified) >= 2:
            sp = simplified.astype(np.float32)
            mean = sp.mean(axis=0)
            if len(sp) >= 3:
                evals, evecs = np.linalg.eigh(np.cov((sp - mean).T))
                v = evecs[:, int(np.argmax(evals))]
                extent = math.sqrt(max(evals)) * 2.0
            else:
                v = (sp[-1] - sp[0]); extent = float(np.hypot(*v)); v = v / (extent + 1e-6)
            if extent > 0.10 * max(H, W):
                a_pt = (mean[0] - v[0] * extent, mean[1] - v[1] * extent)
                b_pt = (mean[0] + v[0] * extent, mean[1] + v[1] * extent)
                dominant_slopes.append(Axis(
                    id=_nid("ax"), start=(round(float(a_pt[0]), 1), round(float(a_pt[1]), 1)),
                    end=(round(float(b_pt[0]), 1), round(float(b_pt[1]), 1)),
                    orientation_deg=_orientation_deg(a_pt, b_pt), role="dominant_slope",
                    importance=round(float(e.importance), 3), visibility_level=2,
                ))
    # keep the strongest handful of internal paths so a beginner isn't buried
    internal_paths.sort(key=lambda p: p.importance, reverse=True)
    dominant_slopes.sort(key=lambda a: a.importance, reverse=True)
    dominant_slopes = dominant_slopes[:5]

    analysis = DrawingAnalysis(
        id=_nid("draw"), project_id=project_id, job_id=job_id,
        image_width=W, image_height=H, canvas_ratio=round(W / H, 4),
        subject_bounds=bounds, occupied_area=hull_poly,
        main_axis=main_axis, dominant_slopes=dominant_slopes,
        landmarks=landmarks, negative_spaces=negative_spaces,
        proportion_checks=proportion_checks, envelope=envelope,
        silhouette=silhouette, silhouette_levels=silhouette_levels,
        tonal_paths=tonal_paths, internal_paths=internal_paths,
        parameters={"contour_levels": {k: list(v) for k, v in _CONTOUR_LEVELS.items()},
                    "envelope_epsilon_frac": 0.03,
                    "busyness": round(busy, 3), "busy_multiplier": round(mult, 2)},
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    analysis.construction_order = _build_construction_order(analysis)
    _assign_lesson_order(analysis)
    return analysis


# ── Pedagogical construction order (spec §2) ──────────────────────────────────

def _build_construction_order(a: DrawingAnalysis) -> list[ConstructionStage]:
    """Assemble the fixed pedagogical build order, wiring each stage to the
    geometry it reveals. Order is NOT derived from path position/length."""
    by_cat: dict[str, list[str]] = {}
    for lm in a.landmarks:
        by_cat.setdefault(lm.category, []).append(lm.id)

    stages: list[ConstructionStage] = []
    o = 0

    def stage(sid, title, summary, **kw) -> None:
        nonlocal o
        o += 1
        stages.append(ConstructionStage(id=sid, order=o, title=title, summary=summary, **kw))

    stage("canvas", "Canvas ratio",
          f"Set a canvas of ratio {a.canvas_ratio:.2f} (width ÷ height) to match the reference crop.")
    stage("placement", "Placement & margins",
          "Place the subject with the same margins it has in the reference before drawing anything inside it.")
    limit_ids = (by_cat.get("subject_top", []) + by_cat.get("subject_bottom", [])
                 + by_cat.get("subject_left", []) + by_cat.get("subject_right", []))
    stage("bounds", "Top, bottom, left, right limits",
          "Mark the four outer limits of the subject — the box everything else is measured against.",
          landmark_ids=limit_ids)
    stage("occupied_area", "Main occupied area",
          "Block the overall shape the subject occupies inside that box.")
    landmark_ids = (by_cat.get("widest_point", []) + by_cat.get("narrowest_point", [])
                    + by_cat.get("major_corner", []))
    stage("landmarks", "Structural landmarks",
          "Place the widest and narrowest points and the major corners of the outline.",
          landmark_ids=landmark_ids)
    stage("axis", "Main axis",
          "Draw the main axis the subject leans along — everything hangs off this line.",
          axis_ids=[a.main_axis.id] if a.main_axis else [],
          landmark_ids=by_cat.get("axis_endpoint", []))
    stage("slopes", "Dominant slopes",
          "Compare the major slopes against each other and the axis before committing curves.",
          axis_ids=[s.id for s in a.dominant_slopes])
    stage("envelope", "Simplified envelope",
          "Connect the landmarks with a few big straight segments — the envelope, not the final line.",
          path_ids=[], landmark_ids=a.envelope.landmark_ids if a.envelope else [])
    stage("negative_space", "Negative-space check",
          "Check the shapes of the spaces AROUND the subject — they must match before you trust the outline.",
          negative_space_ids=[n.id for n in a.negative_spaces])
    stage("proportion", "Proportion check",
          "Verify the big proportions against the reference before refining any edge.",
          proportion_check_ids=[p.id for p in a.proportion_checks],
          landmark_ids=by_cat.get("proportion_reference", []))
    stage("silhouette", "Refined outer silhouette",
          "Now refine the straight envelope into the accurate outer contour.",
          path_ids=[a.silhouette.id] if a.silhouette else [])
    stage("internal_divisions", "Major internal divisions",
          "Add only the largest internal divisions — the big planes and form breaks.",
          path_ids=[p.id for p in a.internal_paths if p.category == "internal_division"])
    stage("secondary_structure", "Secondary structural lines",
          "Add secondary structural lines where they genuinely help the drawing read.",
          path_ids=[p.id for p in a.internal_paths if p.category == "secondary_structure"])
    stage("shadow_line", "Outline the tones (shadow line)",
          "Draw the boundaries of the big light and shadow shapes ON the drawing — "
          "so the painting fills ready-made shapes instead of guessing them.",
          path_ids=[p.id for p in a.tonal_paths])
    stage("checkpoint", "Drawing checkpoint",
          "Stop and compare the whole drawing against the reference before any value or colour.",
          is_checkpoint=True)
    return stages


def _assign_lesson_order(a: DrawingAnalysis) -> None:
    """Stamp each path/landmark with a global lesson_order that follows the
    construction stages, so consumers never have to re-derive teaching order
    from geometry."""
    seq = 0
    for st in a.construction_order:
        seq += 1
        for pid in st.path_ids:
            for p in a.all_paths():
                if p.id == pid:
                    p.lesson_order = seq
                    p.stage = st.id
