"""
Focal competition — does the picture have one centre, or several fighting?

Every strong picture leads the eye to one place. Beginners spread contrast,
detail and saturation everywhere, so the composition has "two centres" that
compete. This locates the image's actual attention hotspots (local contrast ×
edge density × saturation), checks whether they agree with the intended subject
and land near a rule-of-thirds sweet spot, and flags competitors.

Pure NumPy/OpenCV, deterministic, local. Uses the subject mask when available
to know the intended focus.
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
    return "centre" if (v == "middle" and h == "centre") else (f"{v}-{h}" if h != "centre" else v)


def focal_competition(img: Image.Image, subject_mask: np.ndarray | None = None):
    """Returns (overlay_image, notes) diagnosing the focal hierarchy."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    H, W = rgb.shape[:2]
    lab = cv2.cvtColor((rgb / 255.0).astype(np.float32), cv2.COLOR_RGB2LAB)
    L, a, b = lab[..., 0] / 100.0, lab[..., 1], lab[..., 2]

    # Attention = local value contrast × edge density × chroma, blurred to blobs.
    k = max(9, int(round(min(H, W) * 0.06)) | 1)
    local_mean = cv2.blur(L, (k, k))
    contrast = np.abs(L - local_mean)
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    edges = cv2.blur((np.hypot(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3),
                               cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))), (k, k))
    edges /= edges.max() + 1e-6
    chroma = np.sqrt(a * a + b * b)
    chroma /= chroma.max() + 1e-6
    attention = cv2.GaussianBlur((contrast / (contrast.max() + 1e-6)) * 0.5 + edges * 0.3 + chroma * 0.2, (k, k), 0)

    # Peaks: the global max, plus any secondary peak that's both strong and far.
    amax = float(attention.max()) + 1e-6
    att_n = attention / amax
    _, _, _, maxloc = cv2.minMaxLoc(attention)
    fx, fy = maxloc[0] / W, maxloc[1] / H

    # secondary competitor: strongest point outside a radius of the primary
    yy, xx = np.mgrid[0:H, 0:W]
    far = ((xx - maxloc[0]) ** 2 + (yy - maxloc[1]) ** 2) > (min(H, W) * 0.33) ** 2
    comp_val, comp_xy = 0.0, None
    if far.any():
        masked = np.where(far, att_n, 0)
        cv_val = float(masked.max())
        cyx = np.unravel_index(int(masked.argmax()), masked.shape)
        comp_val, comp_xy = cv_val, (cyx[1] / W, cyx[0] / H)

    # rule-of-thirds sweet spots
    thirds = [(x, y) for x in (1 / 3, 2 / 3) for y in (1 / 3, 2 / 3)]
    d_third = min(np.hypot(fx - tx, fy - ty) for tx, ty in thirds)

    # ── overlay: thirds grid + primary (warm ring) + competitor (cool ring) ──
    over = (0.55 * rgb + 0.45 * (gray[..., None])).astype(np.uint8).copy()
    for gx in (W // 3, 2 * W // 3):
        over[:, gx:gx + 1] = (210, 180, 120)
    for gy in (H // 3, 2 * H // 3):
        over[gy:gy + 1, :] = (210, 180, 120)
    cv2.circle(over, maxloc, int(min(H, W) * 0.06), (210, 90, 55), 4)
    if comp_xy and comp_val > 0.6:
        cv2.circle(over, (int(comp_xy[0] * W), int(comp_xy[1] * H)), int(min(H, W) * 0.05), (90, 130, 200), 4)
    overlay = Image.fromarray(over)

    # ── notes ────────────────────────────────────────────────────────────────
    notes: list[str] = []
    if comp_xy and comp_val > 0.6:
        notes.append(
            f"Two competing centres: your strongest pull is the {_loc_word(fx, fy)}, but there's a rival in the "
            f"{_loc_word(*comp_xy)}. Subdue one — drop its contrast, detail or saturation — so a single focal point wins."
        )
    else:
        notes.append(f"One clear focal point (the {_loc_word(fx, fy)}) — good, the eye knows where to go.")
    if subject_mask is not None and subject_mask.shape == (H, W):
        sm = subject_mask > 0.5
        if sm.any():
            sy, sx = np.argwhere(sm).mean(axis=0)
            if np.hypot(fx - sx / W, fy - sy / H) > 0.25:
                notes.append(
                    f"Your strongest contrast isn't on the subject — the eye is pulled to the {_loc_word(fx, fy)} "
                    f"instead of the {_loc_word(sx / W, sy / H)}. Put your hardest, highest-contrast note on the subject."
                )
    notes.append(
        ("The focal point sits near a rule-of-thirds sweet spot — strong placement."
         if d_third < 0.12 else
         "The focal point is near the centre/edge — nudging it toward a third often makes a livelier composition.")
    )
    return overlay, notes[:4]
