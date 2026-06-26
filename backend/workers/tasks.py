from __future__ import annotations
import os
from pathlib import Path
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("art_book", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_serializer  = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content   = ["json"]


@celery_app.task(bind=True, name="art_book.run_pipeline")
def run_pipeline(self, img_path: str, job_id: str,
                 medium: str = "oil",
                 n_colors: int = 32) -> dict:
    """
    Full painting instructor pipeline.

    Steps:
      1. line_art          — 3-layer composite (silhouette + interior + XDoG bg)
      2. notan             — 3-zone LAB value study
      3. color_temperature — LAB b-channel warm/cool map
      4. color_palette     — K-means++ dominant colour chart
      5. light_direction   — Sobel histogram + Gurney 5-zone overlay
      6. color_by_number   — bilateral+BiSeNet+RAG paint-by-numbers
      7. dot_to_dot        — DexiNed+skeleton arc-length numbered dots
      8. video             — progressive tutorial animation
      9. pdf               — A4 book
    """
    from PIL import Image
    from fpdf2 import FPDF

    from ..preprocessing.processor import load_image
    from ..pipeline.line_art.processor import process as line_art
    from ..pipeline.artist_breakdown.processor import (
        notan, color_palette, color_temperature, light_direction
    )
    from ..pipeline.color_by_number.processor import process as color_by_number
    from ..pipeline.dot_to_dot.processor import process as dot_to_dot
    from ..pipeline.video.processor import generate as make_video

    out_dir = Path(f"outputs/{job_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    def step(name: str):
        self.update_state(state="STARTED", meta={"step": name})

    def save(name: str, result: Image.Image) -> str:
        p = str(out_dir / f"{name}.png")
        result.save(p)
        return p

    step("loading")
    img = load_image(img_path)
    pages: list[str] = []

    step("line_art")
    la_result  = line_art(img)
    la_path    = save("line_art", la_result)
    pages.append(la_path)

    step("notan")
    notan_result = notan(img, zones=3)
    pages.append(save("notan", notan_result))

    step("color_temperature")
    pages.append(save("color_temperature", color_temperature(img)))

    step("color_palette")
    pages.append(save("color_palette", color_palette(img, n_colors=n_colors)))

    step("light_direction")
    pages.append(save("light_direction", light_direction(img)))

    step("color_by_number")
    cbn_result = color_by_number(img, n_colors=n_colors)
    pages.append(save("color_by_number", cbn_result))

    step("dot_to_dot")
    pages.append(save("dot_to_dot", dot_to_dot(img, n_dots=500)))

    step("video")
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

    step("pdf")
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    for p in pages:
        pdf.add_page()
        pdf.image(p, x=10, y=10, w=190)
    pdf_path = str(out_dir / "tutorial_book.pdf")
    pdf.output(pdf_path)

    return {"pages": pages, "video": video_path, "pdf": pdf_path}
