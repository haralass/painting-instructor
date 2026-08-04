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
    subj_mask: np.ndarray | None = None,   # Phase 3: float subject mask for drawing construction
    depth_lbl: np.ndarray | None = None,   # Phase 3: depth planes for edge-cause attribution
    job_id: str | None = None,
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

    # ── 3b. Persist per-level label maps (RGB-encoded region ids) ────────────
    # The viewer resolves a click straight to a Region: pixel → id via
    # id+1 = R + G·256 (0 = no region), then regions.json for the metadata.
    # Lossless PNG; same pixel grid as every other analysis output (§21.D).
    label_map_paths: dict[int, str] = {}
    for lvl in range(1, 6):
        lm = label_maps.get(f"l{lvl}")
        if lm is None:
            continue
        lut = np.zeros(int(lm.max()) + 2, dtype=np.int32)  # 0 = background/none
        for r in regions:
            if r.scale == f"l{lvl}" and 0 <= r.source_label <= lm.max():
                lut[r.source_label] = r.id + 1
        ids = lut[np.clip(lm, 0, len(lut) - 1)]
        rgb = np.zeros((*ids.shape, 3), dtype=np.uint8)
        rgb[..., 0] = ids & 0xFF
        rgb[..., 1] = (ids >> 8) & 0xFF
        p = str(out_dir / f"level_{lvl}_labelmap.png")
        Image.fromarray(rgb).save(p)
        label_map_paths[lvl] = p

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

    # ── 5b. Paint-by-numbers from the SAME hierarchy the lesson teaches ──────
    # Overwrites the classic standalone page (when that step produced one):
    # one segmentation everywhere keeps the guides consistent with the
    # lesson's masses, and the merge tree doesn't chain-merge soft horizons
    # the way the old RAG cut_threshold did.
    from .renderer import render_paint_by_numbers
    pbn_path: str | None = None
    try:
        pbn_path = render_paint_by_numbers(
            label_maps=label_maps,
            regions=regions,
            palette=palette,
            out_path=out_dir / "color_by_number.png",
        )
    except Exception:
        log.warning("render_paint_by_numbers failed", exc_info=True)

    # ── 5c. Detail-study overlay — white contours drawn ON the reference ─────
    from .renderer import render_study_overlay, render_smart_dot_to_dot
    study_path: str | None = None
    try:
        study_path = render_study_overlay(
            label_maps=label_maps,
            reference_rgb=cache.rgb,
            out_path=out_dir / "study_overlay.png",
        )
    except Exception:
        log.warning("render_study_overlay failed", exc_info=True)

    # ── 5d. Dot-to-dot placeholder — the REAL numbered exercise is generated
    #      after the drawing analysis below (it needs the vector paths); this
    #      only keeps a fallback if that fails. ──────────────────────────────
    dots_path: str | None = None
    dot_variants: dict = {}

    # ── 5e. Drawing construction analysis (Phase 3) ──────────────────────────
    # Turn the edges/regions/subject/depth signals into a stored, structured
    # account of how the drawing is built (bounds → landmarks → envelope →
    # silhouette → internal structure), in a pedagogical order. Never fatal.
    drawing_path: str | None = None
    drawing_dict: dict | None = None
    try:
        from .drawing import build_drawing_analysis
        from .edge_cause import attach_edge_causes
        drawing = build_drawing_analysis(
            cache=cache, regions=regions, edges=edges,
            subj_mask=subj_mask, depth_lbl=depth_lbl, zone_map=zone_map,
            job_id=job_id,
        )
        attach_edge_causes(drawing, cache, depth_lbl, zone_map)
        drawing.source_assets = {
            "regions": "regions.json", "edges": "edges.json",
        }
        drawing_path = str(out_dir / "drawing.json")
        Path(drawing_path).write_text(drawing.model_dump_json(indent=2))
        drawing_dict = drawing.model_dump()
    except Exception:
        drawing_dict = None
        log.warning("drawing construction analysis failed", exc_info=True)

    # ── 5f. REAL numbered dot-to-dot (brief §14) from the vector paths:
    #    sequential numbering, dots dense on curves / sparse on straights,
    #    three difficulties + solution variants. ────────────────────────────
    if drawing_dict:
        try:
            from .dot_to_dot import render_all as render_dot_variants
            dot_variants = render_dot_variants(drawing_dict, out_dir)
            if "standard" in dot_variants:
                dots_path = dot_variants["standard"]["path"]
        except Exception:
            log.warning("numbered dot-to-dot failed", exc_info=True)
    if dots_path is None:
        # Fallback: the old label-map dots, so the page never goes missing.
        try:
            dots_lm = label_maps.get("l3", label_maps.get("l2"))
            if dots_lm is not None:
                r = render_smart_dot_to_dot(label_map=dots_lm, W=cache.W, H=cache.H,
                                            out_path=out_dir / "dot_to_dot.png")
                dots_path = r["path"] if r else None
        except Exception:
            log.warning("render_smart_dot_to_dot fallback failed", exc_info=True)

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
            "edge_maps":  dl.edge_maps,  # level-aware outline sublayers — absolute, normalised below
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
        "label_maps":          label_map_paths,  # per-level RGB-encoded region ids (viewer click-select)
        "drawing_json":        drawing_path,     # Phase 3 structured drawing construction
        "drawing":             drawing_dict,     # in-process dict for the Phase-4 lesson engine
        "paint_by_numbers":    pbn_path,   # hierarchy-based page (replaces classic when both exist)
        "study_overlay":       study_path, # white region contours ON the reference (detail study)
        "smart_dot_to_dot":    dots_path,  # numbered dot-to-dot page (standard difficulty)
        "dot_to_dot_variants": {k: {"n_dots": v["n_dots"],
                                     "path": v["path"], "solution": v.get("solution")}
                                 for k, v in dot_variants.items()},
    }
