from __future__ import annotations
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.morphology import skeletonize
import sknw


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in ["/System/Library/Fonts/HelveticaNeue.ttc",
              "/System/Library/Fonts/Helvetica.ttc",
              "/System/Library/Fonts/Arial.ttf"]:
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    return ImageFont.load_default()


def _dexined_edges(img_rgb: np.ndarray) -> np.ndarray:
    """DexiNed structural edges via Kornia — thin, semantic, no skin texture noise."""
    import torch
    from kornia.models.dexined import DexiNed
    model = DexiNed(pretrained=True).eval()
    t = torch.from_numpy(img_rgb).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    with torch.no_grad():
        out = model(t)
    edges = out[0].squeeze().cpu().numpy() if isinstance(out, (list, tuple)) else out.squeeze().cpu().numpy()
    if edges.ndim == 3:
        edges = edges.mean(0)
    edges = (edges - edges.min()) / (edges.max() - edges.min() + 1e-8)
    return (edges * 255).astype(np.uint8)


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


def _chain_polylines(polylines: list[np.ndarray]) -> np.ndarray:
    """
    Greedy nearest-endpoint chaining.
    Connects polyline endpoints without global TSP — preserves within-contour order,
    eliminates inter-feature jumps.
    """
    if not polylines:
        return np.empty((0, 2))
    remaining = [p.copy() for p in polylines if len(p) >= 2]
    chain = [remaining.pop(0)]
    while remaining:
        tail = chain[-1][-1]
        best_i, best_d, best_rev = 0, float("inf"), False
        for i, p in enumerate(remaining):
            d_start = np.hypot(*(tail - p[0]))
            d_end   = np.hypot(*(tail - p[-1]))
            if d_start < best_d:
                best_i, best_d, best_rev = i, d_start, False
            if d_end < best_d:
                best_i, best_d, best_rev = i, d_end, True
        p = remaining.pop(best_i)
        chain.append(p[::-1] if best_rev else p)
    return np.concatenate(chain, axis=0)


def _two_opt_crossings(pts: np.ndarray, max_iter: int = 3000) -> np.ndarray:
    """Remove crossings with 2-opt swaps (Euclidean plane → crossing-free = 2-optimal)."""
    n = len(pts)
    improved = True
    itr = 0
    while improved and itr < max_iter:
        improved = False
        itr += 1
        for i in range(1, n - 2):
            for j in range(i + 2, n):
                a, b, c, d = pts[i-1], pts[i], pts[j-1], pts[j % n]
                # check if segment (a,b) crosses (c,d)
                def ccw(P, Q, R):
                    return (R[1]-P[1])*(Q[0]-P[0]) > (Q[1]-P[1])*(R[0]-P[0])
                if ccw(a,c,d) != ccw(b,c,d) and ccw(a,b,c) != ccw(a,b,d):
                    pts[i:j] = pts[i:j][::-1]
                    improved = True
    return pts


def process(
    img: Image.Image,
    n_dots: int = 500,
    threshold: float = 0.25,
    line_art_img: Image.Image | None = None,
) -> Image.Image:
    """
    Photo → numbered dot-to-dot activity page.

    Pipeline:
    1. Edge map — uses pre-computed line_art_img if supplied (avoids re-running DexiNed);
       falls back to Canny on the original photo.
    2. Skeletonize → 1px skeleton
    3. sknw → ordered polylines
    4. Arc-length resampling → proportional dot allocation per polyline
    5. Greedy nearest-endpoint chaining
    6. Light 2-opt crossing removal (max 80 iterations)
    7. Numbered circle rendering

    Args:
        line_art_img: Pre-computed line art (black lines on white, RGB).
                      If supplied, DexiNed is skipped entirely — ~10× faster.
    """
    W, H = img.size
    img_rgb = np.array(img.convert("RGB"))

    # --- structural edges ---------------------------------------------------
    if line_art_img is not None:
        # Line art is black-on-white; invert so edges are bright
        la = np.array(line_art_img.convert("L"))
        edge_map = 255 - la   # now bright = edge
    else:
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        edge_map = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 30, 90)

    binary = (edge_map > int(threshold * 255)).astype(np.uint8)
    skel   = skeletonize(binary > 0).astype(np.uint8)

    # --- skeleton → polylines ----------------------------------------------
    graph = sknw.build_sknw(skel)
    polylines = []
    for s, e in graph.edges():
        pts = graph[s][e]['pts']   # Nx2 (row, col) → convert to (x, y)
        if len(pts) >= 2:
            polylines.append(pts[:, ::-1].astype(float))   # col,row → x,y

    if not polylines:
        # fallback: direct edge pixels
        ys, xs = np.where(skel > 0)
        pts_fb = np.column_stack([xs, ys]).astype(float)
        idx    = np.round(np.linspace(0, len(pts_fb)-1, n_dots)).astype(int)
        ordered = pts_fb[idx]
    else:
        # proportional dot allocation by arc length
        arc_lens = []
        for p in polylines:
            d = np.diff(p, axis=0)
            arc_lens.append(float(np.sum(np.hypot(d[:, 0], d[:, 1]))))
        total = max(sum(arc_lens), 1.0)

        resampled = []
        for p, al in zip(polylines, arc_lens):
            k = max(3, int(n_dots * al / total))
            resampled.append(_resample_polyline(p, k))

        chained = _chain_polylines(resampled)
        ordered = _two_opt_crossings(chained, max_iter=80)

    # scale to image size if edges were computed on full res
    dots = ordered.astype(int)
    dots[:, 0] = np.clip(dots[:, 0], 0, W - 1)
    dots[:, 1] = np.clip(dots[:, 1], 0, H - 1)

    # --- render -------------------------------------------------------------
    out = Image.new("RGB", (W, H), "white")
    dr  = ImageDraw.Draw(out)
    fn  = _font(8)
    fn2 = _font(6)

    for i in range(len(dots) - 1):
        x1, y1 = int(dots[i][0]),   int(dots[i][1])
        x2, y2 = int(dots[i+1][0]), int(dots[i+1][1])
        dr.line([(x1, y1), (x2, y2)], fill=(210, 210, 210), width=1)

    for i, (x, y) in enumerate(dots):
        r = 3
        dr.ellipse([x-r, y-r, x+r, y+r], outline=(0, 0, 0), width=1)
        if i % 3 == 0 or i < 20 or i == len(dots)-1:
            fn_use = fn if i < 100 else fn2
            dr.text((x + r + 1, y - r - 1), str(i + 1), fill=(50, 50, 50), font=fn_use)

    return out
