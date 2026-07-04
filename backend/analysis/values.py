from __future__ import annotations
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
    """Absorb tiny zone patches into their nearest large-component zone.

    Uses distance_transform_edt to assign each tiny-component pixel to the
    zone of its nearest non-tiny pixel — O(P×Z) total instead of the previous
    O(K×P) per-component cv2.dilate loop (K could be 10k+ on noisy images).
    """
    from scipy.ndimage import distance_transform_edt

    min_px = max(50, zone_map.size // 2000)

    # Mark all tiny-component pixels across all zones
    is_tiny = np.zeros(zone_map.shape, dtype=bool)
    for z in range(n_zones):
        labeled, n = scipy_label((zone_map == z).astype(np.uint8))
        if n == 0:
            continue
        sizes = np.bincount(labeled.ravel())
        tiny_ids = np.where((sizes < min_px) & (np.arange(len(sizes)) > 0))[0]
        if len(tiny_ids):
            is_tiny |= np.isin(labeled, tiny_ids)

    not_tiny = ~is_tiny
    if not is_tiny.any() or not not_tiny.any():
        # Nothing to clean up, or all pixels are tiny (no stable anchors — skip)
        return zone_map

    result = zone_map.copy()
    _, indices = distance_transform_edt(is_tiny, return_indices=True)
    result[is_tiny] = zone_map[indices[0][is_tiny], indices[1][is_tiny]]
    return result


def render_value_map(zone_map: np.ndarray, zones: list[ValueZone]) -> np.ndarray:
    """Render a greyscale image where each zone is its representative grey value."""
    H, W = zone_map.shape
    out  = np.zeros((H, W), dtype=np.uint8)
    for z in zones:
        out[zone_map == z.id] = z.grey_value
    return out
