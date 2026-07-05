from __future__ import annotations
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image

from .models import DetailLevel, Region, ColourFamily, ValueZone, MediumStrategy
from .preprocessing import ImageCache
from .edges import LEVEL_EDGE_TYPES

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
    medium_strategy: MediumStrategy | None = None,
    edge_maps: dict[str, np.ndarray] | None = None,  # A9: individual edge maps for per-medium processing
    level_edge_maps: dict[int, dict[str, np.ndarray]] | None = None,  # level-aware outline source
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
            all_scale_regions = [r for r in regions if r.scale == scale_key]
            active_regions = [r for r in all_scale_regions if r.importance >= importance_thresh]
        else:
            scale_priority = ["micro", "fine", "medium", "coarse"]
            label_map = None
            scale_key = "coarse"
            for sc in scale_priority:
                if sc in label_maps:
                    label_map = label_maps[sc]
                    scale_key = sc
                    break
            all_scale_regions = list(regions)
            active_regions = [r for r in regions if r.importance >= importance_thresh]

        region_ids = [r.id for r in active_regions]

        # Value/colour masses must cover the level's own coarse partition fully —
        # using only importance-filtered active_regions would leave low-importance
        # regions unfilled and let full pixel-resolution zone_map noise show through,
        # defeating the point of a simplified Level 1. active_regions (importance
        # filtered) is still used for region_ids / region overlay highlighting below.
        mass_regions = all_scale_regions if all_scale_regions else active_regions

        # ── Edge IDs for this level (complexity filter) ────────────────────
        allowed_types = LEVEL_EDGE_TYPES[lvl]
        edge_ids: list[int] = []
        if edges is not None:
            edge_ids = [e.id for e in edges if e.type in allowed_types]

        # ── Outlines: prefer this level's own ancestor-filtered edge set ────
        # level_edge_maps[lvl] already contains only edges that are (a) the
        # right types for this level and (b) still boundaries at this level's
        # own region resolution (see pipeline.py's filter_edges_for_level) —
        # so Level 1 is genuinely coarser than Level 5, not just a type mask
        # over one fixed-scale edge set.
        # Per-level sublayer PNG paths (primary/secondary/decorative/texture),
        # saved below only when we have genuinely level-aware per-type maps —
        # this is what the frontend's outline sublayer toggles must read
        # instead of the global (non-level-filtered) edge_maps, so toggling
        # detail level actually changes what the sublayers show.
        level_edge_map_paths: dict[str, str] = {}

        if level_edge_maps is not None and lvl in level_edge_maps:
            lvl_maps = level_edge_maps[lvl]
            if medium_strategy is not None:
                lvl_maps = _apply_medium_to_edge_maps(lvl_maps, medium_strategy)
            outline_arr = _composite_all_edge_maps(lvl_maps)

            for type_name, type_arr in lvl_maps.items():
                if type_arr is None or not np.any(type_arr):
                    continue  # no edges of this type at this level — nothing to show
                type_path = str(out_dir / f"level_{lvl}_edges_{type_name}.png")
                Image.fromarray(255 - type_arr).save(type_path)
                level_edge_map_paths[type_name] = type_path
        elif edge_maps is not None and medium_strategy is not None:
            styled = _apply_medium_to_edge_maps(edge_maps, medium_strategy)
            effective_outlines = _composite_edge_maps(styled)
            outline_arr = effective_outlines.get(outline_key, np.full((H, W), 255, dtype=np.uint8))
        elif medium_strategy is not None:
            # Fall back: apply strategy to existing composites
            effective_outlines = dict(outline_composites)
            if medium_strategy.emphasise_primary:
                prim = effective_outlines.get("outlines_primary")
                if prim is not None:
                    edge_mask = (prim == 0).astype(np.uint8)
                    kernel = np.ones((2, 2), np.uint8)
                    thickened = cv2.dilate(edge_mask, kernel)
                    effective_outlines["outlines_primary"] = np.where(thickened, 0, 255).astype(np.uint8)
            if medium_strategy.soften_secondary:
                sec = effective_outlines.get("outlines_primary_secondary")
                if sec is not None:
                    blended = np.clip(sec.astype(np.int32) + 60, 0, 255).astype(np.uint8)
                    effective_outlines["outlines_primary_secondary"] = blended
            outline_arr = effective_outlines.get(outline_key, np.full((H, W), 255, dtype=np.uint8))
        else:
            outline_arr = outline_composites.get(outline_key, np.full((H, W), 255, dtype=np.uint8))

        # ── Outlines PNG ───────────────────────────────────────────────────
        outline_pil = Image.fromarray(outline_arr)
        outline_path = str(out_dir / f"level_{lvl}_outlines.png")
        outline_pil.save(outline_path)

        # ── Value map PNG ──────────────────────────────────────────────────
        # Uses mass_regions (the level's full own-scale partition), not the
        # importance-filtered active_regions, so every pixel gets this level's
        # own coarse mass instead of leaking full-resolution zone_map detail.
        value_arr  = _render_value_lut(zone_map, value_zones, mass_regions, label_maps, H, W,
                                       medium_strategy=medium_strategy)
        value_pil  = Image.fromarray(value_arr)
        value_path = str(out_dir / f"level_{lvl}_values.png")
        value_pil.save(value_path)

        # ── Flat colour PNG ────────────────────────────────────────────────
        colour_arr  = _render_colour_lut(mass_regions, families, label_maps, H, W, lvl,
                                         medium_strategy=medium_strategy,
                                         zones=value_zones)
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
            edge_maps=level_edge_map_paths,
        )

    return detail_levels


