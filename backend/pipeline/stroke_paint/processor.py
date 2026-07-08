from __future__ import annotations
"""
Stroke-by-stroke oil-painting time-lapse renderer (CPU-only, classical CV).

Our own reimplementation of the pipeline behind Im2Oil (Tong et al.) — studied,
not copied (that repo ships no LICENSE). The three classical ingredients:

  1. Edge-Tangent-Flow (ETF) direction field
       Sobel gradients -> smoothed structure tensor -> the minor eigenvector
       gives the local *tangent* (edge-following) direction. Strokes are laid
       ALONG this field so paint follows form, exactly like a painter dragging
       the brush along a contour instead of across it.

  2. Importance / density anchor sampling
       A detail map (gradient magnitude + local variance) drives how many
       stroke anchors land where: many small strokes in busy/detailed areas,
       few big strokes over flat regions. Anchors are drawn by weighted
       rejection sampling with a soft minimum spacing (a cheap Poisson-disk /
       Voronoi stand-in) so they spread out instead of clumping.

  3. Oriented tapered brush stamps
       Each anchor becomes a soft elliptical brush dab (see brush.py), rotated
       to the local ETF angle, tinted with the reference colour under the
       anchor, and alpha-composited onto a blank paper canvas. NO white edge /
       outline layer is ever drawn (Im2Oil's contour overlay is deliberately
       omitted).

Stroke ORDER is the teaching payload: big / low-detail / background strokes are
painted FIRST and small / high-detail strokes LAST, so the emitted frames read
as blank -> block-in -> refinement. If `stage_masks` is supplied (e.g. a notan /
value-zone map), strokes are additionally bucketed by it (background/dark masses
before foreground/light accents); otherwise ordering falls back to stroke size,
large -> small, like Im2Oil's default.

Everything runs on the CPU with numpy + OpenCV; work is downscaled internally
and the anchor budget is capped so a single render stays well under a minute.
"""

import math
import time

import cv2
import numpy as np
from PIL import Image

from .brush import make_brush

# ── internal budget / look knobs ──────────────────────────────────────────────
_MAX_DIM = 640          # longest internal working edge (px); output upscaled after
_SS = 2                 # super-sampling factor for smoother stamp edges
_MIN_ANCHORS = 500
_MAX_ANCHORS = 6000
_ANCHOR_DENSITY = 0.045  # target anchors per working pixel (before detail weighting)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Edge-Tangent-Flow direction field
# ══════════════════════════════════════════════════════════════════════════════
def _etf_angle(gray: np.ndarray, smooth_sigma: float = 4.0) -> np.ndarray:
    """
    Return per-pixel stroke angle in RADIANS (the edge-*tangent* direction).

    Structure-tensor method: form J = [[gx^2, gxgy], [gxgy, gy^2]], Gaussian-blur
    its components (this is what turns raw gradients into a coherent flow field),
    then take the eigenvector of the SMALLER eigenvalue — that is the direction
    of least intensity change, i.e. along edges / form. Strokes follow it.
    """
    g = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=5)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=5)

    jxx = cv2.GaussianBlur(gx * gx, (0, 0), smooth_sigma)
    jyy = cv2.GaussianBlur(gy * gy, (0, 0), smooth_sigma)
    jxy = cv2.GaussianBlur(gx * gy, (0, 0), smooth_sigma)

    # Minor-eigenvector orientation of the 2x2 structure tensor.
    # theta_major = 0.5 * atan2(2*Jxy, Jxx - Jyy) points along max change;
    # add 90 deg to get the tangent (min change / edge-following) direction.
    theta_major = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy)
    tangent = theta_major + math.pi / 2.0
    return tangent.astype(np.float32)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Importance / density map + anchor sampling
# ══════════════════════════════════════════════════════════════════════════════
def _detail_map(gray: np.ndarray) -> np.ndarray:
    """Normalised [0,1] detail/importance map: high where there is edge energy
    and local texture, low over flat regions."""
    g = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(gx * gx + gy * gy)

    mean = cv2.blur(g, (7, 7))
    var = cv2.blur(g * g, (7, 7)) - mean * mean
    var = np.clip(var, 0, None)

    detail = grad + 2.0 * np.sqrt(var)
    detail = cv2.GaussianBlur(detail, (0, 0), 1.5)
    m = detail.max()
    if m > 1e-6:
        detail /= m
    return detail.astype(np.float32)


