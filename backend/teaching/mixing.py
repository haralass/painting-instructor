"""
Real-paint mixing recipes via single-constant Kubelka-Munk theory.

Paint does NOT mix like RGB light: blue + yellow makes green because of how
pigments absorb and scatter, which averaging RGB numbers gets wrong. K-M is
the standard published model (Kubelka & Munk 1931; single-constant form per
Duncan 1940): per wavelength band, K/S = (1-R)²/2R is additive by pigment
concentration, and the mixture reflectance inverts the same formula.

We mix in a real 36-band spectral space (`analysis/spectral.py` — reflectance
recovered from sRGB, luminance-weighted concentration), which captures pigment
absorption far better than the 3-channel shortcut; if the spectral stack
(colour-science) is unavailable, we fall back to running K-M on three coarse
linearised-sRGB bands so recipes still work in a light install.

The algorithm is public science; this implementation is ours. (The idea of
shipping recipes came from studying ArtistAssistApp, whose code we do not
copy — its licence is restrictive; K-M itself is a 1931 paper.)

A small combinatorial search over a standard 12-tube palette produces
"Titanium White 2 : Burnt Sienna 1"-style recipes for every extracted
palette colour. All candidate mixtures are precomputed once per process.
"""
from __future__ import annotations

from functools import lru_cache
from itertools import combinations

import numpy as np

try:
    from ..analysis import spectral as _spectral
    _SPECTRAL = True
except Exception:  # colour-science missing → 3-band fallback
    _SPECTRAL = False

# A standard starter palette (oil/acrylic). sRGB approximations of masstone.
TUBES: list[tuple[str, tuple[int, int, int]]] = [
    ("Titanium White",    (245, 245, 240)),
    ("Ivory Black",       (35, 33, 32)),
    ("Cadmium Yellow",    (250, 205, 15)),
    ("Yellow Ochre",      (200, 155, 60)),
    ("Cadmium Red",       (215, 55, 40)),
    ("Alizarin Crimson",  (120, 25, 45)),
    ("Burnt Sienna",      (125, 65, 40)),
    ("Burnt Umber",       (70, 50, 38)),
    ("Ultramarine Blue",  (25, 45, 130)),
    ("Phthalo Blue",      (10, 60, 105)),
    ("Sap Green",         (65, 90, 45)),
    ("Viridian",          (25, 110, 85)),
]

# Parts ratios searched for 2- and 3-tube mixtures (integers a painter can
# measure out with a knife). Ratios run up to 12:1 because strong tinters
# (blacks, phthalos, siennas) need a LOT of white against them — K-M models
# exactly that dominance, so tints are unreachable without high ratios.
_PAIR_RATIOS = [
    (1, 1), (2, 1), (3, 1), (4, 1), (6, 1), (8, 1), (12, 1), (16, 1), (24, 1),
    (1, 2), (1, 3), (1, 4), (1, 6), (1, 8), (1, 12), (1, 16), (1, 24),
]
_TRIPLE_RATIOS = [
    (1, 1, 1), (2, 1, 1), (1, 2, 1), (1, 1, 2),
    (3, 1, 1), (1, 3, 1), (1, 1, 3), (2, 2, 1), (2, 1, 2), (1, 2, 2),
    (4, 1, 1), (3, 2, 1), (4, 2, 1),
    (6, 1, 1), (8, 1, 1), (6, 2, 1), (8, 2, 1), (12, 2, 1), (10, 4, 1),
]


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    c = np.clip(rgb / 255.0, 0.02, 1.0)   # K-M blows up at R=0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(lin: np.ndarray) -> np.ndarray:
    lin = np.clip(lin, 0.0, 1.0)
    c = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(c * 255.0, 0, 255)


def _ks(refl: np.ndarray) -> np.ndarray:
    return (1.0 - refl) ** 2 / (2.0 * refl)


def _refl(ks: np.ndarray) -> np.ndarray:
    return 1.0 + ks - np.sqrt(ks * ks + 2.0 * ks)


@lru_cache(maxsize=512)
def _reflectance_for(rgb: tuple[int, int, int]) -> np.ndarray:
    """Cached 36-band reflectance recovery for a tube colour (recovery is ~80ms)."""
    return _spectral.rgb_to_reflectance(rgb)


