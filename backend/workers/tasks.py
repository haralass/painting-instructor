from __future__ import annotations
import json
import logging
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from celery import Celery

from ..utils.paths import job_dir, rel_to_outputs, outputs_root

log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("art_book", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_serializer   = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content    = ["json"]

# Progress checkpoints per step
_PROGRESS = {
    "loading":          5,
    "preprocessing":    10,
    "line_art":         15,
    "notan":            25,
    "value_analysis":   30,
    "color_temperature":35,
    "color_palette":    42,
    "light_direction":  48,
    "color_by_number":  55,
    "dot_to_dot":       65,
    "hierarchical":     75,
    "analysis_ready":   80,   # NEW — preliminary manifest written
    "observations":     82,
    "rendering_extras": 85,   # NEW — starting video/PDF
    "video":            88,
    "pdf":              93,
    "manifest":         97,
    "completed":        100,
}


@celery_app.task(bind=True, name="art_book.run_pipeline")
def run_pipeline(
    self,
    img_path: str,
    job_id: str,
    medium: str = "oil",
    palette_size: int = 12,
    initial_view_level: int = 3,
    value_zones: int = 5,
    texture_detail: bool = True,
    background_detail: bool = False,
    region_complexity: int = 3,   # A6: 1–5 hierarchy resolution
    skill_level: str = "intermediate",
    # backward-compat alias
    n_colors: int = 0,
) -> dict:
    """
    Full painting instructor pipeline with per-step progress and error resilience.

    Steps:
      1. loading          — open & resize image
      2-7. (concurrent, independent of each other):
         line_art         — 3-layer composite + fg_mask
         notan            — adaptive value study
         color_temperature— LAB b* warm/cool map (fixed channel)
         color_palette    — K-means++ dominant colour chart
         light_direction  — Sobel histogram + 5-zone overlay
         color_by_number  — bilateral+RAG paint-by-numbers
      8. dot_to_dot       — skeleton arc-length numbered dots (needs line_art's result)
      9. hierarchical     — multi-scale region hierarchy + edge classification
     10. video            — progressive tutorial animation
     11. pdf              — A4 book of all pages that succeeded
     12. manifest         — manifest.json describing all outputs
    """
    import numpy as np
    from PIL import Image

    from ..preprocessing.processor import load_image
    from ..pipeline.line_art.processor import process_with_mask as line_art_with_mask
    from ..pipeline.artist_breakdown.processor import (
        notan, color_palette, color_temperature, light_direction_with_angle
    )
    from ..pipeline.color_by_number.processor import process as color_by_number
    from ..pipeline.dot_to_dot.processor import process as dot_to_dot
    from ..analysis.subject import subject_mask as compute_subject_mask
    from ..analysis.depth import depth_planes as compute_depth_planes
    from ..analysis.albedo_shading import local_vs_light_page
    from ..pipeline.video.processor import generate as make_video
    from ..pipeline.stroke_paint.processor import render_stroke_frames
    from ..teaching.mediums import get_medium
    from ..teaching.lesson import build_lesson_plan
    from ..teaching.pdf_book import build_tutorial_pdf
    from ..teaching.observations import generate_observations
    from ..teaching.planner import build_image_brief, attach_image_notes, load_regions

    # Resolve backward-compat alias
    if n_colors and not palette_size:
        palette_size = n_colors
    if not palette_size:
        palette_size = 12

    out_dir = job_dir(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: dict[str, str] = {}
    timings: dict[str, float] = {}

    def progress(name: str) -> None:
        pct = _PROGRESS.get(name, 5)
        msg = {
            "loading":          "Loading image",
            "line_art":         "Drawing outlines",
            "notan":            "Mapping values",
            "color_temperature":"Analysing warm/cool tones",
            "color_palette":    "Extracting colour palette",
            "light_direction":  "Finding light source",
            "color_by_number":  "Building paint-by-numbers",
            "dot_to_dot":       "Placing structural dots",
            "hierarchical":     "Building hierarchical regions",
            "analysis_ready":   "Analysis complete — generating extras",
            "observations":     "Looking at your image",
            "rendering_extras": "Rendering video and PDF",
            "video":            "Rendering tutorial video",
            "pdf":              "Assembling PDF book",
            "manifest":         "Writing manifest",
            "completed":        "Tutorial ready",
        }.get(name, name)
        self.update_state(
            state="PROGRESS",
            meta={"step": name, "progress": pct, "message": msg, "errors": errors},
        )

    def save(name: str, result: Image.Image) -> str:
        p = str(out_dir / f"{name}.png")
        result.save(p)
        return p

    def _run_silent(name: str, fn):
        """
        Time + error-capture a step without reporting progress. Celery binds
        the task's request context (self.request.id) thread-locally, so
        self.update_state() only works on the thread Celery itself invoked
        the task on — calling it from a ThreadPoolExecutor worker thread
        raises (task_id is None there). Used for steps run concurrently;
        the caller reports progress from the main thread instead.
        """
        t0 = time.perf_counter()
        try:
            result = fn()
            timings[name] = round(time.perf_counter() - t0, 2)
            return result
        except Exception:
            timings[name] = round(time.perf_counter() - t0, 2)
            tb = traceback.format_exc()
            errors[name] = tb
            log.warning("Pipeline step %r failed:\n%s", name, tb)
            return None

    def run(name: str, fn):
        """Run one pipeline step on the main thread; log errors without
        aborting the whole job."""
        progress(name)
        return _run_silent(name, fn)

    # ── Step 1: Load ──────────────────────────────────────────────────────────
    progress("loading")
    img = load_image(img_path)
    pages: list[str] = []
    suffix = Path(img_path).suffix or ".jpg"

    # Copy original reference image to output directory
    import shutil
    ref_path = str(out_dir / f"reference{suffix}")
    shutil.copy2(img_path, ref_path)

    # ── Subject mask (optional local ML, bundled U²-Netp) ─────────────────────
    # Computed once up front: it feeds line-art's silhouette AND its own focal
    # study below. Returns a float [0,1] mask or None (onnxruntime/model absent).
    subj_mask = _run_silent("subject_mask", lambda: compute_subject_mask(img))
    subj_binary = (subj_mask > 0.5).astype(np.uint8) if subj_mask is not None else None

    # ── Depth planes (optional local ML, Depth-Anything-V2) ───────────────────
    # Foreground / middle-ground / background bands for atmospheric-perspective
    # teaching. Returns a uint8 label map (0=far..2=near) or None (model absent).
    depth_lbl = _run_silent("depth", lambda: compute_depth_planes(img, 3))

    # ── Steps 2-7: independent classic-analysis steps — run concurrently ──────
    # None of these six depend on each other's output (only dot_to_dot below
    # needs line_art's result), so running them in a thread pool instead of
    # one after another cuts wall-clock pipeline time — they're numpy/opencv/
    # sklearn heavy and release the GIL during the actual computation.
    # `run()` still records each step's own progress/timing/errors exactly as
    # it did when called sequentially.
    parallel_jobs = {
        "line_art":          lambda: line_art_with_mask(img, fg_mask=subj_binary),
        "notan":             lambda: notan(img, zones=value_zones),
        "color_temperature": lambda: color_temperature(img),
        "color_palette":     lambda: color_palette(img, n_colors=palette_size),
        "light_direction":   lambda: light_direction_with_angle(img),
        "color_by_number":   lambda: color_by_number(img, n_colors=palette_size),
    }
    parallel_results: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=len(parallel_jobs)) as executor:
        future_to_name = {executor.submit(_run_silent, name, fn): name for name, fn in parallel_jobs.items()}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            parallel_results[name] = future.result()
            progress(name)  # reported from the main thread as each step finishes

    la_result, fg_mask = None, None
    la_out = parallel_results.get("line_art")
    if la_out:
        la_result, fg_mask = la_out
        pages.append(save("line_art", la_result))

    # ── Focal Subject study (from the U²-Net mask) ────────────────────────────
    # Subject kept in full colour, background desaturated and lifted toward the
    # paper — a focal-point teaching aid ("this is what the eye must land on").
    if subj_mask is not None:
        def _focal_subject() -> Image.Image:
            rgb  = np.asarray(img.convert("RGB"), dtype=np.float32)
            m    = np.clip(subj_mask, 0.0, 1.0)[..., None]
            gray = rgb.mean(axis=2, keepdims=True)
            muted = 0.55 * gray + 0.45 * 245.0          # desaturate + lighten
            out  = rgb * m + muted * (1.0 - m)
            return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

        focal = run("subject_focus", _focal_subject)
        if focal:
            pages.append(save("subject_focus", focal))
            # keep the raw mask around for teaching (focal weighting), not as a page
            Image.fromarray((np.clip(subj_mask, 0, 1) * 255).astype(np.uint8)).save(
                str(out_dir / "subject_mask.png")
            )

    # ── Depth Planes study (from Depth-Anything) ──────────────────────────────
    # The three distance bands tinted over a desaturated base — foreground warm,
    # background cool — so the learner sees the planes and the warm-near/cool-far
    # rule of atmospheric perspective at a glance.
    if depth_lbl is not None:
        def _planes_study() -> Image.Image:
            rgb  = np.asarray(img.convert("RGB"), dtype=np.float32)
            gray = rgb.mean(axis=2, keepdims=True)
            base = 0.5 * rgb + 0.5 * gray               # desaturate so tints read
            tints = {
                0: np.array([120, 150, 190], np.float32),  # far  → cool
                1: np.array([200, 195, 185], np.float32),  # mid  → neutral
                2: np.array([210, 150, 110], np.float32),  # near → warm
            }
            out = base.copy()
            for lbl, tint in tints.items():
                mask = (depth_lbl == lbl)[..., None]
                out = np.where(mask, 0.7 * base + 0.3 * tint, out)
            return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

        planes = run("depth_planes", _planes_study)
        if planes:
            pages.append(save("depth_planes", planes))

    # ── Local Colour vs Light study (classical intrinsic split) ───────────────
    lvl_page = run("local_vs_light", lambda: local_vs_light_page(img))
    if lvl_page:
        pages.append(save("local_vs_light", lvl_page))

    notan_result = parallel_results.get("notan")
    if notan_result:
        pages.append(save("notan", notan_result))

    r = parallel_results.get("color_temperature")
    if r:
        pages.append(save("color_temperature", r))

    r = parallel_results.get("color_palette")
    if r:
        pages.append(save("color_palette", r))

    light_angle: float | None = None
    r = parallel_results.get("light_direction")
    if r:
        light_img, light_angle = r
        pages.append(save("light_direction", light_img))

    # Perf: O(P×E) full-image mask comparisons have been eliminated via per-label
    # LUT precomputation in color_by_number/processor.py.
    cbn_result = parallel_results.get("color_by_number")
    if cbn_result:
        pages.append(save("color_by_number", cbn_result))
    log.info("color_by_number timing: %.2fs", timings.get("color_by_number", 0.0))

    # ── Step 8: Dot to dot (reuses line art — no second edge detection) ───────
    r = run("dot_to_dot", lambda: dot_to_dot(
        img, n_dots=500,
        line_art_img=la_result,
        fg_mask=fg_mask,
    ))
    if r:
        pages.append(save("dot_to_dot", r))

    # ── Step 9: Hierarchical analysis (new architecture) — CRITICAL ──────────
    CRITICAL_STEPS = {"loading", "hierarchical"}
    try:
        from ..analysis.pipeline import run_hierarchical_analysis
        progress("hierarchical")
        t0 = time.perf_counter()
        hier = run_hierarchical_analysis(
            img=img,
            out_dir=out_dir,
            palette_size=palette_size,
            value_zones=value_zones,
            medium=medium,
            fg_mask=fg_mask,
            texture_detail=texture_detail,
            background_detail=background_detail,
            region_complexity=region_complexity,  # A6
        )
        timings["hierarchical"] = round(time.perf_counter() - t0, 2)
        # Append hierarchical detail level outputs as additional pages
        for lvl in range(1, 6):
            lvl_key = str(lvl)
            if lvl_key in hier.get("detail_levels", {}):
                lvl_data = hier["detail_levels"][lvl_key]
                for asset_key in ("outlines", "regions", "values"):
                    asset_path = lvl_data.get(asset_key)
                    if asset_path and Path(asset_path).exists():
                        pages.append(asset_path)
    except Exception:
        tb = traceback.format_exc()
        errors["hierarchical"] = tb
        log.error("Critical hierarchical analysis failed:\n%s", tb)
        raise RuntimeError(f"Critical hierarchical analysis failed:\n{tb}")
    hier = hier or {}

    # Hierarchy-based paint-by-numbers replaces the classic page; if the
    # classic step failed (no ML deps) it was never in `pages`, so add it.
    pbn_path = hier.get("paint_by_numbers")
    if pbn_path and not any(Path(p).name == "color_by_number.png" for p in pages):
        pages.append(pbn_path)
    if hier.get("study_overlay"):
        pages.append(hier["study_overlay"])
    if hier.get("smart_dot_to_dot") and not any(Path(p).name == "dot_to_dot.png" for p in pages):
        pages.append(hier["smart_dot_to_dot"])

    # ── Step 9a: Image brief — the personal part of the lesson. Deterministic,
    #    derived entirely from this job's own analysis data: which masses to
    #    block in first, where the light comes from, where the focal point is,
    #    which areas will tempt overworking. ─────────────────────────────────
    perspective_vp = None
    try:
        import numpy as _np
        from ..analysis.perspective import detect_vanishing_point
        perspective_vp = detect_vanishing_point(_np.asarray(img.convert("L")))
    except Exception:
        log.warning("vanishing point detection failed", exc_info=True)

    image_brief: dict = {}
    try:
        regions_data = load_regions(hier.get("regions_json", "")) if hier.get("regions_json") else []
        image_brief = build_image_brief(
            regions=regions_data,
            palette=hier.get("palette", []),
            value_zone_list=hier.get("value_zone_list", []),
            light_angle=light_angle,
            img_w=img.size[0],
            img_h=img.size[1],
            medium=medium,
            perspective=perspective_vp,
        )
    except Exception:
        tb = traceback.format_exc()
        errors["image_brief"] = tb
        log.warning("Image brief failed:\n%s", tb)

    # ── Build medium_cfg + lesson_plan ONCE ──────────────────────────────────
    # The plan was previously built three times (prelim manifest, this
    # absolute-path copy for the video/PDF, and again inside the final
    # _build_manifest) — each re-running attach_image_notes, so the copies
    # could silently diverge. Build the absolute-path plan here once, then
    # derive the outputs-relative form the manifest needs from it, so the two
    # path forms are guaranteed identical apart from the paths themselves.
    medium_cfg = get_medium(medium)
    classic_pages = [p for p in pages if not _is_hierarchical_asset(p) and p]
    lesson_plan_abs = build_lesson_plan(
        medium_cfg=medium_cfg,
        medium=medium,
        detail_levels=hier.get("detail_levels", {}),
        outline_composites=hier.get("outline_composites", {}),
        value_zones_map=hier.get("value_zones_path"),
        classic_pages=classic_pages,
        skill_level=skill_level,
    )
    if image_brief:
        lesson_plan_abs = attach_image_notes(lesson_plan_abs, image_brief, medium)
    lesson_plan_rel = _relativize_lesson_plan(lesson_plan_abs)

    # Write preliminary manifest immediately after hierarchical succeeds
    manifest_path = out_dir / "manifest.json"
    progress("analysis_ready")
    prelim_manifest = _build_manifest(
        job_id=job_id,
        img=img,
        medium=medium,
        palette_size=palette_size,
        initial_view_level=initial_view_level,
        value_zones=value_zones,
        pages=pages,
        video_path=None,   # not yet available
        pdf_path=None,
        hier=hier,
        timings=timings,
        errors=errors,
        ref_suffix=suffix,
        region_complexity=region_complexity,
        texture_detail=texture_detail,
        background_detail=background_detail,
        skill_level=skill_level,
        image_brief=image_brief,
        lesson_plan=lesson_plan_rel,
    )
    prelim_manifest["status"] = "analysis_ready"
    manifest_path.write_text(json.dumps(prelim_manifest, indent=2))

    # ── Step 9b: Personal observations — one vision call grounded in this
    #    job's actual palette/value zones/region count, unlike every other
    #    piece of teaching copy which is a static per-medium template. No-ops
    #    (returns None) when ANTHROPIC_API_KEY isn't configured. ──────────────
    progress("observations")
    personal_observations = None
    try:
        t0 = time.perf_counter()
        personal_observations = generate_observations(
            reference_path=ref_path,
            medium=medium,
            medium_cfg=medium_cfg,
            palette=hier.get("palette", []),
            value_zone_list=hier.get("value_zone_list", []),
            region_count=hier.get("n_regions", 0),
        )
        timings["observations"] = round(time.perf_counter() - t0, 2)
    except Exception:
        tb = traceback.format_exc()
        errors["observations"] = tb
        log.warning("Personal observations failed:\n%s", tb)

    # ── Step 10: Video — chapters follow the medium's real teaching stages ────
    progress("rendering_extras")
    video_path = None
    video_chapters: list[dict] = []
    if la_result and notan_result and cbn_result:
        progress("video")
        try:
            t0 = time.perf_counter()
            video_path = str(out_dir / "tutorial.mp4")
            stage_images = _resolve_stage_images(lesson_plan_abs)
            # Real oil strokes for the "painted stroke by stroke" phase; guarded
            # so any failure just falls back to the crossfade animation.
            stroke_frames = _run_silent("stroke_paint", lambda: render_stroke_frames(img, max_frames=40))
            video_result = make_video(
                reference=img,
                line_art=la_result,
                notan=notan_result,
                color_blocking=cbn_result,
                output_path=video_path,
                fps=24,
                out_w=1080,
                medium_stages=medium_cfg.get("stages", []),
                stage_images=stage_images,
                stroke_frames=stroke_frames,
            )
            video_chapters = video_result.get("chapters", [])
            timings["video"] = round(time.perf_counter() - t0, 2)
        except Exception:
            tb = traceback.format_exc()
            errors["video"] = tb
            log.warning("Video generation failed:\n%s", tb)
            video_path = None

    # ── Step 11: PDF — tutorial book built around the lesson_plan ──────────────
    progress("pdf")
    pdf_path = None
    try:
        t0 = time.perf_counter()
        pdf_path = str(out_dir / "tutorial_book.pdf")
        build_tutorial_pdf(
            out_path=pdf_path,
            reference_path=ref_path,
            medium=medium,
            medium_cfg=medium_cfg,
            detail_levels=hier.get("detail_levels", {}),
            lesson_plan=lesson_plan_abs,
            palette=hier.get("palette", []),
            value_zone_list=hier.get("value_zone_list", []),
            classic_pages=classic_pages,
            personal_observations=personal_observations,
        )
        timings["pdf"] = round(time.perf_counter() - t0, 2)
    except Exception:
        tb = traceback.format_exc()
        errors["pdf"] = tb
        log.warning("PDF assembly failed:\n%s", tb)
        pdf_path = None

    # ── Step 12: Manifest ─────────────────────────────────────────────────────
    progress("manifest")
    manifest = _build_manifest(
        job_id=job_id,
        img=img,
        medium=medium,
        palette_size=palette_size,
        initial_view_level=initial_view_level,
        value_zones=value_zones,
        pages=pages,
        video_path=video_path,
        pdf_path=pdf_path,
        hier=hier,
        timings=timings,
        errors=errors,
        ref_suffix=suffix,
        region_complexity=region_complexity,
        texture_detail=texture_detail,
        background_detail=background_detail,
        skill_level=skill_level,
        image_brief=image_brief,
        video_chapters=video_chapters,
        personal_observations=personal_observations,
        lesson_plan=lesson_plan_rel,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2))

    warnings = [k for k in errors if k not in CRITICAL_STEPS]
    return {
        "pages":    pages,
        "video":    video_path,
        "pdf":      pdf_path,
        "manifest": str(manifest_path),
        "warnings": warnings,
        "errors":   errors,
        "timings":  timings,
    }


