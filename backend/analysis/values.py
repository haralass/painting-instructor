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

    Returns
    -------
    zone_map : (H, W) uint8  — zone index per pixel, 0-based
    zones    : list[ValueZone]
    """
    L    = cache.L
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

    # Spatial cleanup: remove tiny isolated patches via morphological opening
    zone_map = _cleanup_zone_map(zone_map, n_zones)
    return zone_map, zones


def _cleanup_zone_map(zone_map: np.ndarray, n_zones: int) -> np.ndarray:
    """Remove speckle noise by absorbing tiny patches into their largest neighbour."""
    min_px = max(50, zone_map.size // 2000)
    result = zone_map.copy()
    for z in range(n_zones):
        binary = (zone_map == z).astype(np.uint8)
        labeled, n = scipy_label(binary)
        if n == 0:
            continue
        sizes = np.bincount(labeled.ravel())
        small = [c for c in range(1, n + 1) if sizes[c] < min_px]
        if not small:
            continue
        small_mask = np.isin(labeled, small)
        # Expand neighbours into tiny patches
        expanded = cv2.dilate(
            (result != z).astype(np.uint8) * 255, np.ones((5, 5), np.uint8)
        )
        result[small_mask & (expanded > 0)] = result[
            np.roll(small_mask & (expanded > 0), 1, axis=0)
        ].max() if small_mask.any() else z
    return result


def render_value_map(zone_map: np.ndarray, zones: list[ValueZone]) -> np.ndarray:
    """Render a greyscale image where each zone is its representative grey value."""
    H, W = zone_map.shape
    out  = np.zeros((H, W), dtype=np.uint8)
    for z in zones:
        out[zone_map == z.id] = z.grey_value
    return out
