from __future__ import annotations
import cv2
import numpy as np
from scipy.ndimage import label as scipy_label

from .models import ValueZone
from .preprocessing import ImageCache

_ZONE_LABELS = {
    3: ["shadow", "midtone", "light"],
    5: ["shadow", "low-midtone", "midtone", "high-midtone", "highlight"],
    7: ["deep shadow", "shadow", "low-midtone", "midtone", "high-midtone", "highlight", "specular"],
}


def compute_value_zones(cache: ImageCache, n_zones: int) -> tuple[np.ndarray, list[ValueZone]]:
    """
    Adaptive value zone segmentation.

    Thresholds are derived from the image L* histogram (equal-area quantile
    splits) rather than fixed values like 33/67, so each zone covers a
    meaningful visual range for this specific image.

    The L channel is smoothed edge-preservingly BEFORE thresholding and the
    zone map is simplified AFTER — a value study is a design of large masses,
    not a per-pixel posterisation. Without this, textured photos (grass,
    rock, fabric) produce salt-and-pepper zone maps that are useless for
    teaching.

    Returns
    -------
    zone_map : (H, W) uint8  — zone index per pixel, 0-based
    zones    : list[ValueZone]
    """
    L = smooth_lightness(cache.L)
    flat = L.ravel()

    # Equal-quantile thresholds
    quantiles  = np.linspace(0, 100, n_zones + 1)
    thresholds = [float(np.percentile(flat, q)) for q in quantiles]
    thresholds[0]  = 0.0
    thresholds[-1] = 100.0

    labels = _ZONE_LABELS.get(n_zones, [f"zone_{i}" for i in range(n_zones)])

    H, W   = L.shape
    zone_map = np.zeros((H, W), dtype=np.uint8)
    zones: list[ValueZone] = []

    for i, label in enumerate(labels):
        lo  = thresholds[i]
        hi  = thresholds[i + 1]
        mask = (L >= lo) & (L < hi) if i < n_zones - 1 else (L >= lo)
        zone_map[mask] = i
        grey = int(round(15 + 225 * i / max(n_zones - 1, 1)))
        zones.append(ValueZone(
            id=i, label=label, l_min=lo, l_max=hi, grey_value=grey
        ))

    zone_map = simplify_zone_map(zone_map, n_zones)
    return zone_map, zones


def smooth_lightness(L: np.ndarray) -> np.ndarray:
    """
    Edge-preserving smoothing of an L* (0-100) channel before quantisation.
    Bilateral filtering flattens texture (grass, rock grain) while keeping
    the mass boundaries a painter actually cares about.
    """
    l8 = np.clip(L * 2.55, 0, 255).astype(np.uint8)
    d = 9
    l8 = cv2.bilateralFilter(l8, d, sigmaColor=35, sigmaSpace=9)
    l8 = cv2.bilateralFilter(l8, d, sigmaColor=25, sigmaSpace=9)
    return l8.astype(np.float32) / 2.55


def simplify_zone_map(zone_map: np.ndarray, n_zones: int, min_frac: float = 0.003) -> np.ndarray:
    """
    Turn a per-pixel quantisation into a mass design:
    1. median-filter the (ordinal) zone indices — removes pepper noise
    2. absorb every component smaller than `min_frac` of the image into the
       zone of its nearest large component (distance-transform pass, O(P))

    0.3% of a 1024² image ≈ 3k px — anything smaller is not a paintable
    shape at study scale.
    """
    from scipy.ndimage import distance_transform_edt

    zm = cv2.medianBlur(zone_map.astype(np.uint8), 7)

    min_px = max(50, int(zm.size * min_frac))
    is_tiny = np.zeros(zm.shape, dtype=bool)
    for z in range(n_zones):
        labeled, n = scipy_label((zm == z).astype(np.uint8))
        if n == 0:
            continue
        sizes = np.bincount(labeled.ravel())
        tiny_ids = np.where((sizes < min_px) & (np.arange(len(sizes)) > 0))[0]
        if len(tiny_ids):
            is_tiny |= np.isin(labeled, tiny_ids)

    not_tiny = ~is_tiny
    if not is_tiny.any() or not not_tiny.any():
        # Nothing to clean up, or all pixels are tiny (no stable anchors — skip)
        return zm

    result = zm.copy()
    _, indices = distance_transform_edt(is_tiny, return_indices=True)
    result[is_tiny] = zm[indices[0][is_tiny], indices[1][is_tiny]]
    return result


# Backwards-compatible alias (previous private name)
def _cleanup_zone_map(zone_map: np.ndarray, n_zones: int) -> np.ndarray:
    return simplify_zone_map(zone_map, n_zones)


def render_value_map(zone_map: np.ndarray, zones: list[ValueZone]) -> np.ndarray:
    """Render a greyscale image where each zone is its representative grey value."""
    H, W = zone_map.shape
    out  = np.zeros((H, W), dtype=np.uint8)
    for z in zones:
        out[zone_map == z.id] = z.grey_value
    return out