def _palette_with_recipes(palette: list[dict], medium: str) -> list[dict]:
    """Kubelka-Munk tube recipes for paint mediums; graceful no-op otherwise."""
    try:
        from ..teaching.mixing import recipes_for_palette
        return recipes_for_palette(palette, medium)
    except Exception:
        log.warning("palette mixing recipes failed", exc_info=True)
        return palette


def _is_hierarchical_asset(path: str) -> bool:
    p = Path(path)
    return p.parent.name.startswith("level_") or "level_" in p.stem


# Which lesson_plan asset type each video phase wants as its overlay image —
# phase 2 needs an outline-style image (its dark pixels become the line mask),
# phases 3/4/6 need a value or colour mass image.
_STAGE_IMAGE_PREFERENCE = {
    2: "outlines",
    3: "values",
    4: "colours",
    6: "colours",
}


def _resolve_stage_images(lesson_plan_abs: list[dict]) -> dict:
    """
    Pick one real, already-generated image per relevant stage order from the
    lesson_plan's resolved assets, for the video to show instead of its
    generic classic-pipeline fallback. Missing/unopenable assets are simply
    left out — generate() falls back to its default image in that case.
    """
    from PIL import Image

    images: dict[int, "Image.Image"] = {}
    for step in lesson_plan_abs:
        order = step.get("order")
        if order not in _STAGE_IMAGE_PREFERENCE:
            continue
        assets = step.get("assets", {})
        if not assets:
            continue
        preferred = _STAGE_IMAGE_PREFERENCE[order]
        chosen = next((p for k, p in assets.items() if preferred in k), next(iter(assets.values())))
        if chosen and Path(chosen).exists():
            try:
                images[order] = Image.open(chosen).convert("RGB")
            except Exception:
                log.warning("_resolve_stage_images: could not open %r for stage order %d", chosen, order)
    return images


