from __future__ import annotations
import logging
import time
import cv2
import numpy as np
from scipy.ndimage import mean as ndimage_mean

from .models import Edge
from .preprocessing import ImageCache

log = logging.getLogger(__name__)

# Minimum contour arc-length to count as an edge
_MIN_ARC = 8

# Which edge types are visible at each of the 5 hierarchical detail levels.
# Shared between pipeline.py (level-aware outline filtering) and renderer.py
# (edge_ids metadata) so the two never drift apart.
LEVEL_EDGE_TYPES: dict[int, set[str]] = {
    1: {"primary"},
    2: {"primary"},
    3: {"primary", "secondary"},
    4: {"primary", "secondary", "decorative"},
    5: {"primary", "secondary", "decorative", "texture"},
}


def _label_to_rid(raw_lbl: int | None, mapping: dict[int, int] | None) -> int | None:
    """
    Resolve a raw label value to a Region.id using the provided mapping.

    Label 0 IS a valid region (zero-based indexing). Only None means no region.
    """
    if raw_lbl is None:
        return None
    if mapping is not None:
        return mapping.get(raw_lbl)   # None if label not in map
    return raw_lbl   # fall back to raw label if no mapping provided


def extract_edge_hierarchy(
    cache: ImageCache,
    label_map: np.ndarray | None,
    fg_mask: np.ndarray | None = None,
    include_texture: bool = True,
    include_background: bool = True,
    label_to_region_id: dict[int, int] | None = None,
    # A13: pathological-input budgets
    max_edges: int = 20_000,
    max_contours: int = 50_000,
    max_time_secs: float = 25.0,
    max_svg_points: int = 500_000,
) -> tuple[list[Edge], dict[str, np.ndarray]]:
    """
    Classify detected edges into four semantic levels:

    primary    — silhouette + large structural boundaries
    secondary  — inter-region boundaries between major areas
    decorative — pattern lines, design elements, moderate-length contours
    texture    — high-frequency, short, repetitive edges

    Classification is based on:
    - contour arc-length (longer = more structural)
    - mean gradient strength along the contour
    - neighbouring region area (large regions → structural boundary)
    - LAB colour/value difference across the boundary
    - local texture frequency (std of gradient in surrounding patch)

    Returns
    -------
    edges    : list[Edge]
    maps     : dict type_name → binary uint8 edge mask (white edges on black)
    """
    H, W   = cache.H, cache.W
    gray   = cache.gray
    grad   = cache.grad

    # Multi-scale edge detection: Canny at coarse and fine sigma
    blur_coarse = cv2.GaussianBlur(gray, (0, 0), 3.0)
    blur_fine   = cv2.GaussianBlur(gray, (0, 0), 0.8)
    canny_coarse = cv2.Canny(blur_coarse, 20, 60)
    canny_fine   = cv2.Canny(blur_fine,   40, 110)

    # Combine: primary candidates = coarse only; texture = fine minus coarse
    combined = np.maximum(canny_coarse, canny_fine)

    contours, _ = cv2.findContours(combined, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    # Background mask: if fg_mask available, edges in background are downgraded
    bg_mask = None
    if fg_mask is not None:
        bg_mask = (fg_mask == 0)

    # Precompute per-label stats if label_map given — vectorised, no per-label mask scan
    # label_stats is keyed by RAW label value (before Region.id mapping)
    label_stats: dict[int, dict] = {}
    if label_map is not None:
        lab_img = cache.lab.astype(np.float32)
        flat_lm = label_map.ravel()
        unique_lbls = np.unique(flat_lm)
        L_stats = ndimage_mean(lab_img[:, :, 0], label_map, unique_lbls)
        a_stats = ndimage_mean(lab_img[:, :, 1], label_map, unique_lbls)
        b_stats = ndimage_mean(lab_img[:, :, 2], label_map, unique_lbls)
        area_lut = np.bincount(flat_lm, minlength=int(unique_lbls.max()) + 1)
        label_stats = {
            int(lbl): {
                "mean_lab": np.array([float(L_stats[i]), float(a_stats[i]), float(b_stats[i])]),
                "area": int(area_lut[lbl]),
            }
            for i, lbl in enumerate(unique_lbls)
        }

    edges: list[Edge] = []
    maps_primary   = np.zeros((H, W), dtype=np.uint8)
    maps_secondary = np.zeros((H, W), dtype=np.uint8)
    maps_decorative= np.zeros((H, W), dtype=np.uint8)
    maps_texture   = np.zeros((H, W), dtype=np.uint8)

    # A13: cap contour count before the loop — drop lowest-arc contours first
    if len(contours) > max_contours:
        arcs = [cv2.arcLength(c, False) for c in contours]
        order = sorted(range(len(contours)), key=lambda k: arcs[k], reverse=True)
        contours = [contours[k] for k in order[:max_contours]]
        log.warning("extract_edge_hierarchy: capped contours from %d to %d", len(order), max_contours)

    max_arc  = max((cv2.arcLength(c, False) for c in contours), default=1.0)
    max_grad = float(grad.max()) + 1e-6

    _t0 = time.perf_counter()
    _time_budget_exceeded = False
    _candidates: list[dict] = []

    for eid, cnt in enumerate(contours):
        # A13: time budget — check every 200 contours to avoid per-iteration overhead
        if eid % 200 == 0 and eid > 0:
            if time.perf_counter() - _t0 > max_time_secs:
                log.warning(
                    "extract_edge_hierarchy: time budget %.1fs exceeded after %d contours; stopping",
                    max_time_secs, eid,
                )
                _time_budget_exceeded = True
                break

        arc    = float(cv2.arcLength(cnt, False))
        if arc < _MIN_ARC:
            continue

        pts    = cnt.reshape(-1, 2)
        xs     = np.clip(pts[:, 0], 0, W - 1)
        ys     = np.clip(pts[:, 1], 0, H - 1)

        mean_grad  = float(grad[ys, xs].mean()) / max_grad
        arc_norm   = arc / max_arc

        # Local texture: std of gradient in small patch around midpoint
        mx, my = int(xs.mean()), int(ys.mean())
        r      = 6
        patch  = grad[
            max(0, my - r):min(H, my + r),
            max(0, mx - r):min(W, mx + r),
        ]
        local_texture = float(patch.std()) / max_grad if patch.size > 0 else 0.0

        # Determine edge type
        in_bg = False
        if bg_mask is not None:
            in_bg = bool(bg_mask[ys, xs].mean() > 0.5)

        # Sample neighbouring regions using offsets around contour midpoint
        ra_raw: int | None = None
        rb_raw: int | None = None
        if label_map is not None:
            H_lm, W_lm = label_map.shape
            mid_idx = len(pts) // 2
            mx_m, my_m = int(pts[mid_idx][0]), int(pts[mid_idx][1])
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1)]:
                nx, ny = mx_m + dx, my_m + dy
                if 0 <= nx < W_lm and 0 <= ny < H_lm:
                    lbl = int(label_map[ny, nx])
                    if ra_raw is None:
                        ra_raw = lbl
                    elif lbl != ra_raw:
                        rb_raw = lbl
                        break

        # Resolve raw label values to Region.id using mapping
        # Label 0 is valid — only None means no region
        ra = _label_to_rid(ra_raw, label_to_region_id)
        rb = _label_to_rid(rb_raw, label_to_region_id)

        # Use region stats for colour difference classification
        # label_stats is keyed by RAW label values
        colour_diff = 0.0
        area_a = 0
        area_b = 0
        if ra_raw is not None and ra_raw in label_stats:
            area_a = label_stats[ra_raw]["area"]
        if rb_raw is not None and rb_raw in label_stats:
            area_b = label_stats[rb_raw]["area"]
        if ra_raw is not None and rb_raw is not None and ra_raw in label_stats and rb_raw in label_stats:
            diff = label_stats[ra_raw]["mean_lab"] - label_stats[rb_raw]["mean_lab"]
            colour_diff = float(np.linalg.norm(diff)) / 100.0

        # Compute composite weighted score using region area, colour and value diff
        total_area = H * W
        mean_region_area = total_area / max(1, len(label_stats)) if label_stats else total_area
        area_score = min(1.0, (area_a + area_b) / (2 * mean_region_area + 1))

        value_diff_norm = 0.0
        if ra_raw is not None and rb_raw is not None and ra_raw in label_stats and rb_raw in label_stats:
            la_mean = label_stats[ra_raw]["mean_lab"]
            lb_mean = label_stats[rb_raw]["mean_lab"]
            value_diff_norm = abs(float(la_mean[0]) - float(lb_mean[0])) / 100.0  # L* diff normalised

        importance_bg = 0.3 if in_bg else 1.0

        composite = (
            arc_norm        * 0.25 +
            mean_grad       * 0.25 +
            colour_diff     * 0.20 +
            value_diff_norm * 0.15 +
            area_score      * 0.10 +
            (1 - local_texture) * 0.05
        ) * importance_bg

        # Classification is deferred: absolute thresholds starved real photos
        # of primary edges entirely (composite rarely exceeds 0.55 outside
        # synthetic images — the block-in outline pages rendered blank).
        # Collect candidates now; rank-based classification happens below.
        _candidates.append({
            "eid": eid, "pts": pts, "arc": arc, "arc_norm": arc_norm,
            "mean_grad": mean_grad, "colour_diff": colour_diff,
            "local_texture": local_texture, "in_bg": in_bg,
            "ra": ra, "rb": rb, "composite": composite,
        })

    # ── Rank-based classification ─────────────────────────────────────────────
    # Primary = the strongest ~6% of candidate edges (capped — a teaching
    # outline must be sparse), and a primary edge must also be long enough to
    # be structural: a 25-px glint can out-score a ridge line on gradient
    # alone. Secondary = the next ~22%. The rest split into texture/decorative
    # by the same local rules as before. Rank thresholds guarantee the
    # primary/secondary outline layers are never empty on real photos.
    _candidates.sort(key=lambda c: c["composite"], reverse=True)
    n_cand      = len(_candidates)
    n_primary   = max(6,  min(int(n_cand * 0.06), 48))
    n_secondary = max(20, min(int(n_cand * 0.22), 300))
    min_primary_arc = max(60.0, 0.02 * max_arc)

    for rank, c in enumerate(_candidates):
        if rank < n_primary and c["arc"] >= min_primary_arc:
            etype = "primary"
        elif rank < n_primary + n_secondary:
            etype = "secondary"
        elif c["local_texture"] > 0.18 or c["arc"] < 20:
            etype = "texture"
        else:
            etype = "decorative"

        # Exclusion policy: skip entirely — do NOT reclassify texture→decorative.
        # maps["texture"] will naturally remain all-zeros if no texture edges are drawn.
        if etype == "texture" and not include_texture:
            continue   # do not append, do not draw

        if c["in_bg"] and not include_background:
            continue   # skip background edge entirely

        edges.append(Edge(
            id=c["eid"],
            region_a=c["ra"],
            region_b=c["rb"],
            type=etype,
            strength=c["mean_grad"],
            hardness=float(np.clip(c["mean_grad"] * 1.5, 0, 1)),
            importance=c["composite"],
            path=c["pts"].tolist(),
        ))

        draw_pts = c["pts"].reshape(-1, 1, 2).astype(np.int32)
        if etype == "primary":
            cv2.polylines(maps_primary, [draw_pts], False, 255, 1)
        elif etype == "secondary":
            cv2.polylines(maps_secondary, [draw_pts], False, 255, 1)
        elif etype == "texture":
            cv2.polylines(maps_texture, [draw_pts], False, 255, 1)
        else:
            cv2.polylines(maps_decorative, [draw_pts], False, 255, 1)

    # A13: trim to max_edges by importance (discard low-value texture edges first)
    if len(edges) > max_edges:
        edges.sort(key=lambda e: e.importance, reverse=True)
        edges = edges[:max_edges]
        log.warning("extract_edge_hierarchy: trimmed edge list to %d", max_edges)

    maps = {
        "primary":    maps_primary,
        "secondary":  maps_secondary,
        "decorative": maps_decorative,
        "texture":    maps_texture,
    }
    return edges, maps


