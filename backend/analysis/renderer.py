from __future__ import annotations
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image

from .models import DetailLevel, Region, ColourFamily, ValueZone
from .preprocessing import ImageCache

_LEVEL_LABELS = {
    1: "Foundation",
    2: "Simplified",
    3: "Standard",
    4: "Detailed",
    5: "Full Reference",
}

# Which outline map to use per level
_LEVEL_OUTLINE = {
    1: "outlines_primary",
    2: "outlines_primary",
    3: "outlines_primary_secondary",
    4: "outlines_detailed",
    5: "outlines_full",
}

# Minimum region importance threshold per level
_LEVEL_IMPORTANCE = {
    1: 0.6,
    2: 0.4,
    3: 0.25,
    4: 0.1,
    5: 0.0,
}

# Which scales contribute to each level (finest to coarsest in the old SLIC scheme)
_SCALE_FOR_LEVEL = {
    1: "coarse",
    2: "coarse",
    3: "medium",
    4: "fine",
    5: "micro",
}
# merge-tree scale names
_MERGE_SCALE_FOR_LEVEL = {
    1: "l1",
    2: "l2",
    3: "l3",
    4: "l4",
    5: "l5",
}


def render_detail_levels(
    cache: ImageCache,
    label_maps: dict[str, np.ndarray],   # scale → label array
    regions: list[Region],
    families: list[ColourFamily],
    value_zones: list[ValueZone],
    zone_map: np.ndarray,
    outline_composites: dict[str, np.ndarray],
    out_dir,
    edges=None,  # list[Edge] | None — for edge_ids per level
) -> dict[str, DetailLevel]:
    """
    Render 5 detail levels to disk and return a DetailLevel dict keyed by str level.
    Uses LUT-based rendering (O(H*W) per level, not O(N*H*W)).

    Outline complexity per level:
      1: primary only
      2: primary only (simplified)
      3: primary + secondary
      4: primary + secondary + decorative
      5: all (including texture)
    """
    from pathlib import Path
    out_dir = Path(out_dir)
    detail_levels: dict[str, DetailLevel] = {}

    H, W = cache.H, cache.W

    # Detect whether this is merge-tree output (scales "l1".."l5") or old SLIC
    is_merge_tree = any(k in label_maps for k in ("l1", "l2", "l3", "l4", "l5"))

    for lvl in range(1, 6):
        importance_thresh = _LEVEL_IMPORTANCE[lvl]
        outline_key       = _LEVEL_OUTLINE[lvl]

        # Pick the label map for this level
        if is_merge_tree:
            scale_key = _MERGE_SCALE_FOR_LEVEL[lvl]
            label_map = label_maps.get(scale_key)
            if label_map is None:
                # fall back to finest available
                for k in ("l5", "l4", "l3", "l2", "l1"):
                    if k in label_maps:
                        label_map = label_maps[k]
                        scale_key = k
                        break
            # Filter regions by scale for this level
            active_regions = [
                r for r in regions
                if r.scale == scale_key and r.importance >= importance_thresh
            ]
        else:
            scale_priority = ["micro", "fine", "medium", "coarse"]
            label_map = None
            scale_key = "coarse"
            for sc in scale_priority:
                if sc in label_maps:
                    label_map = label_maps[sc]
                    scale_key = sc
                    break
            active_regions = [r for r in regions if r.importance >= importance_thresh]

        region_ids = [r.id for r in active_regions]

        # ── Edge IDs for this level (complexity filter) ────────────────────
        _LEVEL_EDGE_TYPES = {
            1: {"primary"},
            2: {"primary"},
            3: {"primary", "secondary"},
            4: {"primary", "secondary", "decorative"},
            5: {"primary", "secondary", "decorative", "texture"},
        }
        allowed_types = _LEVEL_EDGE_TYPES[lvl]
        edge_ids: list[int] = []
        if edges is not None:
            edge_ids = [e.id for e in edges if e.type in allowed_types]

        # ── Outlines PNG ───────────────────────────────────────────────────
        outline_arr = outline_composites.get(outline_key, np.full((H, W), 255, dtype=np.uint8))
        outline_pil = Image.fromarray(outline_arr)
        outline_path = str(out_dir / f"level_{lvl}_outlines.png")
        outline_pil.save(outline_path)

        # ── Value map PNG ──────────────────────────────────────────────────
        value_arr  = _render_value_lut(zone_map, value_zones, active_regions, label_maps, H, W)
        value_pil  = Image.fromarray(value_arr)
        value_path = str(out_dir / f"level_{lvl}_values.png")
        value_pil.save(value_path)

        # ── Flat colour PNG ────────────────────────────────────────────────
        colour_arr  = _render_colour_lut(active_regions, families, label_maps, H, W, lvl)
        colour_pil  = Image.fromarray(colour_arr)
        colour_path = str(out_dir / f"level_{lvl}_colours.png")
        colour_pil.save(colour_path)

        # ── Region overlay PNG ─────────────────────────────────────────────
        region_arr  = _render_regions_lut(cache.rgb, active_regions, families, label_maps, H, W)
        region_pil  = Image.fromarray(region_arr)
        region_path = str(out_dir / f"level_{lvl}_regions.png")
        region_pil.save(region_path)

        detail_levels[str(lvl)] = DetailLevel(
            level=lvl,
            label=_LEVEL_LABELS[lvl],
            region_ids=region_ids,
            edge_ids=edge_ids,
            outlines=outline_path,
            values=value_path,
            colours=colour_path,
            regions=region_path,
        )

    return detail_levels


