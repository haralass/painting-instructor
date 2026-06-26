from __future__ import annotations
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


def render_detail_levels(
    cache: ImageCache,
    label_maps: dict[str, np.ndarray],
    regions: list[Region],
    families: list[ColourFamily],
    value_zones: list[ValueZone],
    zone_map: np.ndarray,
    outline_composites: dict[str, np.ndarray],
    out_dir,
) -> dict[str, DetailLevel]:
    """
    Render 5 detail levels to disk and return a DetailLevel dict keyed by str level.
    """
    from pathlib import Path
    out_dir = Path(out_dir)
    detail_levels: dict[str, DetailLevel] = {}

    H, W = cache.H, cache.W

    # Use fine or micro labels for high detail, coarse for low detail
    scale_priority = ["micro", "fine", "medium", "coarse"]

    for lvl in range(1, 6):
        importance_thresh = _LEVEL_IMPORTANCE[lvl]
        outline_key       = _LEVEL_OUTLINE[lvl]

        # Pick the finest label map available for this level
        label_map = None
        for sc in scale_priority:
            if sc in label_maps:
                label_map = label_maps[sc]
                break

        # Filter regions by importance
        active_regions = [r for r in regions if r.importance >= importance_thresh]
        region_ids     = [r.id for r in active_regions]

        # ── Outlines PNG ───────────────────────────────────────────────────
        outline_arr = outline_composites.get(outline_key, np.full((H, W), 255, dtype=np.uint8))
        outline_pil = Image.fromarray(outline_arr)
        outline_path = str(out_dir / f"level_{lvl}_outlines.png")
        outline_pil.save(outline_path)

        # ── Value map PNG ──────────────────────────────────────────────────
        value_arr  = _render_value(zone_map, value_zones, active_regions, label_map, H, W)
        value_pil  = Image.fromarray(value_arr)
        value_path = str(out_dir / f"level_{lvl}_values.png")
        value_pil.save(value_path)

        # ── Flat colour PNG ────────────────────────────────────────────────
        colour_arr  = _render_colour(active_regions, families, label_map, H, W, lvl)
        colour_pil  = Image.fromarray(colour_arr)
        colour_path = str(out_dir / f"level_{lvl}_colours.png")
        colour_pil.save(colour_path)

        # ── Region overlay PNG ─────────────────────────────────────────────
        region_arr  = _render_regions(cache.rgb, active_regions, families, label_map, H, W)
        region_pil  = Image.fromarray(region_arr)
        region_path = str(out_dir / f"level_{lvl}_regions.png")
        region_pil.save(region_path)

        detail_levels[str(lvl)] = DetailLevel(
            level=lvl,
            label=_LEVEL_LABELS[lvl],
            region_ids=region_ids,
            outlines=outline_path,
            values=value_path,
            colours=colour_path,
            regions=region_path,
        )

    return detail_levels


def _render_value(
    zone_map: np.ndarray,
    zones: list[ValueZone],
    active_regions: list[Region],
    label_map: np.ndarray | None,
    H: int,
    W: int,
) -> np.ndarray:
    out = np.full((H, W), 128, dtype=np.uint8)
    if label_map is not None:
        active_ids = {r.id for r in active_regions}
        for r in active_regions:
            mask = label_map == r.id
            out[mask] = zones[r.value_zone].grey_value if r.value_zone < len(zones) else 128
        # Background pixels: use zone_map directly
        inactive = ~np.isin(label_map, list(active_ids))
        for z in zones:
            out[inactive & (zone_map == z.id)] = z.grey_value
    else:
        for z in zones:
            out[zone_map == z.id] = z.grey_value
    return np.stack([out] * 3, axis=-1)


def _render_colour(
    active_regions: list[Region],
    families: list[ColourFamily],
    label_map: np.ndarray | None,
    H: int,
    W: int,
    lvl: int,
) -> np.ndarray:
    out = np.full((H, W, 3), 245, dtype=np.uint8)
    if label_map is None or not families:
        return out
    # Blend amount increases with detail level
    alpha = 0.35 + lvl * 0.12
    alpha = min(alpha, 0.85)
    bg    = np.array([245, 245, 245], dtype=np.float32)
    for r in active_regions:
        cf_id = min(r.colour_family_id, len(families) - 1)
        base  = np.array(families[cf_id].base_rgb, dtype=np.float32)
        tinted = base * alpha + bg * (1 - alpha)
        mask = label_map == r.id
        out[mask] = np.clip(tinted, 0, 255).astype(np.uint8)
    return out


def _render_regions(
    rgb: np.ndarray,
    active_regions: list[Region],
    families: list[ColourFamily],
    label_map: np.ndarray | None,
    H: int,
    W: int,
) -> np.ndarray:
    """Overlay coloured region tint on top of greyscale reference."""
    gray3 = np.stack([cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)] * 3, axis=-1)
    out   = gray3.copy()
    if label_map is None or not families:
        return out
    for r in active_regions:
        cf_id = min(r.colour_family_id, len(families) - 1)
        base  = np.array(families[cf_id].base_rgb, dtype=np.float32)
        mask  = label_map == r.id
        tinted = gray3[mask].astype(np.float32) * 0.5 + base * 0.5
        out[mask] = np.clip(tinted, 0, 255).astype(np.uint8)
    return out