def mix_km(rgbs: list[tuple[int, int, int]], parts: list[float]) -> np.ndarray:
    """Mix paints by parts; returns the mixture's sRGB as float array.

    Uses 36-band spectral Kubelka-Munk when available (physically accurate),
    else three linearised-sRGB bands."""
    if _SPECTRAL:
        try:
            refls = [_reflectance_for(tuple(int(round(c)) for c in rgb)) for rgb in rgbs]
            mixed = _spectral.mix_reflectances(refls, list(parts))
            return np.asarray(_spectral.reflectance_to_rgb(mixed), dtype=np.float64)
        except Exception:
            pass  # fall through to the 3-band shortcut

    w = np.asarray(parts, dtype=np.float64)
    w = w / w.sum()
    ks_mix = np.zeros(3)
    for rgb, wi in zip(rgbs, w):
        ks_mix += wi * _ks(_srgb_to_linear(np.asarray(rgb, dtype=np.float64)))
    return _linear_to_srgb(_refl(ks_mix))


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Minimal sRGB→CIELAB (D65) for ΔE ranking."""
    lin = _srgb_to_linear(np.asarray(rgb, dtype=np.float64) * 255.0 / 255.0 if rgb.max() <= 1.0 else np.asarray(rgb, dtype=np.float64))
    M = np.array([
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ])
    xyz = M @ lin
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.array([116.0 * f[1] - 16.0, 500.0 * (f[0] - f[1]), 200.0 * (f[1] - f[2])])


@lru_cache(maxsize=1)
def _candidate_mixtures() -> list[tuple[list, np.ndarray, np.ndarray]]:
    """[(recipe, mixed_rgb, mixed_lab)] over singles, pairs and triples."""
    out = []
    for i, (name, rgb) in enumerate(TUBES):
        mixed = np.asarray(rgb, dtype=np.float64)
        out.append(([{"tube": name, "parts": 1}], mixed, _rgb_to_lab(mixed)))
    for (i, j) in combinations(range(len(TUBES)), 2):
        for pa, pb in _PAIR_RATIOS:
            mixed = mix_km([TUBES[i][1], TUBES[j][1]], [pa, pb])
            recipe = [{"tube": TUBES[i][0], "parts": pa}, {"tube": TUBES[j][0], "parts": pb}]
            out.append((recipe, mixed, _rgb_to_lab(mixed)))
    for (i, j, k) in combinations(range(len(TUBES)), 3):
        for pa, pb, pc in _TRIPLE_RATIOS:
            mixed = mix_km([TUBES[i][1], TUBES[j][1], TUBES[k][1]], [pa, pb, pc])
            recipe = [{"tube": TUBES[i][0], "parts": pa},
                      {"tube": TUBES[j][0], "parts": pb},
                      {"tube": TUBES[k][0], "parts": pc}]
            out.append((recipe, mixed, _rgb_to_lab(mixed)))
    return out


def recipe_for(rgb: tuple[int, int, int]) -> dict:
    """
    Best small-parts recipe for a target sRGB colour.
    Returns {"recipe": [...], "mixed_rgb": [r,g,b], "delta_e": float,
             "text": "Titanium White 2 : Burnt Sienna 1"}.
    """
    target_lab = _rgb_to_lab(np.asarray(rgb, dtype=np.float64))
    best = None
    best_de = float("inf")
    for recipe, mixed, lab in _candidate_mixtures():
        de = float(np.linalg.norm(lab - target_lab))
        # tie-break: prefer fewer tubes at effectively equal ΔE
        if de < best_de - 0.25 or (abs(de - best_de) <= 0.25 and best and len(recipe) < len(best[0])):
            best, best_de = (recipe, mixed), de
    recipe, mixed = best
    return {
        "recipe": recipe,
        "mixed_rgb": [int(round(v)) for v in mixed],
        "delta_e": round(best_de, 1),
        "text": " : ".join(f"{r['tube']} {r['parts']}" for r in recipe),
    }


# Mediums where physical paint mixing applies
MIXING_MEDIUMS = {"oil", "acrylic", "watercolor"}


def recipes_for_palette(palette: list[dict], medium: str) -> list[dict]:
    """Attach a mixing recipe to each palette entry (mutates copies)."""
    if medium not in MIXING_MEDIUMS:
        return palette
    enriched = []
    for p in palette:
        q = dict(p)
        try:
            q["mixing"] = recipe_for(tuple(p.get("base_rgb", (128, 128, 128))))
        except Exception:
            pass
        enriched.append(q)
    return enriched
