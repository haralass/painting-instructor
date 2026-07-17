from __future__ import annotations
"""Local ("Analyse this area") region analysis (Phase 2 leftover).

Runs the same hierarchical analysis pipeline the whole-image lesson uses, but
scoped to a rectangle the student drags on the viewer. The crop is always cut
from the ORIGINAL, full-resolution reference file
(``outputs/{job_id}/reference.*``) — never from a resized preview or any
generated/overlay asset — so a local study never compounds resampling error
on top of the whole-image analysis.

Selection geometry travels in ORIGINAL-image pixels end to end (the one
coordinate system convention in ``frontend/app/lib/imageCoords.ts``). The
crop itself may be downscaled for runtime (``MAX_WORKING_SIDE``); the
returned ``offset``/``scale`` let a caller map any point in the local result
back to the parent image:

    parent_px = offset + local_px / scale
"""
import json
import logging
import math
import uuid
from pathlib import Path

from PIL import Image

from .pipeline import run_hierarchical_analysis
from ..utils.paths import job_dir, outputs_root, rel_to_outputs

log = logging.getLogger(__name__)

# Selections smaller than this (in ORIGINAL px, either side) are rejected —
# too small to say anything useful and risk breaking pipeline steps that
# assume a minimum number of pixels (k-means palette, region hierarchy).
MIN_CROP_SIDE = 32

# Crop is downscaled so its longer side is at most this many px before
# running the full hierarchy — keeps a local re-analysis fast regardless of
# how large the original reference or the selection is.
MAX_WORKING_SIDE = 1024


class LocalAnalysisError(ValueError):
    """Bad bbox (degenerate/non-numeric/too small). Callers map this to a 422."""