def _sample_anchors(
    detail: np.ndarray, n_target: int, rng: np.random.Generator
) -> np.ndarray:
    """
    Weighted rejection sampling of anchor points with soft minimum spacing.

    Probability of keeping a candidate scales with the local detail value, so
    detailed regions accrue many (small) strokes and flat regions get a sparse
    scatter of (large) strokes. A coarse occupancy grid enforces a rough
    Poisson-disk spacing so anchors spread instead of piling up — a cheap
    stand-in for Im2Oil's Voronoi/K-means stipple relaxation.

    Returns int array of (y, x), shape (N, 2).
    """
    h, w = detail.shape
    # floor so even flat areas get some coverage for the block-in
    weight = 0.15 + 0.85 * detail
    weight_flat = weight.ravel()
    weight_flat = weight_flat / weight_flat.sum()

    n_candidates = int(n_target * 4)
    idx = rng.choice(weight_flat.size, size=n_candidates, replace=True, p=weight_flat)
    ys = (idx // w).astype(np.int32)
    xs = (idx % w).astype(np.int32)

    # spacing tied to how many anchors we want across the canvas
    spacing = max(2.0, 0.55 * math.sqrt((h * w) / max(1, n_target)))
    cell = max(1, int(spacing))
    gh, gw = h // cell + 1, w // cell + 1
    occupied = np.zeros((gh, gw), dtype=bool)

    kept = []
    for y, x in zip(ys, xs):
        cy, cx = y // cell, x // cell
        if occupied[cy, cx]:
            continue
        occupied[cy, cx] = True
        kept.append((y, x))
        if len(kept) >= n_target:
            break

    if not kept:  # degenerate fallback
        return np.array([[h // 2, w // 2]], dtype=np.int32)
    return np.array(kept, dtype=np.int32)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Stroke construction + ordering
# ══════════════════════════════════════════════════════════════════════════════
def _build_strokes(
    anchors: np.ndarray,
    angle: np.ndarray,
    detail: np.ndarray,
    color: np.ndarray,
    stage_masks: dict | np.ndarray | None,
    rng: np.random.Generator,
) -> list[dict]:
    """
    Turn anchors into stroke dicts and return them in PAINT ORDER.

    Stroke size is inversely tied to local detail (big strokes on flat areas,
    small strokes on detail). Ordering keys, primary first:
      * stage bucket   — from stage_masks if given (low value / background first)
      * size           — large strokes before small
    so the animation blocks in big masses, then refines with small strokes.
    """
    h, w = detail.shape

    # stage bucket per anchor (lower bucket => painted earlier)
    stage_bucket = _stage_bucket_for(anchors, stage_masks, h, w)

    strokes: list[dict] = []
    for i, (y, x) in enumerate(anchors):
        d = float(detail[y, x])
        # size: flat area (d~0) -> long/wide; detailed (d~1) -> short/narrow
        base = 3.0 + 26.0 * (1.0 - d) ** 1.5
        length = base * (0.9 + 0.2 * rng.random())
        width = max(2.5, base * (0.32 + 0.10 * rng.random()))
        strokes.append(
            {
                "y": int(y),
                "x": int(x),
                "angle": float(angle[y, x]),
                "length": float(length),
                "width": float(width),
                "size": float(length * width),
                "color": color[y, x].astype(np.float32),  # RGB
                "stage": int(stage_bucket[i]),
                "seed": int(rng.integers(0, 1 << 30)),
            }
        )

    # Paint order: earlier stage first, then largest-first within a stage.
    strokes.sort(key=lambda s: (s["stage"], -s["size"]))
    return strokes


def _stage_bucket_for(
    anchors: np.ndarray, stage_masks: dict | np.ndarray | None, h: int, w: int
) -> np.ndarray:
    """
    Map each anchor to an integer paint-stage bucket (lower = earlier).

    Accepts either:
      * a single-channel array (e.g. a notan / value map) — bucketed by value,
        DARK masses painted first (they are usually the big background shapes);
      * a dict of {order: mask-array}, painted in ascending key order;
      * None — everyone in bucket 0 (pure size ordering then takes over).
    """
    n = len(anchors)
    if stage_masks is None:
        return np.zeros(n, dtype=np.int32)

    # dict of ordered masks
    if isinstance(stage_masks, dict):
        buckets = np.zeros(n, dtype=np.int32)
        assigned = np.zeros(n, dtype=bool)
        for order in sorted(stage_masks.keys()):
            m = _as_gray_array(stage_masks[order], h, w)
            if m is None:
                continue
            hit = m[anchors[:, 0], anchors[:, 1]] > 127
            new = hit & ~assigned
            buckets[new] = order
            assigned |= hit
        return buckets

    # single array -> value buckets (dark first)
    m = _as_gray_array(stage_masks, h, w)
    if m is None:
        return np.zeros(n, dtype=np.int32)
    vals = m[anchors[:, 0], anchors[:, 1]].astype(np.float32)
    # 4 value bands, darkest -> bucket 0
    return np.clip((vals / 64.0).astype(np.int32), 0, 3)


def _as_gray_array(obj, h: int, w: int) -> np.ndarray | None:
    """Coerce a PIL image or ndarray to a HxW uint8 gray array at (h, w)."""
    if obj is None:
        return None
    if isinstance(obj, Image.Image):
        arr = np.array(obj.convert("L"))
    else:
        arr = np.asarray(obj)
        if arr.ndim == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    if arr.shape[:2] != (h, w):
        arr = cv2.resize(arr, (w, h), interpolation=cv2.INTER_NEAREST)
    return arr.astype(np.uint8)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Rendering / compositing
# ══════════════════════════════════════════════════════════════════════════════
def _stamp(canvas: np.ndarray, stroke: dict) -> None:
    """
    Alpha-composite one oriented brush dab onto `canvas` (RGB float32) in place.

    canvas is at super-sampled resolution (_SS x working size).
    """
    length = max(3, int(round(stroke["length"] * _SS)))
    width = max(3, int(round(stroke["width"] * _SS)))
    brush = make_brush(length, width, seed=stroke["seed"])

    # rotate stamp to the ETF angle (degrees, CCW; image y is down so negate)
    deg = -math.degrees(stroke["angle"])
    (bh, bw) = brush.shape
    M = cv2.getRotationMatrix2D((bw / 2.0, bh / 2.0), deg, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nw = int(bh * sin + bw * cos)
    nh = int(bh * cos + bw * sin)
    M[0, 2] += nw / 2.0 - bw / 2.0
    M[1, 2] += nh / 2.0 - bh / 2.0
    rot = cv2.warpAffine(brush, M, (nw, nh), flags=cv2.INTER_LINEAR, borderValue=0.0)

    cy = int(round(stroke["y"] * _SS))
    cx = int(round(stroke["x"] * _SS))
    H, W = canvas.shape[:2]
    y0, y1 = cy - nh // 2, cy - nh // 2 + nh
    x0, x1 = cx - nw // 2, cx - nw // 2 + nw

    # clip to canvas
    sy0, sx0 = max(0, -y0), max(0, -x0)
    dy0, dx0 = max(0, y0), max(0, x0)
    dy1, dx1 = min(H, y1), min(W, x1)
    if dy1 <= dy0 or dx1 <= dx0:
        return
    a = rot[sy0 : sy0 + (dy1 - dy0), sx0 : sx0 + (dx1 - dx0)][:, :, None]
    col = stroke["color"][None, None, :]
    region = canvas[dy0:dy1, dx0:dx1]
    canvas[dy0:dy1, dx0:dx1] = region * (1.0 - a) + col * a


def _downscale(canvas_ss: np.ndarray, out_size: tuple[int, int]) -> Image.Image:
    """Super-sampled float canvas -> antialiased PIL RGB at out_size (W, H)."""
    arr = np.clip(canvas_ss, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    if img.size != out_size:
        img = img.resize(out_size, Image.LANCZOS)
    return img


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════
def render_stroke_frames(
    img: Image.Image,
    stage_masks: dict | np.ndarray | None = None,
    max_frames: int = 60,
    seed: int = 0,
) -> list[Image.Image]:
    """
    Render a stroke-by-stroke oil-painting time-lapse of `img`.

    Args:
        img:         reference PIL image.
        stage_masks: optional stroke-ordering hint — either a single value/notan
                     map (dark masses painted first) or a {order: mask} dict
                     (painted in ascending order). None -> size ordering only.
        max_frames:  approximate number of frames to emit (blank -> finished),
                     evenly spaced by stroke count.
        seed:        RNG seed for reproducibility.

    Returns:
        List of PIL RGB images: frame 0 is the blank paper canvas, the last is
        the finished painting, with visible oriented strokes and NO outline.
    """
    rng = np.random.default_rng(seed)
    orig = img.convert("RGB")
    out_size = orig.size  # (W, H) to return at

    # ── downscale to the internal working resolution ──────────────────────────
    W0, H0 = orig.size
    scale = min(1.0, _MAX_DIM / max(W0, H0))
    wW, wH = max(16, int(W0 * scale)), max(16, int(H0 * scale))
    work = orig.resize((wW, wH), Image.LANCZOS)
    color = np.array(work, dtype=np.float32)                # HxWx3 RGB
    gray = cv2.cvtColor(np.array(work), cv2.COLOR_RGB2GRAY)

    # ── ETF field + detail map ────────────────────────────────────────────────
    angle = _etf_angle(gray)
    detail = _detail_map(gray)

    # ── anchor budget scaled by area, capped for cost ─────────────────────────
    n_target = int(_ANCHOR_DENSITY * wW * wH)
    n_target = int(np.clip(n_target, _MIN_ANCHORS, _MAX_ANCHORS))
    anchors = _sample_anchors(detail, n_target, rng)

    # ── build ordered strokes ─────────────────────────────────────────────────
    strokes = _build_strokes(anchors, angle, detail, color, stage_masks, rng)
    n = len(strokes)

    # ── paper canvas: warm off-white ground (NO outline layer) ────────────────
    canvas = np.empty((wH * _SS, wW * _SS, 3), dtype=np.float32)
    canvas[:] = np.array([246.0, 243.0, 236.0], dtype=np.float32)

    # frame schedule: which stroke-count checkpoints to snapshot
    n_frames = max(2, min(max_frames, n + 1))
    checkpoints = sorted(set(int(round(t)) for t in np.linspace(0, n, n_frames)))

    frames: list[Image.Image] = []
    next_ckpt = iter(checkpoints)
    target = next(next_ckpt)
    for i in range(n + 1):
        while i == target:
            frames.append(_downscale(canvas, out_size))
            target = next(next_ckpt, None)
            if target is None:
                break
        if target is None:
            break
        if i < n:
            _stamp(canvas, strokes[i])

    # guarantee a final finished frame
    if not frames or frames[-1] is None:
        frames.append(_downscale(canvas, out_size))
    return frames


def _self_test(image_path: str, out_dir: str) -> None:
    """Standalone smoke test: render frames and dump a few PNGs."""
    import os

    os.makedirs(out_dir, exist_ok=True)
    im = Image.open(image_path)
    t0 = time.perf_counter()
    frames = render_stroke_frames(im, max_frames=40)
    dt = time.perf_counter() - t0
    print(f"{len(frames)} frames in {dt:.2f}s  ({dt / max(1,len(frames)):.3f}s/frame)")
    picks = [0, len(frames) // 3, 2 * len(frames) // 3, len(frames) - 1]
    for p in picks:
        path = os.path.join(out_dir, f"stroke_frame_{p:03d}.png")
        frames[p].save(path)
        print("saved", path)


if __name__ == "__main__":
    import sys

    _self_test(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "./_stroke_out")
