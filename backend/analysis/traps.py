"""
Perceptual "traps" — where the eye will misjudge value before you paint.

Simultaneous contrast (Albers; Munsell value constancy) is the #1 perceptual
failure in painting: a value looks darker against a light surround and lighter
against a dark one, so the learner paints the *apparent* value, not the true
one. This flags, ahead of time, the spots where local contrast is strong enough
to fool the eye — "this shadow looks black next to the sky, but it's a mid
value; you will paint it too dark."

Pure NumPy/OpenCV, deterministic, local — computed from the image's own
luminance against its local surround. Returns a teaching overlay plus a few
plain-language warnings tied to image locations.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


def _loc_word(nx: float, ny: float) -> str:
    v = "top" if ny < 0.34 else "bottom" if ny > 0.66 else "middle"
    h = "left" if nx < 0.34 else "right" if nx > 0.66 else "centre"
    if v == "middle" and h == "centre":
        return "centre"
    return f"{v}-{h}" if h != "centre" else v


def value_traps(img: Image.Image, strength: float = 0.18):
    """
    Detect simultaneous-contrast value traps.

    Returns (overlay_image, notes) where overlay is a PIL image with the trap
    zones flagged over a desaturated base, and notes is a list of short
    warnings (most severe first, ≤4).
    """
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    H, W = rgb.shape[:2]
    lab_L = cv2.cvtColor((rgb / 255.0).astype(np.float32), cv2.COLOR_RGB2LAB)[..., 0]  # 0..100

    # Local surround = large-radius blur; the eye exaggerates the difference
    # between a region and this surround (simultaneous contrast).
    r = max(9, int(round(min(H, W) * 0.08)) | 1)
    surround = cv2.GaussianBlur(lab_L, (r, r), 0)
    contrast = lab_L - surround                      # + = looks lighter than it is
    trap = np.abs(contrast) / 100.0                  # 0..~1 severity

    # A trap zone is where local contrast is strong AND the region is a
    # reasonable size (smooth it so speckle doesn't count).
    trap_s = cv2.GaussianBlur(trap, (r, r), 0)
    mask = trap_s > strength

    # ── overlay: desaturated base, trap zones tinted (blue=will-read-too-dark,
    #    warm=will-read-too-light), so the learner sees where to distrust the eye
    gray = lab_L / 100.0 * 255.0
    base = (0.5 * rgb + 0.5 * gray[..., None]).astype(np.float32)
    too_light = (contrast > 0) & mask                 # sits on dark surround → over-lighten
    too_dark = (contrast < 0) & mask                  # sits on light surround → over-darken
    warm = np.array([210, 150, 110], np.float32)
    cool = np.array([90, 130, 200], np.float32)
    out = base.copy()
    out[too_light] = 0.55 * base[too_light] + 0.45 * warm
    out[too_dark] = 0.55 * base[too_dark] + 0.45 * cool
    overlay = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    # ── notes: pick the few strongest connected trap blobs ──────────────────
    notes: list[str] = []
    sev = trap_s * mask
    m8 = (mask * 255).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(m8, connectivity=8)
    blobs = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < H * W * 0.004:
            continue
        cx, cy = centroids[i]
        region = labels == i
        mean_contrast = float(contrast[region].mean())
        blobs.append((float(sev[region].mean()) * area, cx / W, cy / H, mean_contrast, area / (H * W)))
    blobs.sort(reverse=True)
    for _, nx, ny, mc, frac in blobs[:4]:
        where = _loc_word(nx, ny)
        if mc < 0:
            notes.append(
                f"Trap in the {where}: this shape sits against a lighter surround, so it looks darker "
                f"than it is — you'll paint it too dark. Judge its value against the whole picture, not its neighbour."
            )
        else:
            notes.append(
                f"Trap in the {where}: this shape sits against a darker surround, so it looks lighter "
                f"than it is — you'll paint it too light. Squint and compare it to your lightest light."
            )
    return overlay, notes
