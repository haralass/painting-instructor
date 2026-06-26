from __future__ import annotations
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.morphology import skeletonize
from scipy.spatial import cKDTree
import sknw

from ...utils.fonts import get_font as _font


def _resample_polyline(pts: np.ndarray, n: int) -> np.ndarray:
    """Arc-length uniform resampling of a polyline to exactly n points."""
    if len(pts) < 2:
        return pts
    diffs = np.diff(pts.astype(float), axis=0)
    seg = np.hypot(diffs[:, 0], diffs[:, 1])
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    if arc[-1] == 0:
        return pts
    arc /= arc[-1]
    t = np.linspace(0.0, 1.0, n)
    x = np.interp(t, arc, pts[:, 0].astype(float))
    y = np.interp(t, arc, pts[:, 1].astype(float))
    return np.stack([x, y], axis=1)


def _chain_nearest(pts: np.ndarray, n_dots: int) -> np.ndarray:
    """
    Greedy nearest-endpoint chaining via cKDTree — O(D log D) instead of O(D²).
    Chain a set of 2D polyline endpoints into an ordered sequence.
    """
    if len(pts) == 0:
        return pts
    used = np.zeros(len(pts), dtype=bool)
    order = [0]
    used[0] = True
    tree = cKDTree(pts)

    for _ in range(len(pts) - 1):
        cur = pts[order[-1]]
        # Query more neighbours than needed to find first unvisited
        k = min(20, len(pts))
        dists, idxs = tree.query(cur, k=k)
        found = False
        for idx in (idxs if np.ndim(idxs) > 0 else [idxs]):
            if not used[int(idx)]:
                order.append(int(idx))
                used[int(idx)] = True
                found = True
                break
        if not found:
            break
    return pts[np.array(order)]


def _chain_polylines(polylines: list[np.ndarray]) -> np.ndarray:
    """
    Vectorised greedy nearest-endpoint chaining via cKDTree on endpoints.
    Falls back to simple concatenation for single-polyline input.
    """
    if not polylines:
        return np.empty((0, 2))
    remaining = [p.copy() for p in polylines if len(p) >= 2]
    if not remaining:
        return np.empty((0, 2))
    if len(remaining) == 1:
        return remaining[0]

    # Build endpoint array: [start_0, end_0, start_1, end_1, ...]
    endpoints = []
    for p in remaining:
        endpoints.append(p[0])
        endpoints.append(p[-1])
    ep_arr = np.array(endpoints, dtype=float)   # (2*n, 2)

    n = len(remaining)
    visited = np.zeros(n, dtype=bool)
    chain = [remaining[0]]
    visited[0] = True

    while not visited.all():
        tail = chain[-1][-1]
        best_dist = np.inf
        best_i = -1
        best_flip = False
        for i in range(n):
            if visited[i]:
                continue
            ds = np.sum((remaining[i][0] - tail) ** 2)
            de = np.sum((remaining[i][-1] - tail) ** 2)
            if ds < best_dist:
                best_dist = ds
                best_i = i
                best_flip = False
            if de < best_dist:
                best_dist = de
                best_i = i
                best_flip = True
        if best_i == -1:
            break
        seg = remaining[best_i][::-1] if best_flip else remaining[best_i]
        chain.append(seg)
        visited[best_i] = True

    return np.concatenate(chain, axis=0)


def _local_2opt(pts: np.ndarray, max_iters: int = 200, max_secs: float = 0.5) -> np.ndarray:
    """Bounded local 2-opt: only checks nearby segments, not all pairs."""
    n = len(pts)
    if n < 4:
        return pts
    improved = True
    iters = 0
    t0 = time.perf_counter()
    while improved and iters < max_iters and (time.perf_counter() - t0) < max_secs:
        improved = False
        iters += 1
        # Only check segments within a local window of 20 (not global O(n²))
        for i in range(n - 1):
            window_end = min(n, i + 20)
            for j in range(i + 2, window_end):
                d_before = (np.linalg.norm(pts[i + 1] - pts[i]) +
                            np.linalg.norm(pts[(j + 1) % n] - pts[j]))
                d_after  = (np.linalg.norm(pts[j] - pts[i]) +
                            np.linalg.norm(pts[(j + 1) % n] - pts[i + 1]))
                if d_after < d_before - 1e-6:
                    pts[i + 1:j + 1] = pts[i + 1:j + 1][::-1]
                    improved = True
    return pts


