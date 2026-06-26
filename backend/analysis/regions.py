from __future__ import annotations
import logging

import cv2
import numpy as np
from skimage import segmentation, graph as sk_graph, measure
from skimage import color as skcolor

from .models import Region
from .preprocessing import ImageCache
from .values import compute_value_zones

log = logging.getLogger(__name__)

# Target superpixel counts for each coarseness scale
_SCALE_SEGMENTS = {
    "coarse": 150,
    "medium": 500,
    "fine":   1400,
    "micro":  3500,
}

# detail_level → which scales to use and merge threshold
_LEVEL_SCALES = {
    1: ["coarse"],
    2: ["coarse", "medium"],
    3: ["coarse", "medium", "fine"],
    4: ["coarse", "medium", "fine", "micro"],
    5: ["coarse", "medium", "fine", "micro"],
}


def build_region_hierarchy(
    cache: ImageCache,
    palette_size: int,
    detail_level: int,
    n_value_zones: int,
    value_colour_families: dict,   # mapping from colour_family pipeline
    seed: int = 42,
) -> tuple[dict[str, np.ndarray], list[Region]]:
    """
    Build multi-scale SLIC hierarchy.

    Returns
    -------
    label_maps : dict scale → (H,W) int32 label array
    regions    : flat list of all Region objects across all scales
    """
    smooth_rgb = cache.smooth
    zone_map, zones = compute_value_zones(cache, n_value_zones)

    active_scales = _LEVEL_SCALES.get(detail_level, list(_SCALE_SEGMENTS.keys()))
    label_maps: dict[str, np.ndarray] = {}
    all_regions: list[Region] = []
    region_id = 0

    coarse_labels = None   # used for parent assignment

    for scale in active_scales:
        n_seg = _adapt_segments(_SCALE_SEGMENTS[scale], cache.W, cache.H)
        try:
            labels = segmentation.slic(
                smooth_rgb,
                n_segments=n_seg,
                compactness=10,
                sigma=1,
                start_label=1,
                enforce_connectivity=True,
                convert2lab=True,
            )
        except Exception:
            log.warning("SLIC failed at scale %r (n_seg=%d)", scale, n_seg)
            continue

        # RAG merge toward palette_size at coarse level only
        if scale == "coarse" and palette_size < n_seg:
            labels = _rag_merge(smooth_rgb, labels, target_n=palette_size)

        label_maps[scale] = labels
        level_idx = active_scales.index(scale)

        uniq = np.unique(labels)
        uniq = uniq[uniq > 0]

        lab_img = cache.lab
        grad    = cache.grad

        for lbl in uniq:
            mask = labels == lbl
            area = int(mask.sum())
            if area == 0:
                continue

            ys, xs = np.where(mask)
            cy, cx = float(ys.mean()), float(xs.mean())
            x_min, x_max = int(xs.min()), int(xs.max())
            y_min, y_max = int(ys.min()), int(ys.max())

            lab_vals = lab_img[mask]
            mean_lab = lab_vals.mean(axis=0)
            mean_rgb_f = skcolor.lab2rgb(mean_lab.reshape(1, 1, 3))[0, 0] * 255
            mean_rgb   = tuple(int(np.clip(v, 0, 255)) for v in mean_rgb_f)

            # Value zone: majority vote
            vz_ids = zone_map[mask]
            vz     = int(np.bincount(vz_ids).argmax())

            # Importance: area × gradient strength at boundary
            importance = float(np.log1p(area)) * (1 + float(grad[mask].mean()) / 50.0)
            importance = min(1.0, importance / 15.0)

            # Texture score: std of L* within region
            texture = float(lab_vals[:, 0].std()) / 50.0
            texture = min(1.0, texture)

            # Colour family id: index of nearest palette centre
            cf_id = _nearest_colour_family(mean_lab, value_colour_families)

            # Parent region: nearest coarse-scale region at centroid
            parent_id: int | None = None
            if coarse_labels is not None and scale != "coarse":
                cy_i, cx_i = int(round(cy)), int(round(cx))
                cy_i = np.clip(cy_i, 0, cache.H - 1)
                cx_i = np.clip(cx_i, 0, cache.W - 1)
                parent_lbl = int(coarse_labels[cy_i, cx_i])
                if parent_lbl > 0:
                    parent_id = parent_lbl + (1_000_000 if scale != "coarse" else 0)

            all_regions.append(Region(
                id=region_id,
                parent_id=parent_id,
                level=level_idx,
                area=area,
                centroid=(cx, cy),
                bbox=(x_min, y_min, x_max, y_max),
                mean_lab=(float(mean_lab[0]), float(mean_lab[1]), float(mean_lab[2])),
                mean_rgb=mean_rgb,
                value_zone=vz,
                colour_family_id=cf_id,
                importance=importance,
                texture_score=texture,
            ))
            region_id += 1

        if scale == "coarse":
            coarse_labels = labels

    return label_maps, all_regions


def _adapt_segments(base: int, W: int, H: int) -> int:
    """Scale segment count to image resolution (normalised to 800×600 reference)."""
    area   = W * H
    ref    = 800 * 600
    factor = area / ref
    return max(20, int(base * factor ** 0.5))


def _rag_merge(smooth_rgb: np.ndarray, labels: np.ndarray, target_n: int) -> np.ndarray:
    """Binary-search RAG threshold to reach approximately target_n regions."""
    g_base = sk_graph.rag_mean_color(smooth_rgb, labels)
    lo, hi = 2.0, 100.0
    best   = labels
    for _ in range(20):
        mid    = (lo + hi) / 2.0
        merged = sk_graph.cut_threshold(labels, g_base.copy(), thresh=mid)
        n_reg  = len(np.unique(merged))
        if n_reg > target_n:
            lo = mid
        else:
            hi = mid
            best = merged
    return best


def _nearest_colour_family(mean_lab: np.ndarray, families: dict) -> int:
    if not families:
        return 0
    centres = families.get("centres_lab")
    if centres is None or len(centres) == 0:
        return 0
    dists = np.linalg.norm(centres - mean_lab, axis=1)
    return int(dists.argmin())
