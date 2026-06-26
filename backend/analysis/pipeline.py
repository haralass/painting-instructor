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
from .edges import extract_edge_hierarchy, render_outline_levels, export_edges_svg
from .renderer import render_detail_levels
from .models import _get_medium_strategy

log = logging.getLogger(__name__)


def run_hierarchical_analysis(
    img: Image.Image,
    out_dir: Path,
    palette_size: int,
    detail_level: int,
    value_zones: int,
    medium: str,
    fg_mask: np.ndarray | None = None,
    seed: int = 42,
    texture_detail: bool = True,
    background_detail: bool = False,
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
        detail_level=detail_level,
        n_value_zones=value_zones,
        value_colour_families=colour_internal,
        seed=seed,
    )

    # Assign value_zone region_ids back to zone objects
    for z in zones:
        z.region_ids = [r.id for r in regions if r.value_zone == z.id]

    # Assign colour family linked_region_ids
    for f in families:
        f.linked_region_ids = [r.id for r in regions if r.colour_family_id == f.id]

    # ── 4. Edge hierarchy ─────────────────────────────────────────────────────
    # Use l3/l4 for edge context (good structural detail)
    label_map_for_edges = None
    edge_scale = None
    for sc in ["l3", "l4", "l2", "l5", "l1"]:
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
        medium_strategy=strategy,    # NEW
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
    def _lvl_dict(dl):
        return {
            "level":      dl.level,
            "label":      dl.label,
            "outlines":   dl.outlines,
            "regions":    dl.regions,
            "values":     dl.values,
            "colours":    dl.colours,
            "region_ids": dl.region_ids[:200],  # truncate for JSON
        }

    return {
        "detail_levels":       {k: _lvl_dict(v) for k, v in detail_levels.items()},
        "palette":             [p.model_dump() for p in palette],
        "colour_families":     [f.model_dump() for f in families],
        "value_zone_list":     [z.model_dump() for z in zones],
        "n_regions":           len(regions),
        "n_edges":             len(edges),
        "value_zones_path":    zone_map_path,
        "regions_json":        str(regions_path),
        "edges_json":          str(edges_path),
        "edges_svg":           str(svg_path),
        "edge_scale":          edge_scale,
        "label_to_region_id":  label_to_region_id,
    }