def _normalize_detail_levels(detail_levels: dict) -> dict:
    """A1: convert absolute asset paths in detail_levels to outputs-relative paths."""
    result = {}
    for k, lvl in detail_levels.items():
        raw_edge_maps = lvl.get("edge_maps") or {}
        result[k] = {
            "level":      lvl.get("level"),
            "label":      lvl.get("label"),
            "outlines":   rel_to_outputs(lvl.get("outlines")),
            "regions":    rel_to_outputs(lvl.get("regions")),
            "values":     rel_to_outputs(lvl.get("values")),
            "colours":    rel_to_outputs(lvl.get("colours")),
            "region_ids": lvl.get("region_ids", []),
            # Level-aware outline sublayers — distinct from the global,
            # non-level-filtered "edge_maps" at the top of the manifest.
            "edge_maps":  {name: rel_to_outputs(p) for name, p in raw_edge_maps.items() if p},
        }
    return result


def _relativize_lesson_plan(lesson_plan: list[dict]) -> list[dict]:
    """
    Derive the outputs-relative form of an absolute-path lesson plan.

    Only the asset path strings differ between the two forms — step order,
    name, level, resolved asset *keys*, and the image notes/micro-steps are
    identical. Deriving instead of rebuilding guarantees they cannot diverge.
    """
    rel_plan: list[dict] = []
    for step in lesson_plan:
        rel_step = dict(step)
        rel_step["assets"] = {
            k: rel_to_outputs(v) for k, v in step.get("assets", {}).items()
        }
        rel_plan.append(rel_step)
    return rel_plan


