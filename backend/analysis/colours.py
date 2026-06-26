from __future__ import annotations
import colorsys

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from skimage import color as skcolor

from .models import ColourFamily, PaletteEntry
from .preprocessing import ImageCache


def extract_colour_families(
    cache: ImageCache,
    palette_size: int,
    seed: int = 42,
) -> tuple[list[ColourFamily], list[PaletteEntry], dict]:
    """
    Cluster region mean colours (in LAB space) into palette_size families.

    Uses the smoothed image for clustering so texture noise doesn't
    fragment the palette.

    Returns
    -------
    families    : list[ColourFamily]
    palette     : list[PaletteEntry]
    internal    : dict with 'centres_lab' and 'cluster_id_to_rank' for lookups
    """
    smooth = cache.smooth.astype(np.float32) / 255.0
    lab    = skcolor.rgb2lab(smooth).reshape(-1, 3)

    # Subsample for speed
    step = max(1, len(lab) // 50_000)
    lab_sample = lab[::step]

    k = min(palette_size, len(lab_sample))
    km = MiniBatchKMeans(
        n_clusters=k,
        init="k-means++",
        n_init=8,
        random_state=seed,
    ).fit(lab_sample)

    centres_lab = km.cluster_centers_   # (k, 3) in LAB
    counts      = np.bincount(km.labels_, minlength=k)
    total       = counts.sum() or 1

    # Convert centres to RGB
    centres_rgb = (
        skcolor.lab2rgb(centres_lab.reshape(1, -1, 3))[0] * 255
    ).astype(np.uint8)

    # Sort by area coverage descending
    order = np.argsort(-counts)

    # Build cluster_id → rank mapping for stable ID lookups
    cluster_id_to_rank: dict[int, int] = {
        int(cluster_idx): rank for rank, cluster_idx in enumerate(order)
    }

    families: list[ColourFamily] = []
    palette:  list[PaletteEntry] = []

    for rank, idx in enumerate(order):
        lab_c   = centres_lab[idx]
        rgb_c   = tuple(int(v) for v in centres_rgb[idx])
        area_f  = float(counts[idx] / total)
        name    = _colour_name_from_lab(lab_c, rank)

        variations = _make_variations(lab_c)

        families.append(ColourFamily(
            id=rank,
            name=name,
            base_rgb=rgb_c,
            base_lab=(float(lab_c[0]), float(lab_c[1]), float(lab_c[2])),
            area_fraction=area_f,
            variations=variations,
        ))

        palette.append(PaletteEntry(
            id=rank,
            name=name,
            base_rgb=rgb_c,
            base_lab=(float(lab_c[0]), float(lab_c[1]), float(lab_c[2])),
            area_fraction=area_f,
            variations=variations,
        ))

    internal = {
        "centres_lab": centres_lab,
        "order": order,
        "cluster_id_to_rank": cluster_id_to_rank,
    }
    return families, palette, internal


def _colour_name_from_lab(lab: np.ndarray, rank: int) -> str:
    """Approximate colour name from LAB values, falling back to numbered label."""
    rgb = skcolor.lab2rgb(lab.reshape(1, 1, 3))[0, 0]
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h_deg = h * 360
    if s < 0.12:
        if l > 0.85:
            return "Near-white"
        if l < 0.15:
            return "Near-black"
        return "Grey"
    if l > 0.85:
        return "Light tint"
    if l < 0.15:
        return "Dark shade"
    if h_deg < 15 or h_deg >= 345:
        return "Red"
    if h_deg < 40:
        return "Orange"
    if h_deg < 70:
        return "Yellow"
    if h_deg < 150:
        return "Green"
    if h_deg < 200:
        return "Cyan"
    if h_deg < 260:
        return "Blue"
    if h_deg < 290:
        return "Violet"
    if h_deg < 345:
        return "Magenta"
    return f"Colour {rank + 1}"


def _make_variations(lab: np.ndarray) -> dict[str, tuple[int, int, int]]:
    """Generate shadow/midtone/light/highlight variations by shifting L* in LAB."""
    L, a, b = float(lab[0]), float(lab[1]), float(lab[2])
    out: dict[str, tuple[int, int, int]] = {}
    for name, l_shift in [("shadow", -30), ("midtone", -10), ("light", +15), ("highlight", +30)]:
        l_new = np.clip(L + l_shift, 0, 100)
        rgb_f = skcolor.lab2rgb(np.array([[[l_new, a, b]]]))[0, 0] * 255
        out[name] = tuple(int(np.clip(v, 0, 255)) for v in rgb_f)
    return out


def render_flat_colour(
    label_map: np.ndarray,
    regions,
    families: list[ColourFamily],
    alpha: float = 0.5,
    bg: tuple[int, int, int] = (255, 255, 255),
) -> np.ndarray:
    """Render a flat-colour image from region labels + colour family assignments."""
    H, W = label_map.shape
    out  = np.full((H, W, 3), bg, dtype=np.uint8)

    for region in regions:
        lbl = getattr(region, "source_label", None)
        if lbl is None:
            lbl = region.id
        mask = label_map == lbl
        if not mask.any():
            continue
        cf_id = min(region.colour_family_id, len(families) - 1)
        base  = np.array(families[cf_id].base_rgb, dtype=np.float32)
        tinted = base * alpha + np.array(bg, dtype=np.float32) * (1 - alpha)
        out[mask] = np.clip(tinted, 0, 255).astype(np.uint8)
    return out