def _render_value_lut(
    zone_map: np.ndarray,
    zones: list[ValueZone],
    active_regions: list[Region],
    label_maps: dict[str, np.ndarray],
    H: int,
    W: int,
    medium_strategy: MediumStrategy | None = None,
) -> np.ndarray:
    n = len(zones)

    def _zone_grey(zone_idx: int) -> int:
        """Return grey value for a zone index, applying medium strategy."""
        if medium_strategy is not None and medium_strategy.compress_values and n > 0:
            group = zone_idx * 3 // n   # 0, 1, or 2
            grey = [30, 128, 220][group]
        else:
            # Find the zone with this id
            matched = next((z for z in zones if z.id == zone_idx), None)
            grey = matched.grey_value if matched is not None else 128
        if medium_strategy is not None and medium_strategy.value_contrast != 1.0:
            grey = int(np.clip((grey - 128) * medium_strategy.value_contrast + 128, 0, 255))
        return grey

    # Build a zone_id → adjusted grey mapping
    zone_grey = {z.id: _zone_grey(z.id) for z in zones}
    # Start from zone_map
    out = np.full((H, W), 128, dtype=np.uint8)
    for z in zones:
        out[zone_map == z.id] = zone_grey[z.id]

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
    medium_strategy: MediumStrategy | None = None,
    zones: list[ValueZone] | None = None,
) -> np.ndarray:
    if medium_strategy is not None:
        alpha = medium_strategy.colour_alpha * (0.7 + lvl * 0.06)
        alpha = min(alpha, 0.95)
    else:
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
                if medium_strategy is not None and medium_strategy.greyscale_colours:
                    # Use zone grey value instead of colour family hue
                    zone_idx = r.value_zone
                    if zones is not None:
                        matched = next((z for z in zones if z.id == zone_idx), None)
                        grey = matched.grey_value if matched is not None else 128
                    else:
                        grey = 128
                    if medium_strategy.value_contrast != 1.0:
                        grey = int(np.clip((grey - 128) * medium_strategy.value_contrast + 128, 0, 255))
                    lut[r.source_label] = (grey, grey, grey)
                else:
                    cf_id = min(r.colour_family_id, len(families) - 1)
                    base = np.array(families[cf_id].base_rgb, dtype=np.float32)
                    tinted = np.clip(base * alpha + bg * (1 - alpha), 0, 255).astype(np.uint8)
                    lut[r.source_label] = tinted
        clipped_lm = lm.clip(0, max_lbl - 1)
        out = np.where((lm < max_lbl)[:, :, None], lut[clipped_lm], out)

    # A10: preserve_whites — LUT approach, O(P) per scale instead of O(P×R)
    if medium_strategy is not None and medium_strategy.preserve_whites:
        by_scale_white: dict[str, set[int]] = defaultdict(set)
        for r in active_regions:
            if r.mean_lab[0] > 80:
                by_scale_white[r.scale].add(r.source_label)
        for sc, white_lbls in by_scale_white.items():
            lm = label_maps.get(sc)
            if lm is None:
                continue
            max_lbl = int(lm.max()) + 1
            white_lut = np.zeros(max_lbl, dtype=bool)
            for sl in white_lbls:
                if sl < max_lbl:
                    white_lut[sl] = True
            clipped_lm = lm.clip(0, max_lbl - 1)
            white_px = (lm < max_lbl) & white_lut[clipped_lm]
            out[white_px] = (248, 248, 248)

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


def _apply_medium_to_edge_maps(
    edge_maps: dict[str, np.ndarray],
    strategy: MediumStrategy,
) -> dict[str, np.ndarray]:
    """
    A9: Apply MediumStrategy to individual edge maps (primary/secondary/decorative/texture)
    BEFORE compositing. Returns new styled dict without mutating the originals.
    """
    styled = {k: arr.copy() for k, arr in edge_maps.items()}

    if strategy.emphasise_primary:
        prim = styled.get("primary")
        if prim is not None:
            kernel = np.ones((2, 2), np.uint8)
            styled["primary"] = cv2.dilate(prim, kernel)

    if strategy.soften_secondary:
        sec = styled.get("secondary")
        if sec is not None:
            # Reduce secondary map opacity: threshold at higher value → fewer pixels
            styled["secondary"] = (sec * 0.5).astype(np.uint8)

    if not strategy.include_texture_edges:
        # Watercolour/charcoal: clear texture map entirely
        if "texture" in styled:
            styled["texture"] = np.zeros_like(styled["texture"])

    return styled