def _render_value_lut(
    zone_map: np.ndarray,
    zones: list[ValueZone],
    active_regions: list[Region],
    label_maps: dict[str, np.ndarray],
    H: int,
    W: int,
) -> np.ndarray:
    # Build a zone_id → grey mapping
    zone_grey = {z.id: z.grey_value for z in zones}
    # Start from zone_map
    out = np.full((H, W), 128, dtype=np.uint8)
    for z in zones:
        out[zone_map == z.id] = z.grey_value

    # Overlay active regions using their value_zone
    by_scale: dict[str, list[Region]] = defaultdict(list)
    for r in active_regions:
        by_scale[r.scale].append(r)

    for scale, regs in by_scale.items():
        lm = label_maps.get(scale)
        if lm is None:
            continue
        max_lbl = int(lm.max()) + 1
        lut = np.full(max_lbl, 128, dtype=np.uint8)
        for r in regs:
            if r.source_label < max_lbl:
                grey = zone_grey.get(r.value_zone, 128)
                lut[r.source_label] = grey
        out = np.where(lm < max_lbl, lut[lm.clip(0, max_lbl - 1)], out)

    return np.stack([out] * 3, axis=-1)


def _render_colour_lut(
    active_regions: list[Region],
    families: list[ColourFamily],
    label_maps: dict[str, np.ndarray],
    H: int,
    W: int,
    lvl: int,
) -> np.ndarray:
    alpha = min(0.35 + lvl * 0.12, 0.85)
    bg = np.array([245, 245, 245], dtype=np.float32)
    out = np.full((H, W, 3), 245, dtype=np.uint8)
    if not families:
        return out

    by_scale: dict[str, list[Region]] = defaultdict(list)
    for r in active_regions:
        by_scale[r.scale].append(r)

    for scale, regs in by_scale.items():
        lm = label_maps.get(scale)
        if lm is None:
            continue
        max_lbl = int(lm.max()) + 1
        lut = np.full((max_lbl, 3), 245, dtype=np.uint8)
        for r in regs:
            if r.source_label < max_lbl:
                cf_id = min(r.colour_family_id, len(families) - 1)
                base = np.array(families[cf_id].base_rgb, dtype=np.float32)
                tinted = np.clip(base * alpha + bg * (1 - alpha), 0, 255).astype(np.uint8)
                lut[r.source_label] = tinted
        clipped_lm = lm.clip(0, max_lbl - 1)
        out = np.where((lm < max_lbl)[:, :, None], lut[clipped_lm], out)

    return out


def _render_regions_lut(
    rgb: np.ndarray,
    active_regions: list[Region],
    families: list[ColourFamily],
    label_maps: dict[str, np.ndarray],
    H: int,
    W: int,
) -> np.ndarray:
    """Overlay coloured region tint on top of greyscale reference."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray3 = np.stack([gray] * 3, axis=-1).astype(np.float32)
    out = gray3.copy().astype(np.uint8)
    if not families:
        return out

    by_scale: dict[str, list[Region]] = defaultdict(list)
    for r in active_regions:
        by_scale[r.scale].append(r)

    for scale, regs in by_scale.items():
        lm = label_maps.get(scale)
        if lm is None:
            continue
        max_lbl = int(lm.max()) + 1
        # LUT: label → base RGB (float) for blending
        lut_rgb = np.zeros((max_lbl, 3), dtype=np.float32)
        lut_active = np.zeros(max_lbl, dtype=bool)
        for r in regs:
            if r.source_label < max_lbl:
                cf_id = min(r.colour_family_id, len(families) - 1)
                lut_rgb[r.source_label] = np.array(families[cf_id].base_rgb, dtype=np.float32)
                lut_active[r.source_label] = True

        clipped_lm = lm.clip(0, max_lbl - 1)
        active_mask = (lm < max_lbl) & lut_active[clipped_lm]
        region_colours = lut_rgb[clipped_lm]
        blended = np.clip(gray3 * 0.5 + region_colours * 0.5, 0, 255).astype(np.uint8)
        out = np.where(active_mask[:, :, None], blended, out)

    return out


# Keep old function names as aliases for backward compatibility with pipeline.py
def _render_value(zone_map, zones, active_regions, label_map, H, W):
    # For backward-compat: build a fake label_maps dict
    if label_map is not None:
        scale = active_regions[0].scale if active_regions else "coarse"
        lm = {scale: label_map}
        # re-assign scale to match for all regions
        return _render_value_lut(zone_map, zones, active_regions, lm, H, W)
    return _render_value_lut(zone_map, zones, active_regions, {}, H, W)


def _render_colour(active_regions, families, label_map, H, W, lvl):
    if label_map is not None and active_regions:
        scale = active_regions[0].scale if active_regions else "coarse"
        lm = {scale: label_map}
        return _render_colour_lut(active_regions, families, lm, H, W, lvl)
    return _render_colour_lut(active_regions, families, {}, H, W, lvl)


def _render_regions(rgb, active_regions, families, label_map, H, W):
    if label_map is not None and active_regions:
        scale = active_regions[0].scale if active_regions else "coarse"
        lm = {scale: label_map}
        return _render_regions_lut(rgb, active_regions, families, lm, H, W)
    return _render_regions_lut(rgb, active_regions, families, {}, H, W)
