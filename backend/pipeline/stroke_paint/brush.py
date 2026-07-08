from __future__ import annotations
"""
Procedural soft brush stamp.

A brush stamp is a single-channel float32 alpha mask in [0, 1] shaped like an
oriented, tapered oil-brush dab: an elongated ellipse whose alpha falls off
softly toward the edges and tapers to near-zero at the two ends, so overlapping
strokes read as bristly paint rather than hard blobs. Purely computed — no
external image asset — so the pipeline stays dependency-light and deterministic.

This is our own reimplementation of the *idea* behind Im2Oil's brush template
(an oriented, alpha-tapered stamp); no code or asset is copied from it.
"""

import numpy as np

# Cache of base (unrotated, unit-ish) brush stamps keyed by (length, width, seed).
_CACHE: dict[tuple, np.ndarray] = {}


def make_brush(length: int, width: int, seed: int = 0) -> np.ndarray:
    """
    Build a horizontal (major axis along +x) soft brush alpha stamp.

    Args:
        length: stamp length in px (major axis, >= 3).
        width:  stamp width in px  (minor axis, >= 3).
        seed:   varies the fine bristle texture between strokes.

    Returns:
        float32 array (H=width, W=length), alpha in [0, 1].
    """
    length = max(3, int(length))
    width = max(3, int(width))
    key = (length, width, seed % 8)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    ys = np.linspace(-1.0, 1.0, width, dtype=np.float32)[:, None]   # across width
    xs = np.linspace(-1.0, 1.0, length, dtype=np.float32)[None, :]  # along length

    # Elliptical falloff: 1 at centre -> 0 at the rim.
    rr = xs * xs + ys * ys
    alpha = 1.0 - rr
    alpha = np.clip(alpha, 0.0, 1.0)

    # Soft, slightly super-linear edge so the dab has a soft shoulder.
    alpha = alpha ** 0.9

    # Longitudinal taper: fade the two tips of the stroke a bit more so the
    # dab reads as a brush stroke with lifted ends rather than a fat ellipse.
    tip = 1.0 - 0.35 * (np.abs(xs) ** 3)
    alpha *= np.clip(tip, 0.0, 1.0)

    # Faint lengthwise bristle streaks -> the characteristic dragged-paint look.
    rng = np.random.default_rng(seed)
    n_streaks = max(3, width)
    streaks = 0.85 + 0.15 * rng.random(n_streaks, dtype=np.float32)
    streaks = np.interp(
        np.linspace(0, n_streaks - 1, width),
        np.arange(n_streaks),
        streaks,
    ).astype(np.float32)[:, None]
    alpha *= streaks

    alpha = np.clip(alpha, 0.0, 1.0).astype(np.float32)
    _CACHE[key] = alpha
    return alpha
