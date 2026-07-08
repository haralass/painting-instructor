"""
Local colour vs light — a classical intrinsic-image split.

Gurney's central lesson: "local colour" (the object's own colour) is a myth in
isolation — what you see is that colour *under* the light. This separates the
two so a learner can see it: the smooth, edge-preserving large-scale luminance
is treated as **shading** (the light), and dividing it out leaves **albedo**
(the local colour, lighting removed) — the true mixing target.

This is the classic Retinex / edge-preserving-smoothing route (all NumPy +
OpenCV, milliseconds, no model, no paid API) — we deliberately do NOT ship the
heavy patented deep intrinsic-decomposition network; for a teaching aid this
approximation is more than enough and stays local.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

_EPS = 1e-4


def albedo_shading(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """
    Split ``img`` into (albedo_rgb, shading) float arrays in [0, 1].

    albedo_rgb : (H, W, 3) local colour with the light divided out.
    shading    : (H, W)    the smooth light field (grayscale).
    """
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    lum = np.clip(lum, _EPS, 1.0)

    # Edge-preserving large-scale luminance = the illumination (shading). A
    # bilateral filter on log-luminance keeps material boundaries crisp so the
    # albedo doesn't bleed colour across edges, unlike a plain Gaussian.
    log_lum = np.log(lum).astype(np.float32)
    d = max(5, int(round(min(rgb.shape[:2]) * 0.02)) | 1)
    shading_log = cv2.bilateralFilter(log_lum, d=d, sigmaColor=0.4, sigmaSpace=d)
    shading = np.exp(shading_log)
    shading = np.clip(shading / max(float(shading.max()), _EPS), _EPS, 1.0)

    # Divide the light out; renormalise by a high percentile so the albedo
    # plate uses the full range without a few speculars blowing it out.
    albedo = rgb / shading[..., None]
    hi = float(np.percentile(albedo, 99)) or 1.0
    albedo = np.clip(albedo / hi, 0.0, 1.0)
    return albedo, shading


def local_vs_light_page(img: Image.Image) -> Image.Image:
    """
    Side-by-side teaching plate: local colour (albedo) | the light (shading),
    with a thin divider — "this shadow isn't a different colour, it's the same
    colour under less light."
    """
    albedo, shading = albedo_shading(img)
    left = (albedo * 255).astype(np.uint8)
    right = np.repeat((shading * 255).astype(np.uint8)[..., None], 3, axis=2)
    h, w = left.shape[:2]
    div = 3
    out = np.empty((h, w * 2 + div, 3), dtype=np.uint8)
    out[:, :w] = left
    out[:, w:w + div] = np.array([180, 140, 90], np.uint8)  # ochre divider
    out[:, w + div:] = right
    return Image.fromarray(out)
