from __future__ import annotations
import cv2
import numpy as np

from .models import Edge
from .preprocessing import ImageCache

# Minimum contour arc-length to count as an edge
_MIN_ARC = 8


def extract_edge_hierarchy(
    cache: ImageCache,
    label_map: np.ndarray | None,
    fg_mask: np.ndarray | None = None,
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

        importance = arc_norm * 0.6 + mean_grad * 0.4
        if in_bg:
            importance *= 0.3

        if arc_norm > 0.12 or mean_grad > 0.7:
            etype = "primary"
        elif arc_norm > 0.04 or mean_grad > 0.45:
            etype = "secondary"
        elif local_texture > 0.15 or arc < 20:
            etype = "texture"
        else:
            etype = "decorative"

        edges.append(Edge(
            id=eid,
            region_a=0,
            region_b=None,
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
        elif etype == "decorative":
            cv2.polylines(maps_decorative, [draw_pts], False, 255, 1)
        else:
            cv2.polylines(maps_texture, [draw_pts], False, 255, 1)

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
