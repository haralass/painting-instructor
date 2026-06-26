from __future__ import annotations
import cv2
import numpy as np
from scipy.ndimage import mean as ndimage_mean

from .models import Edge
from .preprocessing import ImageCache

# Minimum contour arc-length to count as an edge
_MIN_ARC = 8


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
    label_to_region_id: dict[int, int] | None = None,   # NEW param
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

    max_arc  = max((cv2.arcLength(c, False) for c in contours), default=1.0)
    max_grad = float(grad.max()) + 1e-6

    for eid, cnt in enumerate(contours):
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

        # Classification thresholds
        if composite > 0.55 or (arc_norm > 0.10 and mean_grad > 0.45):
            etype = "primary"
        elif composite > 0.30 or colour_diff > 0.35:
            etype = "secondary"
        elif local_texture > 0.18 or arc < 20:
            etype = "texture"
        else:
            etype = "decorative"

        importance = composite  # store composite as importance (diagnostic)

        # Exclusion policy: skip entirely — do NOT reclassify texture→decorative.
        # maps["texture"] will naturally remain all-zeros if no texture edges are drawn.
        if etype == "texture" and not include_texture:
            continue   # do not append, do not draw

        if in_bg and not include_background:
            continue   # skip background edge entirely

        edges.append(Edge(
            id=eid,
            region_a=ra,
            region_b=rb,
            type=etype,
            strength=mean_grad,
            hardness=float(np.clip(mean_grad * 1.5, 0, 1)),
            importance=importance,
            path=pts.tolist(),
        ))

        # Render to appropriate map
        draw_pts = pts.reshape(-1, 1, 2).astype(np.int32)
        if etype == "primary":
            cv2.polylines(maps_primary, [draw_pts], False, 255, 1)
        elif etype == "secondary":
            cv2.polylines(maps_secondary, [draw_pts], False, 255, 1)
        elif etype == "texture":
            cv2.polylines(maps_texture, [draw_pts], False, 255, 1)
        else:
            cv2.polylines(maps_decorative, [draw_pts], False, 255, 1)

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
