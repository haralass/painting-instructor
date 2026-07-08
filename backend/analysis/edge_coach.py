"""
Edge-control coach — lost, found, soft, hard.

"The eye locks onto the hardest edge in the picture" (Gurney; Richard Schmid).
A beginner outlines everything at equal sharpness, so nothing leads the eye.
This maps every edge by hardness and — the teaching point — relates that to
where the edges *should* be crisp: clustered at the focal subject, dissolving
in the shadow masses and the background. Hard edges away from the focus are
flagged as "competing".

Pure NumPy/OpenCV, deterministic, local. Uses the subject mask when available
to locate the focus; otherwise falls back to the image centre.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


def edge_plan(img: Image.Image, subject_mask: np.ndarray | None = None):
    """
    Returns (overlay_image, notes).

    overlay: edges drawn over a pale base — hard edges warm, soft edges cool —
    so the learner sees their edge hierarchy at a glance.
    notes: short guidance, most useful first (≤4).
    """
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    H, W = rgb.shape[:2]
    gray = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)

    # Edge strength = gradient magnitude; hardness = how abrupt the transition
    # is (normalised gradient), so a crisp boundary scores high, a soft one low.
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    mag_n = mag / (mag.max() + 1e-6)
    edge = mag_n > 0.18                                   # where an edge exists
    hardness = np.clip(mag_n * 1.6, 0, 1)                 # 0 soft .. 1 hard

    # Focus map: subject mask if we have it, else a centred gaussian.
    if subject_mask is not None and subject_mask.shape == (H, W):
        focus = np.clip(subject_mask.astype(np.float32), 0, 1)
    else:
        yy, xx = np.mgrid[0:H, 0:W]
        focus = np.exp(-(((xx - W / 2) / (W * 0.32)) ** 2 + ((yy - H / 2) / (H * 0.32)) ** 2)).astype(np.float32)

    # ── overlay ─────────────────────────────────────────────────────────────
    gray3 = np.repeat(gray[..., None], 3, axis=2)
    base = (0.75 * 255.0 + 0.25 * gray3).astype(np.float32)          # pale paper, 3-channel
    warm = np.array([200, 90, 55], np.float32)     # hard/found edge
    cool = np.array([120, 150, 185], np.float32)   # soft/lost edge
    out = base.copy()
    soft_e = edge & (hardness < 0.5)
    hard_e = edge & (hardness >= 0.5)
    a = hardness[..., None]
    out[soft_e] = (base * (1 - 0.5) + cool * 0.5)[soft_e]
    out[hard_e] = (base * (1 - a) + warm * a)[hard_e]
    overlay = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

    # ── competing-edge diagnosis ────────────────────────────────────────────
    hard_map = (hard_e).astype(np.float32)
    total_hard = float(hard_map.sum()) + 1e-6
    hard_in_focus = float((hard_map * (focus > 0.5)).sum())
    focus_frac = hard_in_focus / total_hard              # share of hard edges on the focus

    notes: list[str] = []
    if focus_frac < 0.45:
        notes.append(
            "Your hard edges are scattered across the picture — the eye has nothing to lock onto. "
            "Keep the crispest edges on the focal subject and soften the rest."
        )
    else:
        notes.append(
            "Good — most of your hard edges sit on the focal subject. Keep the background and shadow "
            "masses soft so they stay back."
        )
    # background hard edges (outside focus) = specific competitors
    competitors = hard_map * (focus < 0.3)
    if competitors.sum() > total_hard * 0.25:
        notes.append(
            "Several hard edges in the background compete with your subject — lose them: soften where "
            "shapes of similar value meet, especially away from the focal point."
        )
    notes.append("Rule of thumb: hard/found edges pull the eye in, soft/lost edges let it rest — spend hard edges only where you want attention.")
    return overlay, notes[:4]
