"""
Vanishing-point detection for composition teaching — classical Hough +
RANSAC over line intersections (approach after Lu et al. / XiaohuLuVPDetection,
MIT; reimplemented on OpenCV primitives).

Deliberately conservative: a vanishing point is only reported when many
independent structural lines genuinely converge. A wrong perspective note is
worse than none — same honesty contract as the diffuse-light detection.
"""
from __future__ import annotations

import numpy as np
import cv2


def detect_vanishing_point(gray: np.ndarray) -> dict | None:
    """
    Returns {"x", "y" (image coords, may lie outside the frame),
             "nx", "ny" (normalised, clamped to [0,1] for location words),
             "n_lines"} or None when no convincing convergence exists.
    """
    H, W = gray.shape[:2]
    diag = float(np.hypot(H, W))

    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 140)
    raw = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=60,
        minLineLength=int(diag * 0.08), maxLineGap=int(diag * 0.01),
    )
    if raw is None or len(raw) < 8:
        return None

    # Keep genuinely oblique lines: horizontals are parallel to the horizon
    # and verticals are parallel to gravity — neither pins an interior VP.
    lines = []
    for x1, y1, x2, y2 in raw.reshape(-1, 4):
        ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180
        if min(ang, 180 - ang) < 8 or abs(ang - 90) < 8:
            continue
        lines.append((float(x1), float(y1), float(x2), float(y2)))
    if len(lines) < 6:
        return None

    # Homogeneous line equations for fast point-line distances
    eqs = []
    for x1, y1, x2, y2 in lines:
        a, b = y2 - y1, x1 - x2
        c = -(a * x1 + b * y1)
        n = np.hypot(a, b)
        eqs.append((a / n, b / n, c / n))
    eqs = np.array(eqs)          # (N, 3)
    n_lines = len(lines)

    # RANSAC over pairwise intersections
    rng = np.random.default_rng(0)
    tol = diag * 0.03
    best_count, best_pt = 0, None
    for _ in range(min(400, n_lines * (n_lines - 1) // 2)):
        i, j = rng.choice(n_lines, size=2, replace=False)
        cross = np.cross(
            (eqs[i][0], eqs[i][1], eqs[i][2]),
            (eqs[j][0], eqs[j][1], eqs[j][2]),
        )
        if abs(cross[2]) < 1e-9:
            continue   # parallel
        px, py = cross[0] / cross[2], cross[1] / cross[2]
        # a VP wildly outside the frame teaches nothing usable
        if not (-0.6 * W <= px <= 1.6 * W and -0.6 * H <= py <= 1.6 * H):
            continue
        d = np.abs(eqs[:, 0] * px + eqs[:, 1] * py + eqs[:, 2])
        count = int((d < tol).sum())
        if count > best_count:
            best_count, best_pt = count, (px, py)

    # Require real consensus: at least 6 lines AND a third of the oblique set
    if best_pt is None or best_count < max(6, n_lines // 3):
        return None

    px, py = best_pt
    return {
        "x": round(px, 1), "y": round(py, 1),
        "nx": round(float(np.clip(px / W, 0, 1)), 3),
        "ny": round(float(np.clip(py / H, 0, 1)), 3),
        "n_lines": best_count,
    }
