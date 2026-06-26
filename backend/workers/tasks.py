from __future__ import annotations
import os
import traceback
from pathlib import Path
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("art_book", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_serializer   = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content    = ["json"]


@celery_app.task(bind=True, name="art_book.run_pipeline")
def run_pipeline(self, img_path: str, job_id: str,
                 medium: str = "oil",
                 n_colors: int = 32) -> dict:
    """
    Full painting instructor pipeline with per-step error resilience.

    Steps:
      1. line_art          — 3-layer composite; also produces fg_mask
      2. notan             — 3-zone LAB value study
      3. color_temperature — LAB b-channel warm/cool map
      4. color_palette     — K-means++ dominant colour chart
      5. light_direction   — Sobel histogram + Gurney 5-zone overlay
      6. color_by_number   — bilateral+BiSeNet+RAG paint-by-numbers
      7. dot_to_dot        — skeleton arc-length numbered dots (reuses line art)
      8. video             — progressive tutorial animation
      9. pdf               — A4 book of all pages that succeeded
    """
    from PIL import Image
    from fpdf2 import FPDF

    from ..preprocessing.processor import load_image
    from ..pipeline.line_art.processor import process_with_mask as line_art_with_mask
    from ..pipeline.artist_breakdown.processor import (
        notan, color_palette, color_temperature, light_direction
    )
    from ..pipeline.color_by_number.processor import process as color_by_number
    from ..pipeline.dot_to_dot.processor import process as dot_to_dot
    from ..pipeline.video.processor import generate as make_video

    out_dir = Path(f"outputs/{job_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    errors: dict[str, str] = {}

    def step(name: str):
        self.update_state(state="STARTED", meta={"step": name, "errors": errors})

    def save(name: str, result: Image.Image) -> str:
        p = str(out_dir / f"{name}.png")
        result.save(p)
        return p

    def run(name: str, fn):
        """Run one pipeline step; log errors without aborting the whole job."""
        step(name)
        try:
            return fn()
        except Exception:
            errors[name] = traceback.format_exc()
            return None

    step("loading")
    img = load_image(img_path)
    pages: list[str] = []

    # Line art — also captures fg_mask for dot_to_dot
    step("line_art")
    la_result, fg_mask = None, None
    try:
        la_result, fg_mask = line_art_with_mask(img)
        pages.append(save("line_art", la_result))
    except Exception:
        errors["line_art"] = traceback.format_exc()

    notan_result = run("notan",             lambda: notan(img, zones=3))
    if notan_result: pages.append(save("notan", notan_result))

    r = run("color_temperature", lambda: color_temperature(img))
    if r: pages.append(save("color_temperature", r))

    r = run("color_palette",     lambda: color_palette(img, n_colors=n_colors))
    if r: pages.append(save("color_palette", r))

    r = run("light_direction",   lambda: light_direction(img))
    if r: pages.append(save("light_direction", r))

    cbn_result = run("color_by_number", lambda: color_by_number(img, n_colors=n_colors))
    if cbn_result: pages.append(save("color_by_number", cbn_result))

    r = run("dot_to_dot", lambda: dot_to_dot(
        img, n_dots=500,
        line_art_img=la_result,
        fg_mask=fg_mask,
    ))
    if r: pages.append(save("dot_to_dot", r))

    # Video — needs at least line_art + notan + color_by_number
    video_path = None
    if la_result and notan_result and cbn_result:
        step("video")
        try:
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
        except Exception:
            errors["video"] = traceback.format_exc()
            video_path = None

    # PDF — only pages that succeeded
    step("pdf")
    pdf_path = None
    if pages:
        try:
            pdf = FPDF(orientation="P", unit="mm", format="A4")
            for p in pages:
                pdf.add_page()
                pdf.image(p, x=10, y=10, w=190)
            pdf_path = str(out_dir / "tutorial_book.pdf")
            pdf.output(pdf_path)
        except Exception:
            errors["pdf"] = traceback.format_exc()

    return {
        "pages":  pages,
        "video":  video_path,
        "pdf":    pdf_path,
        "errors": errors,
    }