def _clamp_bbox(bbox: dict, width: int, height: int) -> dict:
    """Normalise + clamp a selection bbox (ORIGINAL image px) to integer
    bounds inside the reference image. Mirrors
    frontend/app/lib/imageCoords.ts:bboxToCropRect so both sides agree on
    what "the selection" means."""
    try:
        x = float(bbox["x"]); y = float(bbox["y"])
        w = float(bbox["w"]); h = float(bbox["h"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LocalAnalysisError(f"bbox must have numeric x, y, w, h: {exc}") from exc
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        raise LocalAnalysisError("bbox values must be finite numbers")

    x0 = max(0.0, min(x, x + w))
    y0 = max(0.0, min(y, y + h))
    x1 = min(float(width),  max(x, x + w))
    y1 = min(float(height), max(y, y + h))

    ix0 = max(0, math.floor(x0))
    iy0 = max(0, math.floor(y0))
    ix1 = min(width,  math.ceil(x1))
    iy1 = min(height, math.ceil(y1))

    return {"x": ix0, "y": iy0, "w": max(0, ix1 - ix0), "h": max(0, iy1 - iy0)}


def _load_job_settings(job_out: Path) -> dict:
    """Pull medium/palette/value_zones from the parent job's manifest so a
    local re-analysis matches the lesson it zooms into, instead of drifting
    to unrelated defaults. Missing/unreadable manifest -> empty (defaults)."""
    manifest_path = job_out / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text()).get("input", {}) or {}
    except Exception:
        return {}


def run_local_analysis(
    job_id: str,
    bbox: dict,
    *,
    medium: str | None = None,
    palette_size: int | None = None,
    value_zones: int | None = None,
    region_complexity: int | None = None,
) -> dict:
    """Crop ``bbox`` (ORIGINAL image px) out of the job's full-resolution
    reference and run the full hierarchical analysis on it.

    Raises:
        FileNotFoundError: no ``reference.*`` on disk for this job.
        LocalAnalysisError: bbox is degenerate, non-numeric, or too small
            after clamping to the image bounds.
    """
    job_out = job_dir(job_id)
    reference = next(iter(job_out.glob("reference.*")), None)
    if reference is None:
        raise FileNotFoundError(f"No reference image found for job {job_id!r}")

    # Load the ORIGINAL, full-resolution file — the house rule this module
    # exists to enforce. Never touch a level_*/overlay/preview asset here.
    img = Image.open(reference)
    img.load()
    img = img.convert("RGB")
    width, height = img.size

    clamped = _clamp_bbox(bbox, width, height)
    if clamped["w"] < MIN_CROP_SIDE or clamped["h"] < MIN_CROP_SIDE:
        raise LocalAnalysisError(
            f"selection too small — need at least {MIN_CROP_SIDE}x{MIN_CROP_SIDE}px "
            f"inside the image, got {clamped['w']}x{clamped['h']}px after clamping"
        )

    settings = _load_job_settings(job_out)
    eff_medium      = medium or settings.get("medium", "oil")
    eff_palette     = palette_size or settings.get("palette_size", 12)
    eff_zones       = value_zones or settings.get("value_zones", 5)
    eff_complexity  = region_complexity or settings.get("region_complexity", 3)

    crop = img.crop((
        clamped["x"], clamped["y"],
        clamped["x"] + clamped["w"], clamped["y"] + clamped["h"],
    ))
    crop_w, crop_h = crop.size

    # Downscale the CROP (not the original) for runtime; remember the exact
    # scale actually applied so callers can map back:
    #   parent_px = offset + local_px / scale
    scale = 1.0
    max_side = max(crop_w, crop_h)
    if max_side > MAX_WORKING_SIDE:
        target = MAX_WORKING_SIDE / max_side
        work_w = max(1, round(crop_w * target))
        work_h = max(1, round(crop_h * target))
        crop = crop.resize((work_w, work_h), Image.LANCZOS)
        scale = work_w / crop_w   # exact ratio actually applied (rounding-safe)

    selection_id = uuid.uuid4().hex[:10]
    local_dir = job_out / "local" / selection_id
    local_dir.mkdir(parents=True, exist_ok=True)

    # Save the working-size crop as the background for a focused construction
    # view (its pixel grid matches the child drawing's analysis coordinates).
    crop_path = local_dir / "crop.jpg"
    try:
        crop.convert("RGB").save(crop_path, quality=90)
    except Exception:
        crop_path = None

    # Subject mask + depth for the CROP, so the child drawing construction
    # (built inside run_hierarchical_analysis) isolates the subject properly at
    # this local resolution instead of falling back to whole-crop regions.
    # Both are optional ML — a failure just yields the region fallback.
    import numpy as _np
    subj_mask = None
    depth_lbl = None
    try:
        from .subject import subject_mask as _subject_mask
        subj_mask = _subject_mask(crop)
    except Exception:
        subj_mask = None
    try:
        from .depth import depth_planes as _depth_planes
        depth_lbl = _depth_planes(crop, 3)
    except Exception:
        depth_lbl = None
    fg_mask = (subj_mask > 0.5).astype(_np.uint8) if subj_mask is not None else None

    hier = run_hierarchical_analysis(
        img=crop,
        out_dir=local_dir,
        palette_size=eff_palette,
        value_zones=eff_zones,
        medium=eff_medium,
        region_complexity=eff_complexity,
        fg_mask=fg_mask,
        subj_mask=subj_mask,
        depth_lbl=depth_lbl,
        job_id=f"{job_id}/local/{selection_id}",
    )

    detail_levels = hier.get("detail_levels", {}) or {}
    # A single representative level keeps the response (and the panel that
    # renders it) simple; prefer the mid-detail level, fall back to whatever
    # rendered for very small crops that only produced coarser levels.
    level_key = "3" if "3" in detail_levels else next(iter(detail_levels), None)
    level_data = detail_levels.get(level_key, {}) if level_key else {}

    label_maps = hier.get("label_maps", {}) or {}
    label_map_path = label_maps.get(int(level_key)) if level_key else None

    def _rel(p: str | None) -> str | None:
        return rel_to_outputs(p) if p else None

    assets = {
        "outlines":     _rel(level_data.get("outlines")),
        "regions":      _rel(level_data.get("regions")),
        "values":       _rel(level_data.get("values")),
        "colours":      _rel(level_data.get("colours")),
        "label_map":    _rel(label_map_path),
        "regions_json": _rel(hier.get("regions_json")),
        "drawing_json": _rel(hier.get("drawing_json")),   # child construction for the crop
        "crop":         _rel(str(crop_path)) if crop_path else None,  # background for the nested view
        "detail_level": int(level_key) if level_key else None,
    }

    # A focused local construction summary (brief §9) — a compact, honest
    # read of how the selected region is built, from the child drawing.
    drawing_summary = _drawing_summary(hier.get("drawing"))

    return {
        "selection_id": selection_id,
        "job_id":        job_id,
        "bbox":           clamped,                          # ORIGINAL image px — the true crop rect
        "offset":         {"x": clamped["x"], "y": clamped["y"]},
        "scale":          scale,                             # working px per crop px
        "working_size":   {"width": crop.size[0], "height": crop.size[1]},
        "assets":         assets,
        "drawing_summary": drawing_summary,
    }


_CAUSE_WORD = {
    "object_boundary": "an object boundary", "depth": "a depth change",
    "illumination": "a light/shadow edge", "reflectance": "a colour change",
    "texture": "surface texture",
}


def _drawing_summary(drawing: dict | None) -> dict | None:
    """Compact, honest summary of the child drawing construction for the
    'analyse this area' panel — subject fit, landmark/structure counts, and
    what the outer edge most likely is (only stated when confident)."""
    if not drawing:
        return None
    bounds = drawing.get("subject_bounds", {}) or {}
    silh = drawing.get("silhouette") or {}
    cause = (silh.get("edge_cause") or {})
    cause_word = None
    if cause.get("primary") and float(cause.get("confidence", 0) or 0) >= 0.4:
        cause_word = _CAUSE_WORD.get(cause["primary"], cause["primary"])
    env = drawing.get("envelope") or {}
    return {
        "subject_source":    bounds.get("source"),
        "occupied_fraction": bounds.get("occupied_fraction"),
        "n_landmarks":       len(drawing.get("landmarks", []) or []),
        "envelope_segments": env.get("segment_count"),
        "n_internal_paths":  len(drawing.get("internal_paths", []) or []),
        "silhouette_cause":  cause_word,
    }
