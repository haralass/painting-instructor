"""
Edge-cause attribution (Phase 3, spec §3/§16).

For each construction path, estimate WHY the edge is there — an object/depth
boundary, an illumination (shading) edge, a reflectance (material-colour)
edge, or texture — by sampling the existing signals across the edge. This is
deliberately a soft distribution with a confidence, never a hard claim: when
the signals disagree or are weak, confidence stays low and no strong
statement should be made downstream.

Signals used (all already computed for the job):
- depth_lbl  → a plane change across the edge suggests a depth/object edge
- L* (value) → a large luminance step with little colour change suggests light
- a*/b*      → a colour (chroma/hue) step suggests a reflectance/material edge
- gradient   → high local high-frequency energy suggests texture
"""
from __future__ import annotations

import numpy as np

from ..schemas.drawing import DrawingAnalysis, EdgeCauseEstimate, VectorPath


def _normals(pts: np.ndarray) -> np.ndarray:
    """Unit normals at each point of a polyline (perpendicular to the local tangent)."""
    tang = np.zeros_like(pts)
    tang[1:-1] = pts[2:] - pts[:-2]
    tang[0] = pts[1] - pts[0]
    tang[-1] = pts[-1] - pts[-2]
    n = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
    norm = np.hypot(n[:, 0], n[:, 1]) + 1e-6
    return n / norm[:, None]


def _sample(arr: np.ndarray, xy: np.ndarray, H: int, W: int):
    x = np.clip(xy[:, 0].astype(int), 0, W - 1)
    y = np.clip(xy[:, 1].astype(int), 0, H - 1)
    return arr[y, x]


def _estimate_path_cause(
    path: VectorPath, cache, depth_lbl, offset: float = 4.0,
) -> EdgeCauseEstimate:
    H, W = cache.H, cache.W
    pts = np.array(path.points, dtype=np.float32)
    if len(pts) < 2:
        return EdgeCauseEstimate(scores={}, primary=None, confidence=0.0)

    # Sample up to 40 evenly spaced points; look a few px to each side.
    idx = np.linspace(0, len(pts) - 1, min(40, len(pts))).astype(int)
    p = pts[idx]
    nrm = _normals(pts)[idx]
    side_a = p + nrm * offset
    side_b = p - nrm * offset

    L = cache.L
    a, b = cache.a, cache.b
    dL = np.abs(_sample(L, side_a, H, W) - _sample(L, side_b, H, W))          # 0..100
    dChroma = np.hypot(_sample(a, side_a, H, W) - _sample(a, side_b, H, W),
                       _sample(b, side_a, H, W) - _sample(b, side_b, H, W))    # ~0..100

    lum_step = float(np.median(dL)) / 100.0
    col_step = float(np.median(dChroma)) / 60.0

    # Texture: local high-frequency energy along the edge.
    grad = cache.grad
    g = _sample(grad, p, H, W)
    tex = float(np.clip(np.std(g) / (np.mean(g) + 1e-6), 0, 1))

    depth_step = 0.0
    if depth_lbl is not None and depth_lbl.shape == (H, W):
        da = _sample(depth_lbl.astype(np.float32), side_a, H, W)
        db = _sample(depth_lbl.astype(np.float32), side_b, H, W)
        depth_step = float(np.mean(np.abs(da - db)) > 0.5)  # crosses a plane boundary

    # Raw evidence per cause.
    ev = {
        "object_boundary": 1.0 if path.category == "silhouette" else 0.3 + 0.4 * depth_step,
        "depth":           depth_step,
        "illumination":    max(0.0, lum_step - col_step),
        "reflectance":     max(0.0, col_step - 0.3 * lum_step),
        "texture":         tex if tex > 0.6 else 0.0,
    }
    total = sum(ev.values()) + 1e-6
    scores = {k: round(v / total, 3) for k, v in ev.items()}
    primary = max(scores, key=scores.get)
    top = scores[primary]
    runner = sorted(scores.values(), reverse=True)[1] if len(scores) > 1 else 0.0
    # Confidence: separation between top and runner-up, scaled by signal strength.
    signal = min(1.0, lum_step + col_step + depth_step)
    confidence = round(float(np.clip((top - runner) * 1.5 * signal, 0, 1)), 3)
    # Always expose the mode of the distribution; confidence conveys how much
    # to trust it (the lesson/UI states it strongly only when confidence is
    # high — spec §16: use confidence to decide, not to hide the estimate).
    return EdgeCauseEstimate(scores=scores, primary=primary, confidence=confidence)


def attach_edge_causes(drawing: DrawingAnalysis, cache, depth_lbl, zone_map=None) -> None:
    """Fill `edge_cause` on the silhouette and every internal path in place."""
    for path in drawing.all_paths():
        try:
            path.edge_cause = _estimate_path_cause(path, cache, depth_lbl)
        except Exception:
            path.edge_cause = EdgeCauseEstimate(scores={}, primary=None, confidence=0.0)
