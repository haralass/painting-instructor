from __future__ import annotations
import json
import logging
import os
import time
import traceback
from pathlib import Path

from celery import Celery

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
    "line_art":         20,
    "notan":            30,
    "value_analysis":   35,
    "color_temperature":40,
    "color_palette":    50,
    "light_direction":  55,
    "color_by_number":  65,
    "dot_to_dot":       75,
    "hierarchical":     80,
    "video":            85,
    "pdf":              92,
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
    detail_level: int = 3,
    value_zones: int = 5,
    texture_detail: bool = True,
    background_detail: bool = False,
    # backward-compat alias
    n_colors: int = 0,
) -> dict:
    """
    Full painting instructor pipeline with per-step progress and error resilience.

    Steps:
      1. loading          — open & resize image
      2. line_art         — 3-layer composite + fg_mask
      3. notan            — adaptive value study
      4. color_temperature— LAB b* warm/cool map (fixed channel)
      5. color_palette    — K-means++ dominant colour chart
      6. light_direction  — Sobel histogram + 5-zone overlay
      7. color_by_number  — bilateral+RAG paint-by-numbers
      8. dot_to_dot       — skeleton arc-length numbered dots (reuses line art)
      9. hierarchical     — multi-scale region hierarchy + edge classification
     10. video            — progressive tutorial animation
     11. pdf              — A4 book of all pages that succeeded
     12. manifest         — manifest.json describing all outputs
    """
    from PIL import Image
    from fpdf import FPDF

    from ..preprocessing.processor import load_image
    from ..pipeline.line_art.processor import process_with_mask as line_art_with_mask
    from ..pipeline.artist_breakdown.processor import (
        notan, color_palette, color_temperature, light_direction
    )
    from ..pipeline.color_by_number.processor import process as color_by_number
    from ..pipeline.dot_to_dot.processor import process as dot_to_dot
    from ..pipeline.video.processor import generate as make_video

    # Resolve backward-compat alias
    if n_colors and not palette_size:
        palette_size = n_colors
    if not palette_size:
        palette_size = 12

    out_dir = Path(f"outputs/{job_id}")
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

    def run(name: str, fn):
        """Run one pipeline step; log errors without aborting the whole job."""
        progress(name)
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

    # ── Step 1: Load ──────────────────────────────────────────────────────────
    progress("loading")
    img = load_image(img_path)
    pages: list[str] = []

    # ── Step 2: Line art ──────────────────────────────────────────────────────
    la_result, fg_mask = None, None
    try:
        progress("line_art")
        t0 = time.perf_counter()
        la_result, fg_mask = line_art_with_mask(img)
        timings["line_art"] = round(time.perf_counter() - t0, 2)
        pages.append(save("line_art", la_result))
    except Exception:
        tb = traceback.format_exc()
        errors["line_art"] = tb
        log.warning("Pipeline step 'line_art' failed:\n%s", tb)

    # ── Step 3: Notan ─────────────────────────────────────────────────────────
    notan_result = run("notan", lambda: notan(img, zones=min(value_zones, 5)))
    if notan_result:
        pages.append(save("notan", notan_result))

    # ── Step 4: Colour temperature ────────────────────────────────────────────
    r = run("color_temperature", lambda: color_temperature(img))
    if r:
        pages.append(save("color_temperature", r))

    # ── Step 5: Colour palette ────────────────────────────────────────────────
    r = run("color_palette", lambda: color_palette(img, n_colors=palette_size))
    if r:
        pages.append(save("color_palette", r))

    # ── Step 6: Light direction ───────────────────────────────────────────────
    r = run("light_direction", lambda: light_direction(img))
    if r:
        pages.append(save("light_direction", r))

    # ── Step 7: Color by number ───────────────────────────────────────────────
    cbn_result = run("color_by_number", lambda: color_by_number(img, n_colors=palette_size))
    if cbn_result:
        pages.append(save("color_by_number", cbn_result))

    # ── Step 8: Dot to dot (reuses line art — no second edge detection) ───────
    r = run("dot_to_dot", lambda: dot_to_dot(
        img, n_dots=500,
        line_art_img=la_result,
        fg_mask=fg_mask,
    ))
    if r:
        pages.append(save("dot_to_dot", r))

    # ── Step 9: Hierarchical analysis (new architecture) ──────────────────────
    try:
        from ..analysis.pipeline import run_hierarchical_analysis
        progress("hierarchical")
        t0 = time.perf_counter()
        hier = run_hierarchical_analysis(
            img=img,
            out_dir=out_dir,
            palette_size=palette_size,
            detail_level=detail_level,
            value_zones=value_zones,
            medium=medium,
            fg_mask=fg_mask,
            texture_detail=texture_detail,
            background_detail=background_detail,
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
        log.warning("Hierarchical analysis failed:\n%s", tb)
        hier = {}

    # ── Step 10: Video ────────────────────────────────────────────────────────
    video_path = None
    if la_result and notan_result and cbn_result:
        progress("video")
        try:
            t0 = time.perf_counter()
            video_path = str(out_dir / "tutorial.mp4")
            make_video(
                reference=img,
                line_art=la_result,
                notan=notan_result,
                color_blocking=cbn_result,
                output_path=video_path,
                fps=24,
                out_w=1080,
            )
            timings["video"] = round(time.perf_counter() - t0, 2)
        except Exception:
            tb = traceback.format_exc()
            errors["video"] = tb
            log.warning("Video generation failed:\n%s", tb)
            video_path = None

    # ── Step 11: PDF ──────────────────────────────────────────────────────────
    progress("pdf")
    pdf_path = None
    # Filter pages to only classic analysis outputs (not hierarchical detail levels)
    classic_pages = [p for p in pages if not _is_hierarchical_asset(p)]
    if classic_pages:
        try:
            t0 = time.perf_counter()
            pdf = FPDF(orientation="P", unit="mm", format="A4")
            for p in classic_pages:
                pdf.add_page()
                pdf.image(p, x=10, y=10, w=190)
            pdf_path = str(out_dir / "tutorial_book.pdf")
            pdf.output(pdf_path)
            timings["pdf"] = round(time.perf_counter() - t0, 2)
        except Exception:
            tb = traceback.format_exc()
            errors["pdf"] = tb
            log.warning("PDF assembly failed:\n%s", tb)

    # ── Step 12: Manifest ─────────────────────────────────────────────────────
    progress("manifest")
    manifest = _build_manifest(
        job_id=job_id,
        img=img,
        medium=medium,
        palette_size=palette_size,
        detail_level=detail_level,
        value_zones=value_zones,
        pages=pages,
        video_path=video_path,
        pdf_path=pdf_path,
        hier=hier,
        timings=timings,
        errors=errors,
    )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return {
        "pages":  pages,
        "video":  video_path,
        "pdf":    pdf_path,
        "manifest": str(manifest_path),
        "errors": errors,
        "timings": timings,
    }


def _is_hierarchical_asset(path: str) -> bool:
    p = Path(path)
    return p.parent.name.startswith("level_") or "level_" in p.stem


def _build_manifest(
    job_id: str,
    img,
    medium: str,
    palette_size: int,
    detail_level: int,
    value_zones: int,
    pages: list[str],
    video_path: str | None,
    pdf_path: str | None,
    hier: dict,
    timings: dict,
    errors: dict,
) -> dict:
    w, h = img.size
    base = f"outputs/{job_id}"

    def rel(p: str | None) -> str | None:
        if not p:
            return None
        return str(Path(p).relative_to(Path("outputs"))) if "outputs" in p else p

    classic_pages = [rel(p) for p in pages if not _is_hierarchical_asset(p) and p]

    manifest = {
        "job_id": job_id,
        "input": {
            "medium":       medium,
            "palette_size": palette_size,
            "detail_level": detail_level,
            "value_zones":  value_zones,
        },
        "image": {"width": w, "height": h},
        "pages": classic_pages,
        "detail_levels": hier.get("detail_levels", {}),
        "palette":        hier.get("palette", []),
        "colour_families":hier.get("colour_families", []),
        "value_zones":    hier.get("value_zone_list", []),
        "video":  rel(video_path),
        "pdf":    rel(pdf_path),
        "timings": timings,
        "errors": {k: v[:300] for k, v in errors.items()},  # truncate for JSON
    }

    from ..teaching.mediums import get_medium as _get_medium_for_manifest
    medium_cfg = _get_medium_for_manifest(medium)
    manifest["teaching_stages"]       = medium_cfg.get("stages", [])
    manifest["teaching_instructions"] = medium_cfg.get("instructions", {})

    return manifest