def process(
    img: Image.Image,
    n_dots: int = 500,
    threshold: float = 0.25,
    line_art_img: Image.Image | None = None,
    fg_mask: np.ndarray | None = None,
) -> Image.Image:
    """
    Photo → numbered dot-to-dot activity page.

    Pipeline:
    1. Edge map — if line_art_img supplied, inverts it and optionally masks
       to foreground only (strips background XDoG noise); else falls back to Canny.
    2. Skeletonize → 1px skeleton
    3. sknw → ordered polylines
    4. Arc-length resampling (proportional dot allocation per polyline)
    5. cKDTree greedy chaining — O(D log D) endpoint chaining
    6. Bounded local 2-opt (window=20, max 200 iters, 0.5s cap)
    7. Final dot-count cap via uniform subsampling
    8. Numbered circle rendering

    Args:
        line_art_img: Pre-computed line art (black lines on white).
                      Reuses existing output — no second DexiNed pass.
        fg_mask:      (H,W) uint8 foreground mask.  When supplied together
                      with line_art_img the background XDoG layer is stripped
                      before skeletonising, dramatically reducing skeleton noise.
    """
    W, H    = img.size
    img_rgb = np.array(img.convert("RGB"))

    # ── Edge map ──────────────────────────────────────────────────────────────
    if line_art_img is not None:
        la       = np.array(line_art_img.convert("L"))
        edge_map = (255 - la).astype(np.uint8)          # bright = edge
        if fg_mask is not None:
            # Keep only foreground edges — removes distracting background XDoG
            edge_map = (edge_map * fg_mask).astype(np.uint8)
    else:
        gray     = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        edge_map = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 30, 90)

    binary = (edge_map > int(threshold * 255)).astype(np.uint8)
    skel   = skeletonize(binary > 0).astype(np.uint8)

    # ── Safe empty skeleton handling ─────────────────────────────────────────
    if skel is None or skel.sum() == 0:
        return Image.fromarray(np.full((H, W, 3), 255, dtype=np.uint8))

    # ── Skeleton → polylines ──────────────────────────────────────────────────
    graph     = sknw.build_sknw(skel)
    polylines = []
    for s, e in graph.edges():
        pts = graph[s][e]['pts']
        if len(pts) >= 2:
            polylines.append(pts[:, ::-1].astype(float))   # (row,col) → (x,y)

    if not polylines:
        ys, xs  = np.where(skel > 0)
        if len(xs) == 0:
            return Image.fromarray(np.full((H, W, 3), 255, dtype=np.uint8))
        pts_fb  = np.column_stack([xs, ys]).astype(float)
        idx     = np.round(np.linspace(0, len(pts_fb) - 1, min(n_dots, len(pts_fb)))).astype(int)
        ordered = pts_fb[idx]
    else:
        arc_lens = []
        for p in polylines:
            d = np.diff(p, axis=0)
            arc_lens.append(float(np.sum(np.hypot(d[:, 0], d[:, 1]))))
        total = max(sum(arc_lens), 1.0)

        resampled = []
        for p, al in zip(polylines, arc_lens):
            k = max(3, int(n_dots * al / total))
            resampled.append(_resample_polyline(p, k))

        # Collect all resampled points and chain with cKDTree
        all_pts = np.concatenate(resampled, axis=0)

        # Check for empty endpoints before chaining
        if len(all_pts) == 0:
            return Image.fromarray(np.full((H, W, 3), 255, dtype=np.uint8))

        chained = _chain_polylines(resampled)
        ordered = _local_2opt(chained.copy(), max_iters=200, max_secs=0.5)

    # ── Final dot-count cap — subsample evenly if over budget ────────────────
    if len(ordered) > n_dots:
        idx = np.round(np.linspace(0, len(ordered) - 1, n_dots)).astype(int)
        ordered = ordered[idx]

    # ── Clamp to image bounds ─────────────────────────────────────────────────
    dots     = ordered.astype(int)
    dots[:, 0] = np.clip(dots[:, 0], 0, W - 1)
    dots[:, 1] = np.clip(dots[:, 1], 0, H - 1)

    # ── Render ────────────────────────────────────────────────────────────────
    out = Image.new("RGB", (W, H), "white")
    dr  = ImageDraw.Draw(out)
    fn  = _font(8)
    fn2 = _font(6)

    for i in range(len(dots) - 1):
        x1, y1 = int(dots[i][0]),     int(dots[i][1])
        x2, y2 = int(dots[i + 1][0]), int(dots[i + 1][1])
        dr.line([(x1, y1), (x2, y2)], fill=(210, 210, 210), width=1)

    for i, (x, y) in enumerate(dots):
        r = 3
        dr.ellipse([x - r, y - r, x + r, y + r], outline=(0, 0, 0), width=1)
        if i % 3 == 0 or i < 20 or i == len(dots) - 1:
            fn_use = fn if i < 100 else fn2
            dr.text((x + r + 1, y - r - 1), str(i + 1), fill=(50, 50, 50), font=fn_use)

    return out