def render_outline_levels(maps: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """
    Composite progressive outline images (white background, black lines).

    outlines_primary              → primary only
    outlines_primary_secondary    → primary + secondary
    outlines_detailed             → primary + secondary + decorative
    outlines_full                 → all four types
    """
    def _composite(*keys: str) -> np.ndarray:
        combined = np.zeros_like(maps["primary"])
        for k in keys:
            combined = np.maximum(combined, maps.get(k, 0))
        return 255 - combined   # black on white

    return {
        "outlines_primary":           _composite("primary"),
        "outlines_primary_secondary": _composite("primary", "secondary"),
        "outlines_detailed":          _composite("primary", "secondary", "decorative"),
        "outlines_full":              _composite("primary", "secondary", "decorative", "texture"),
    }


def build_region_ancestor_chain(
    regions: list,
    edge_scale: str,
) -> dict[int, dict[str, int]]:
    """
    For every region at edge_scale, walk Region.parent_id up through
    successively coarser scales and record the ancestor region id at each
    scale reached. Used to test whether two edge_scale regions still belong
    to the same mass at a coarser detail level (in which case the edge
    between them is interior noise at that level, not a boundary).

    Returns {region_id: {scale_name: ancestor_region_id}}, always including
    edge_scale itself mapping to the region's own id.
    """
    regions_by_id = {r.id: r for r in regions}
    chains: dict[int, dict[str, int]] = {}
    for r in regions:
        if r.scale != edge_scale:
            continue
        chain = {edge_scale: r.id}
        cur = r
        while cur.parent_id is not None:
            parent = regions_by_id.get(cur.parent_id)
            if parent is None:
                break
            chain[parent.scale] = parent.id
            cur = parent
        chains[r.id] = chain
    return chains


def filter_edges_for_level(
    edges: list[Edge],
    level: int,
    target_scale: str,
    ancestor_chains: dict[int, dict[str, int]],
) -> list[Edge]:
    """
    Keep only edges that are (a) a type visible at this level, and (b) still
    a boundary between two DIFFERENT regions once rolled up to target_scale.
    An edge whose two sides collapse into the same coarse region at this
    level is interior detail that level shouldn't show — this is what makes
    Level 1 outlines genuinely coarser than Level 5, not just a type filter
    over one fixed-resolution edge set.

    Edges missing region context on either side (e.g. silhouette edges
    against background) are always kept — they carry structural meaning
    regardless of region resolution.
    """
    allowed_types = LEVEL_EDGE_TYPES[level]
    kept: list[Edge] = []
    for e in edges:
        if e.type not in allowed_types:
            continue
        anc_a = ancestor_chains.get(e.region_a, {}).get(target_scale) if e.region_a is not None else None
        anc_b = ancestor_chains.get(e.region_b, {}).get(target_scale) if e.region_b is not None else None
        if anc_a is None or anc_b is None or anc_a != anc_b:
            kept.append(e)
    return kept


def bucket_edge_maps(edges: list[Edge], H: int, W: int) -> dict[str, np.ndarray]:
    """
    Rasterise a list of edges into the four type maps (primary/secondary/
    decorative/texture), in the same format as extract_edge_hierarchy's
    `maps` return value (white line on black, per type). Used to turn a
    level-filtered edge subset back into images for rendering/medium styling.
    """
    maps = {
        "primary":    np.zeros((H, W), dtype=np.uint8),
        "secondary":  np.zeros((H, W), dtype=np.uint8),
        "decorative": np.zeros((H, W), dtype=np.uint8),
        "texture":    np.zeros((H, W), dtype=np.uint8),
    }
    for e in edges:
        if len(e.path) < 2 or e.type not in maps:
            continue
        pts = np.array(e.path, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(maps[e.type], [pts], False, 255, 1)
    return maps


def export_edges_svg(edges: list[Edge], width: int, height: int) -> str:
    """
    Export edge contours as an SVG string.
    Types are styled distinctly for vector use.
    """
    type_style = {
        "primary":    'stroke="#111111" stroke-width="2"',
        "secondary":  'stroke="#333333" stroke-width="1.2"',
        "decorative": 'stroke="#555555" stroke-width="0.8" stroke-dasharray="4 2"',
        "texture":    'stroke="#888888" stroke-width="0.4"',
    }
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for edge in edges:
        if len(edge.path) < 2:
            continue
        style = type_style.get(edge.type, type_style["texture"])
        pts   = " ".join(f"{float(p[0]):.1f},{float(p[1]):.1f}" for p in edge.path)
        lines.append(f'  <polyline points="{pts}" fill="none" {style}/>')
    lines.append("</svg>")
    return "\n".join(lines)
