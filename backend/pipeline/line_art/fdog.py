"""
Coherent Line Drawing — our own implementation of Kang, Lee & Chui (NPAR 2007):
Edge Tangent Flow + Flow-based Difference of Gaussians.

Pure numpy/OpenCV, no ML. The DoG magnitude sketch we shipped first draws
soft graphite strokes; FDoG produces the confident, connected INK lines the
paper is famous for, because the DoG filter is applied perpendicular to a
smoothed flow field and then integrated ALONG it — line responses reinforce
each other along a curve instead of fragmenting.

All sampling is done with cv2.remap over full coordinate grids, so the cost
is a few dozen 1-megapixel remaps — around a second at working resolution.
"""
from __future__ import annotations

import cv2
import numpy as np


def _remap(arr: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    return cv2.remap(
        arr, xs.astype(np.float32), ys.astype(np.float32),
        interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE,
    )


def edge_tangent_flow(gray: np.ndarray, kernel: int = 5, iterations: int = 2) -> np.ndarray:
    """
    Smooth vector field tangent to edges (perpendicular to the gradient).
    Returns (H, W, 2) float32 unit vectors.
    """
    g = gray.astype(np.float32) / 255.0
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=5)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=5)
    mag = np.hypot(gx, gy)
    mag_n = mag / (mag.max() + 1e-8)

    # initial tangent: gradient rotated 90°
    eps = 1e-8
    tx = -gy / (mag + eps)
    ty = gx / (mag + eps)

    H, W = g.shape
    for _ in range(iterations):
        acc_x = np.zeros_like(tx)
        acc_y = np.zeros_like(ty)
        for dy in range(-kernel, kernel + 1):
            for dx in range(-kernel, kernel + 1):
                if dx * dx + dy * dy > kernel * kernel:
                    continue
                ntx = np.roll(np.roll(tx, dy, axis=0), dx, axis=1)
                nty = np.roll(np.roll(ty, dy, axis=0), dx, axis=1)
                nmag = np.roll(np.roll(mag_n, dy, axis=0), dx, axis=1)
                dot = tx * ntx + ty * nty
                phi = np.sign(dot)
                wm = (1.0 + np.tanh(nmag - mag_n)) * 0.5   # magnitude weight
                wd = np.abs(dot)                            # direction weight
                w = phi * wm * wd
                acc_x += ntx * w
                acc_y += nty * w
        norm = np.hypot(acc_x, acc_y) + eps
        tx, ty = acc_x / norm, acc_y / norm

    return np.dstack([tx, ty])


def fdog(
    gray: np.ndarray,
    etf: np.ndarray | None = None,
    sigma_c: float = 1.0,
    rho: float = 0.99,
    sigma_m: float = 3.0,
    tau: float = 0.95,
    phi: float = 120.0,
    iterations: int = 2,
) -> np.ndarray:
    """
    Flow-based DoG. Returns uint8, black ink lines (0) on white (255).

      sigma_c : cross-flow DoG width (line thickness)
      rho     : DoG balance (closer to 1 → cleaner background)
      sigma_m : along-flow integration width (line coherence)
      tau     : ink threshold
      phi     : tanh sharpness — the normalised response lives in ±0.05,
                so without this gain nothing ever crosses the ink threshold
    """
    g = gray.astype(np.float32) / 255.0
    H, W = g.shape
    if etf is None:
        etf = edge_tangent_flow(gray)
    tx, ty = etf[..., 0], etf[..., 1]
    # gradient direction = perpendicular to tangent
    gxd, gyd = -ty, tx

    ys0, xs0 = np.mgrid[0:H, 0:W].astype(np.float32)

    # ── 1. DoG across the flow ────────────────────────────────────────────
    sigma_s = 1.6 * sigma_c
    T = max(2, int(np.ceil(2.0 * sigma_s)))
    centre   = np.zeros_like(g)
    surround = np.zeros_like(g)
    wsum_c = 0.0
    wsum_s = 0.0
    for t in range(-T, T + 1):
        wc = float(np.exp(-(t * t) / (2 * sigma_c * sigma_c)))
        ws = float(np.exp(-(t * t) / (2 * sigma_s * sigma_s)))
        sample = _remap(g, xs0 + gxd * t, ys0 + gyd * t) if t != 0 else g
        centre   += sample * wc
        surround += sample * ws
        wsum_c += wc
        wsum_s += ws
    # Each Gaussian normalised separately (else the wider surround dominates
    # by mass alone and the sign of the response is meaningless).
    resp = centre / wsum_c - rho * surround / wsum_s

    # ── 2. Integrate the response ALONG the flow ─────────────────────────
    S = max(2, int(np.ceil(2.0 * sigma_m)))
    total = resp.copy()
    weight = np.ones_like(g)
    for direction in (1.0, -1.0):
        xs, ys = xs0.copy(), ys0.copy()
        for s in range(1, S + 1):
            vx = _remap(tx, xs, ys) * direction
            vy = _remap(ty, xs, ys) * direction
            xs = xs + vx
            ys = ys + vy
            wm = float(np.exp(-(s * s) / (2 * sigma_m * sigma_m)))
            total += _remap(resp, xs, ys) * wm
            weight += wm
    total /= weight

    # ── 3. Ink threshold (Kang eq. 11) ────────────────────────────────────
    ink = np.where(total > 0, 1.0, 1.0 + np.tanh(phi * total))
    lines = (ink < tau)

    # ── 4. Optional iteration: draw ink into the image and re-run once ───
    for _ in range(iterations - 1):
        g2 = np.where(lines, 0.0, g)
        return fdog((g2 * 255).astype(np.uint8), etf=etf, sigma_c=sigma_c,
                    rho=rho, sigma_m=sigma_m, tau=tau, phi=phi, iterations=1)

    out = np.where(lines, 0, 255).astype(np.uint8)
    # tidy stray single-pixel ink specks
    out = 255 - cv2.morphologyEx(255 - out, cv2.MORPH_OPEN,
                                 np.ones((2, 2), np.uint8))
    return out


def coherent_line_drawing(gray: np.ndarray, max_side: int = 1024) -> np.ndarray:
    """
    Full pipeline at a bounded working resolution. Input uint8 grayscale,
    output uint8 black-on-white line drawing at the ORIGINAL size.
    """
    H, W = gray.shape
    scale = min(1.0, max_side / max(H, W))
    work = cv2.resize(gray, (int(W * scale), int(H * scale)),
                      interpolation=cv2.INTER_AREA) if scale < 1.0 else gray

    smooth = cv2.bilateralFilter(work, 7, 35, 7)
    lines = fdog(smooth)

    if lines.shape != (H, W):
        lines = cv2.resize(lines, (W, H), interpolation=cv2.INTER_LINEAR)
        _, lines = cv2.threshold(lines, 160, 255, cv2.THRESH_BINARY)
    return lines