def _composite_edge_maps(styled: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """
    Re-composite individual edge maps into the four composite keys expected by render_detail_levels.
    Returns white-background (255=white, 0=line) composites, same as render_outline_levels.
    """
    def _comp(*keys: str) -> np.ndarray:
        base = np.zeros_like(next(iter(styled.values())))
        for k in keys:
            m = styled.get(k)
            if m is not None:
                base = np.maximum(base, m)
        return 255 - base

    return {
        "outlines_primary":           _comp("primary"),
        "outlines_primary_secondary": _comp("primary", "secondary"),
        "outlines_detailed":          _comp("primary", "secondary", "decorative"),
        "outlines_full":              _comp("primary", "secondary", "decorative", "texture"),
    }


def _composite_all_edge_maps(maps: dict[str, np.ndarray]) -> np.ndarray:
    """
    Composite every type map present into a single white-bg/black-line image.
    Used for level-aware outlines, where the input maps are already filtered
    to exactly the types+edges relevant for that level, so no further
    type-subset selection is needed.
    """
    if not maps:
        return None
    base = np.zeros_like(next(iter(maps.values())))
    for m in maps.values():
        if m is not None:
            base = np.maximum(base, m)
    return 255 - base


def render_paint_by_numbers(
    label_maps: dict[str, np.ndarray],
    regions: list[Region],
    palette,
    out_path,
    level_scale: str = "l4",
) -> str | None:
    """
    Paint-by-numbers page generated from the merge-tree hierarchy itself,
    so its regions are the SAME masses the lesson teaches. The previous
    standalone RAG cut_threshold implementation chain-merged soft-edged
    photos (sky↔land through a hazy horizon) into one giant region.

    Each l4 region is tinted toward white with its palette colour and
    numbered with that colour's palette index; boundaries are drawn from
    the label map directly.
    """
    from PIL import ImageDraw
    from skimage.segmentation import find_boundaries
    from ..utils.fonts import get_font

    lm = label_maps.get(level_scale)
    if lm is None and label_maps:
        level_scale, lm = sorted(label_maps.items())[-1]
    if lm is None:
        return None

    regs = [r for r in regions if r.scale == level_scale]
    if not regs:
        return None

    H, W = lm.shape
    max_lbl = int(lm.max())
    pal_rgb = {p.id: tuple(p.base_rgb) for p in palette}
    n_pal = max(len(palette), 1)

    lut = np.full((max_lbl + 1, 3), 255, dtype=np.uint8)
    for r in regs:
        rgb = pal_rgb.get(r.colour_family_id, tuple(r.mean_rgb))
        tint = tuple(int(c + (255 - c) * 0.45) for c in rgb)
        if 0 <= r.source_label <= max_lbl:
            lut[r.source_label] = tint

    out = lut[lm]
    out[find_boundaries(lm, mode="thick")] = (70, 66, 60)

    img = Image.fromarray(out)
    dr = ImageDraw.Draw(img)
    font = get_font(max(10, min(H, W) // 60))
    min_area_for_number = H * W * 0.0008
    for r in regs:
        if r.area < min_area_for_number:
            continue
        # Region.centroid is stored (x, y)
        cx, cy = r.centroid if len(r.centroid) == 2 else (W / 2, H / 2)
        number = (r.colour_family_id % n_pal) + 1
        rgb = pal_rgb.get(r.colour_family_id, (128, 128, 128))
        lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
        colour = (40, 38, 34) if lum > 100 else (30, 28, 25)
        dr.text((float(cx) - 4, float(cy) - 6), str(number), fill=colour, font=font)

    img.save(str(out_path))
    return str(out_path)


def render_study_overlay(
    label_maps: dict[str, np.ndarray],
    reference_rgb: np.ndarray,
    out_path,
    level_scale: str = "l5",
) -> str | None:
    """
    Detail-study overlay: thin white contours of the finest partition drawn
    directly ON the reference — the digital equivalent of tracing colour
    regions by hand on the artwork (white gel pen on a print). Unlike the
    teaching outlines this is deliberately dense: it is an analysis tool,
    not a block-in guide.
    """
    from skimage.segmentation import find_boundaries

    lm = label_maps.get(level_scale)
    if lm is None:
        return None

    H, W = lm.shape
    ref = reference_rgb
    if ref.shape[:2] != (H, W):
        ref = cv2.resize(ref, (W, H), interpolation=cv2.INTER_AREA)
    out = ref.copy()

    b = find_boundaries(lm, mode="inner")
    # faint dark halo first so the white line reads on light areas too
    halo = cv2.dilate(b.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    out[halo & ~b] = (out[halo & ~b] * 0.65).astype(np.uint8)
    out[b] = (250, 248, 242)

    Image.fromarray(out).save(str(out_path))
    return str(out_path)
