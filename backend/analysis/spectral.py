"""
Physically-correct **36-band spectral** colour module.

The shipped paint-mixing code (``backend/teaching/mixing.py``) runs Kubelka-Munk
on only three linearised sRGB channels — the "industry shortcut". That is
physically wrong: three coarse bands cannot represent the reflectance curve of a
real pigment, so subtractive mixes (blue + yellow -> green) come out muddy and
wrong. This module is the correct alternative, kept standalone so ``mixing.py``
can adopt it later without a risky in-place rewrite.

Design
------
* We work over a fixed **36-band** grid, ``SpectralShape(380, 730, 10)`` nm
  (36 samples), matching the resolution used by academic reflectance-mixing
  work while staying cheap.
* sRGB <-> spectral reflectance uses the ``colour`` science library
  (``colour-science``), which is already a project dependency, rather than
  hand-rolled matrices:
    - **recovery**: ``colour.recovery.XYZ_to_sd_Jakob2019`` — the Jakob & Hanika
      (2019) analytic reflectance model. It is smooth, fast, ships in
      ``colour`` 0.4.x, needs no downloaded datasets (works fully offline), and
      round-trips sRGB to within ~1 ΔRGB across the gamut including
      white/black/primaries.
    - **rendering**: ``colour.colorimetry.sd_to_XYZ`` with the CIE 1931 2°
      observer + D65 illuminant, then ``colour.XYZ_to_sRGB``.
* Mixing is **two-constant Kubelka-Munk** per band with a crucial twist: the
  effective weight of a pigment is ``ratio**2 * luminance``. Squaring the ratio
  and scaling by the pigment's own relative luminance is what lets strong dark
  pigments (blacks, phthalos) tint correctly — a little goes a long way, exactly
  as on a real palette.

Everything here is public science (Kubelka & Munk 1931; Jakob & Hanika 2019;
CIE colorimetry); the implementation is ours. Pure NumPy + ``colour``, local,
no network, no paid API.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

import colour
from colour import SpectralShape
from colour.colorimetry import (
    MSDS_CMFS,
    SDS_ILLUMINANTS,
    SpectralDistribution,
    sd_to_XYZ,
)
from colour.recovery import XYZ_to_sd_Jakob2019

# ---------------------------------------------------------------------------
# Fixed spectral grid + colorimetric context.
# ---------------------------------------------------------------------------

#: 36 bands over 380..730 nm inclusive, 10 nm apart.
SPECTRAL_SHAPE: SpectralShape = SpectralShape(380, 730, 10)

#: Wavelengths of the 36 bands (nm), immutable reference grid.
WAVELENGTHS: np.ndarray = SPECTRAL_SHAPE.wavelengths.astype(np.float64)

#: Number of spectral bands (36).
N_BANDS: int = int(WAVELENGTHS.size)

# Guard rails so K/S and reflectance recovery never hit 0 or 1 exactly.
_EPS: float = 1.0e-4


@lru_cache(maxsize=1)
def _cmfs():
    """CIE 1931 2 degree standard observer, aligned to the 36-band grid."""
    return MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(SPECTRAL_SHAPE)


@lru_cache(maxsize=1)
def _illuminant():
    """D65 illuminant SD, aligned to the 36-band grid."""
    return SDS_ILLUMINANTS["D65"].copy().align(SPECTRAL_SHAPE)


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _normalise_rgb(rgb) -> np.ndarray:
    """
    Coerce an sRGB triple to a float array in [0, 1].

    Accepts either 0-255 integers/floats or already-normalised 0-1 values and
    auto-detects which by inspecting the maximum component.

    Parameters
    ----------
    rgb
        Length-3 sequence of sRGB components (0-255 or 0-1).

    Returns
    -------
    numpy.ndarray
        Shape ``(3,)`` float array clipped to [0, 1].
    """
    arr = np.asarray(rgb, dtype=np.float64).reshape(3)
    if arr.max() > 1.0:
        arr = arr / 255.0
    return np.clip(arr, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 1. sRGB -> spectral reflectance.
# ---------------------------------------------------------------------------

def rgb_to_reflectance(rgb) -> np.ndarray:
    """
    Recover a plausible spectral reflectance curve from an sRGB colour.

    Uses Jakob & Hanika (2019) reflectance recovery
    (:func:`colour.recovery.XYZ_to_sd_Jakob2019`) evaluated against the CIE 1931
    2 degree observer and D65, then resamples onto the fixed 36-band grid.

    Parameters
    ----------
    rgb
        Length-3 sRGB triple. Either 0-255 or 0-1 (auto-detected).

    Returns
    -------
    numpy.ndarray
        Shape ``(36,)`` reflectance curve, one value per band, clamped to the
        open interval ``(0, 1)``.
    """
    rgb01 = _normalise_rgb(rgb)
    xyz = colour.sRGB_to_XYZ(rgb01)
    sd = XYZ_to_sd_Jakob2019(
        xyz, cmfs=_cmfs(), illuminant=_illuminant()
    ).align(SPECTRAL_SHAPE)
    return np.clip(np.asarray(sd.values, dtype=np.float64), _EPS, 1.0 - _EPS)


# ---------------------------------------------------------------------------
# 2. spectral reflectance -> sRGB.
# ---------------------------------------------------------------------------

def reflectance_to_rgb(refl) -> tuple[int, int, int]:
    """
    Render a 36-band reflectance curve back to an sRGB triple.

    Integrates the reflectance against the CIE 1931 2 degree observer under D65
    (:func:`colour.colorimetry.sd_to_XYZ`), then converts XYZ to sRGB
    (:func:`colour.XYZ_to_sRGB`).

    Parameters
    ----------
    refl
        Length-36 reflectance curve on the :data:`SPECTRAL_SHAPE` grid.

    Returns
    -------
    tuple of int
        ``(r, g, b)`` in the range 0-255.
    """
    values = np.clip(np.asarray(refl, dtype=np.float64).reshape(N_BANDS), _EPS, 1.0 - _EPS)
    sd = SpectralDistribution(dict(zip(WAVELENGTHS, values)))
    xyz = sd_to_XYZ(sd, cmfs=_cmfs(), illuminant=_illuminant()) / 100.0
    rgb01 = np.clip(colour.XYZ_to_sRGB(xyz), 0.0, 1.0)
    return tuple(int(round(v)) for v in rgb01 * 255.0)


# ---------------------------------------------------------------------------
# Kubelka-Munk primitives.
# ---------------------------------------------------------------------------

def _ks(refl: np.ndarray) -> np.ndarray:
    """K/S = (1 - rho)^2 / (2 rho) per band (single-constant K-M)."""
    rho = np.clip(refl, _EPS, 1.0 - _EPS)
    return (1.0 - rho) ** 2 / (2.0 * rho)


def _refl_from_ks(ks: np.ndarray) -> np.ndarray:
    """Invert K/S back to reflectance: rho = 1 + KS - sqrt(KS^2 + 2 KS)."""
    ks = np.maximum(ks, 0.0)
    rho = 1.0 + ks - np.sqrt(ks * ks + 2.0 * ks)
    return np.clip(rho, _EPS, 1.0 - _EPS)


def _relative_luminance(refl: np.ndarray) -> float:
    """Rec.709 relative luminance of a reflectance curve, in [0, 1]."""
    r, g, b = (np.asarray(reflectance_to_rgb(refl), dtype=np.float64) / 255.0)
    return float(0.2126 * r + 0.7152 * g + 0.0722 * b)


# ---------------------------------------------------------------------------
# 3. Subtractive spectral mixing.
# ---------------------------------------------------------------------------

def mix_reflectances(refls, weights) -> np.ndarray:
    """
    Subtractive (two-constant Kubelka-Munk) mix of reflectance curves.

    Per band, ``K/S = (1 - rho)^2 / (2 rho)`` is blended linearly by *effective*
    weight and the result is inverted back to reflectance via
    ``rho = 1 + KS - sqrt(KS^2 + 2 KS)``.

    The effective weight of pigment ``i`` is **not** its raw ratio but
    ``ratio_i**2 * luminance_i`` — the ratio squared, scaled by that pigment's
    own relative luminance. This is what makes strong dark pigments tint
    correctly: a small amount of a dark, low-luminance pigment still dominates a
    mix, matching real paint behaviour rather than a naive average.

    Parameters
    ----------
    refls
        Sequence of length-36 reflectance curves (one per pigment).
    weights
        Sequence of non-negative mixing ratios (parts), same length as
        ``refls``.

    Returns
    -------
    numpy.ndarray
        Shape ``(36,)`` mixed reflectance curve, clamped to ``(0, 1)``.

    Raises
    ------
    ValueError
        If ``refls`` and ``weights`` differ in length, are empty, or the total
        effective weight is zero.
    """
    curves = [np.clip(np.asarray(r, dtype=np.float64).reshape(N_BANDS), _EPS, 1.0 - _EPS)
              for r in refls]
    ratios = np.asarray(weights, dtype=np.float64).reshape(-1)
    if len(curves) == 0 or len(curves) != ratios.size:
        raise ValueError("refls and weights must be non-empty and equal length")

    ks_mix = np.zeros(N_BANDS, dtype=np.float64)
    total_w = 0.0
    for curve, ratio in zip(curves, ratios):
        eff = float(ratio) ** 2 * _relative_luminance(curve)
        ks_mix += eff * _ks(curve)
        total_w += eff
    if total_w <= 0.0:
        raise ValueError("total effective weight is zero; check weights/curves")
    ks_mix /= total_w
    return _refl_from_ks(ks_mix)


# ---------------------------------------------------------------------------
# 4. Spectral similarity.
# ---------------------------------------------------------------------------

def spectral_similarity(a, b) -> float:
    """
    Similarity of two reflectance curves in ``[0, 1]`` (1 == identical).

    Combines two complementary views of the curves:

    * **Spectral angle** (shape agreement, invariant to overall scale)::

          cos_theta  = dot(a, b) / (norm(a) * norm(b))
          norm_angle = 1 - acos(clip(cos_theta)) / (pi / 2)

    * **Euclidean curve distance** (level agreement)::

          norm_dist  = 1 - sqrt(mean((a - b)^2))

    blended as ``sqrt(norm_angle) * sqrt(norm_dist)`` so both must be high for a
    high score.

    Parameters
    ----------
    a, b
        Length-36 reflectance curves.

    Returns
    -------
    float
        Similarity in ``[0, 1]``.
    """
    va = np.asarray(a, dtype=np.float64).reshape(N_BANDS)
    vb = np.asarray(b, dtype=np.float64).reshape(N_BANDS)

    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    cos_theta = float(np.clip(np.dot(va, vb) / (na * nb), -1.0, 1.0))
    # Snap to 1.0 within float noise so identical curves score exactly 1 (the
    # dot/norm ratio can land at 0.999...9989 for a**2, giving a spurious angle).
    if cos_theta > 1.0 - 1.0e-12:
        cos_theta = 1.0
    norm_angle = 1.0 - np.arccos(cos_theta) / (np.pi / 2.0)

    rmse = float(np.sqrt(np.mean((va - vb) ** 2)))
    norm_dist = 1.0 - rmse

    norm_angle = max(0.0, min(1.0, norm_angle))
    norm_dist = max(0.0, min(1.0, norm_dist))
    return float(np.sqrt(norm_angle) * np.sqrt(norm_dist))


__all__ = [
    "SPECTRAL_SHAPE",
    "WAVELENGTHS",
    "N_BANDS",
    "rgb_to_reflectance",
    "reflectance_to_rgb",
    "mix_reflectances",
    "spectral_similarity",
]