def _build_manifest(
    job_id: str,
    img,
    medium: str,
    palette_size: int,
    initial_view_level: int,
    value_zones: int,
    pages: list[str],
    video_path: str | None,
    pdf_path: str | None,
    hier: dict,
    timings: dict,
    errors: dict,
    ref_suffix: str = ".jpg",
    region_complexity: int = 3,
    texture_detail: bool = True,
    background_detail: bool = False,
    skill_level: str = "intermediate",
    image_brief: dict | None = None,
    video_chapters: list[dict] | None = None,
    personal_observations: str | None = None,
    lesson_plan: list[dict] | None = None,
) -> dict:
    w, h = img.size

    classic_pages = [rel_to_outputs(p) for p in pages if not _is_hierarchical_asset(p) and p]

    # A4: normalise individual edge-map paths
    raw_edge_maps = hier.get("edge_maps", {})
    edge_maps_rel = {name: rel_to_outputs(p) for name, p in raw_edge_maps.items() if p}

    # Global outline composites (non-level-filtered) — used by lesson_plan resolution
    raw_outline_composites = hier.get("outline_composites", {})
    outline_composites_rel = {name: rel_to_outputs(p) for name, p in raw_outline_composites.items() if p}

    value_zones_map = rel_to_outputs(hier.get("value_zones_path"))

    manifest = {
        "job_id": job_id,
        "input": {
            "medium":              medium,
            "palette_size":        palette_size,
            "initial_view_level":  initial_view_level,
            "value_zones":         value_zones,
            "region_complexity":   region_complexity,
            "texture_detail":      texture_detail,
            "background_detail":   background_detail,
            "skill_level":         skill_level,
        },
        "image": {"width": w, "height": h},
        "reference": f"{job_id}/reference{ref_suffix}",
        "pages": classic_pages,
        "detail_levels": _normalize_detail_levels(hier.get("detail_levels", {})),  # A1
        "edge_maps":      edge_maps_rel,    # A4: individual sublayer maps
        "outline_composites": outline_composites_rel,
        "value_zones_map": value_zones_map,
        "palette":        _palette_with_recipes(hier.get("palette", []), medium),
        "colour_families":hier.get("colour_families", []),
        "value_zones":    hier.get("value_zone_list", []),
        "video":  rel_to_outputs(video_path),
        "video_chapters": video_chapters or [],
        "pdf":    rel_to_outputs(pdf_path),
        "personal_observations": personal_observations,
        "timings": timings,
        "errors": {k: v[:300] for k, v in errors.items()},  # truncate for JSON
    }

    from ..teaching.mediums import get_medium as _get_medium_for_manifest
    medium_cfg = _get_medium_for_manifest(medium)
    manifest["teaching_stages"]       = medium_cfg.get("stages", [])
    manifest["teaching_instructions"] = medium_cfg.get("instructions", {})

    # The lesson plan is built once by the caller (absolute paths) and passed
    # in already relativised, so the manifest and the video/PDF copies cannot
    # diverge. Fall back to building it here only if a caller omits it.
    if lesson_plan is None:
        from ..teaching.lesson import build_lesson_plan
        lesson_plan = build_lesson_plan(
            medium_cfg=medium_cfg,
            medium=medium,
            detail_levels=manifest["detail_levels"],
            outline_composites=outline_composites_rel,
            value_zones_map=value_zones_map,
            classic_pages=classic_pages,
            skill_level=skill_level,
        )
        if image_brief:
            from ..teaching.planner import attach_image_notes as _attach_notes
            lesson_plan = _attach_notes(lesson_plan, image_brief, medium)
    manifest["lesson_plan"] = lesson_plan
    manifest["image_brief"] = image_brief or {}

    return manifest
