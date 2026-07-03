from __future__ import annotations
import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image

from .preprocessing import prepare
from .values import compute_value_zones, render_value_map
from .colours import extract_colour_families
from .regions import build_region_hierarchy
from .edges import (
    extract_edge_hierarchy, render_outline_levels, export_edges_svg,
    build_region_ancestor_chain, filter_edges_for_level, bucket_edge_maps,
)
from .renderer import render_detail_levels
from .models import _get_medium_strategy
from ..utils.paths import rel_to_outputs

log = logging.getLogger(__name__)


def run_hierarchical_analysis(
    img: Image.Image,
    out_dir: Path,
    palette_size: int,
    value_zones: int,
    medium: str,
    fg_mask: np.ndarray | None = None,
    seed: int = 42,
    texture_detail: bool = True,
    background_detail: bool = False,
    region_complexity: int = 3,  # A6: 1–5, controls hierarchy resolution independently of palette
) -> dict:
    """
    Full hierarchical analysis pipeline.

    Returns a dict suitable for embedding in the task manifest, with keys:
      detail_levels, palette, colour_families, value_zone_list
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    strategy = _get_medium_strategy(medium)

    cache = prepare(img)

    # ── 1. Value zones ────────────────────────────────────────────────────────
    zone_map, zones = compute_value_zones(cache, value_zones)
    zone_map_path   = str(out_dir / "value_zones.png")
    value_img       = render_value_map(zone_map, zones)
    Image.fromarray(np.stack([value_img] * 3, axis=-1) if value_img.ndim == 2 else value_img).save(zone_map_path)

    # ── 2. Colour families ────────────────────────────────────────────────────
    families, palette, colour_internal = extract_colour_families(
        cache, palette_size=palette_size, seed=seed
    )

    # ── 3. Multi-scale region hierarchy ───────────────────────────────────────
    label_maps, regions = build_region_hierarchy(
        cache=cache,
        palette_size=palette_size,
        n_value_zones=value_zones,
        value_colour_families=colour_internal,
        seed=seed,
        zone_map=zone_map,
        zones=zones,
        region_complexity=region_complexity,  # A6
    )

    # Assign value_zone region_ids back to zone objects
    for z in zones:
        z.region_ids = [r.id for r in regions if r.value_zone == z.id]

    # Assign colour family linked_region_ids
    for f in families:
        f.linked_region_ids = [r.id for r in regions if r.colour_family_id == f.id]

    # ── 4. Edge hierarchy ─────────────────────────────────────────────────────
    # Prefer the FINEST available scale for edge/region context: Region.parent_id
    # only points to coarser levels, so ancestor roll-up for level-aware outlines
    # (below) can only look coarser than edge_scale, never finer.
    label_map_for_edges = None
    edge_scale = None
    for sc in ["l5", "l4", "l3", "l2", "l1"]:
        if sc in label_maps:
            label_map_for_edges = label_maps[sc]
            edge_scale = sc
            break

    # Build label→region_id mapping for the chosen scale
    label_to_region_id: dict[int, int] = {}
    if edge_scale is not None:
        label_to_region_id = {
            r.source_label: r.id
            for r in regions
            if r.scale == edge_scale
        }

    effective_texture = texture_detail and strategy.include_texture_edges
    edges, edge_maps = extract_edge_hierarchy(
        cache, label_map_for_edges, fg_mask,
        include_texture=effective_texture,
        include_background=background_detail,
        label_to_region_id=label_to_region_id,
    )
    outline_composites = render_outline_levels(edge_maps)

    # Save individual outline composites
    from PIL import Image as PILImage
    for name, arr in outline_composites.items():
        PILImage.fromarray(arr).save(str(out_dir / f"{name}.png"))

    # Save edge map maps (raw binary)
    for name, arr in edge_maps.items():
        PILImage.fromarray(255 - arr).save(str(out_dir / f"edges_{name}.png"))

    # ── 4b. Level-aware outline filtering ─────────────────────────────────────
    # Edges classified above are global; for each of the 5 detail levels we
    # additionally drop edges that are interior noise at that level's own
    # region resolution (both sides roll up to the same coarser mass), so
    # Level 1 outlines reflect l1 structure and Level 5 shows full l5 detail
    # instead of every level just being a type-subset of one fixed-scale map.
    level_edge_maps: dict[int, dict[str, np.ndarray]] = {}
    if edge_scale is not None:
        ancestor_chains = build_region_ancestor_chain(regions, edge_scale)
        for lvl in range(1, 6):
            target_scale = f"l{lvl}"
            level_edges = filter_edges_for_level(edges, lvl, target_scale, ancestor_chains)
            level_edge_maps[lvl] = bucket_edge_maps(level_edges, cache.H, cache.W)
    else:
        for lvl in range(1, 6):
            level_edge_maps[lvl] = edge_maps

    # ── 5. Render 5 detail levels ─────────────────────────────────────────────
    detail_levels = render_detail_levels(
        cache=cache,
        label_maps=label_maps,
        regions=regions,
        families=families,
        value_zones=zones,
        zone_map=zone_map,
        outline_composites=outline_composites,
        out_dir=out_dir,
        edges=edges,
        medium_strategy=strategy,
        edge_maps=edge_maps,  # A9: pass individual maps for per-medium processing
        level_edge_maps=level_edge_maps,  # level-aware outline source (see above)
    )

    # ── 6. Write regions JSON ─────────────────────────────────────────────────
    regions_path = out_dir / "regions.json"
    regions_path.write_text(json.dumps(
        [r.model_dump() for r in regions], indent=2
    ))

    # ── 7. Write edges JSON ───────────────────────────────────────────────────
    edges_path = out_dir / "edges.json"
    edges_path.write_text(json.dumps(
        [e.model_dump() for e in edges[:5000]], indent=2  # cap to avoid huge files
    ))

    svg_str  = export_edges_svg(edges, cache.W, cache.H)
    svg_path = out_dir / "edges.svg"
    svg_path.write_text(svg_str)

    # ── Build return dict ─────────────────────────────────────────────────────
    # A1: all asset paths are kept absolute here so callers can call .exists();
    # tasks.py._build_manifest normalises them to relative paths before writing JSON.
    def _lvl_dict(dl):
        return {
            "level":      dl.level,
            "label":      dl.label,
            "outlines":   dl.outlines,   # absolute — normalised in _build_manifest
            "regions":    dl.regions,
            "values":     dl.values,
            "colours":    dl.colours,
            "region_ids": dl.region_ids[:200],
        }

    # A4: individual edge map absolute paths (normalised in _build_manifest)
    _edge_map_paths = {
        name: str(out_dir / f"edges_{name}.png")
        for name in ("primary", "secondary", "decorative", "texture")
        if (out_dir / f"edges_{name}.png").exists()
    }

    # Global (non-level-filtered) outline composite paths — used by lesson_plan
    # to resolve stage layer keys like "outlines_primary_secondary".
    _outline_composite_paths = {
        name: str(out_dir / f"{name}.png")
        for name in outline_composites
        if (out_dir / f"{name}.png").exists()
    }

    return {
        "detail_levels":       {k: _lvl_dict(v) for k, v in detail_levels.items()},
        "palette":             [p.model_dump() for p in palette],
        "colour_families":     [f.model_dump() for f in families],
        "value_zone_list":     [z.model_dump() for z in zones],
        "n_regions":           len(regions),
        "n_edges":             len(edges),
        "value_zones_path":    zone_map_path,   # absolute — for internal use
        "regions_json":        str(regions_path),
        "edges_json":          str(edges_path),
        "edges_svg":           str(svg_path),
        "edge_scale":          edge_scale,
        "label_to_region_id":  label_to_region_id,
        "edge_maps":           _edge_map_paths,  # A4: individual maps for frontend sublayer toggles
        "outline_composites":  _outline_composite_paths,  # global composites for lesson_plan resolution
    }
