from __future__ import annotations
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..workers.tasks import run_pipeline, celery_app

app = FastAPI(title="Painting Instructor API", version="0.2.0")

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file serving for generated outputs ─────────────────────────────────
OUTPUTS_DIR = Path("outputs")
OUTPUTS_DIR.mkdir(exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

UPLOAD_DIR = OUTPUTS_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


# ── POST /jobs/ ───────────────────────────────────────────────────────────────
@app.post("/jobs/")
async def create_job(
    file:     UploadFile,
    medium:   str = Form("oil"),
    n_colors: int = Form(32),
):
    """Upload a photo and start the painting instructor pipeline."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}")

    job_id   = str(uuid.uuid4())
    suffix   = Path(file.filename or "img.jpg").suffix or ".jpg"
    img_path = UPLOAD_DIR / f"{job_id}{suffix}"
    img_path.write_bytes(await file.read())

    # Use job_id as the Celery task ID so GET /jobs/{job_id} can find it
    run_pipeline.apply_async(
        args=[str(img_path), job_id],
        kwargs={"medium": medium, "n_colors": n_colors},
        task_id=job_id,
    )

    return {"job_id": job_id}


# ── GET /jobs/{job_id} ────────────────────────────────────────────────────────
@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """Poll job status. Returns Celery state + current step + result when done."""
    from celery.result import AsyncResult

    r = AsyncResult(job_id, app=celery_app)

    if r.state == "PENDING":
        return {"status": "PENDING"}

    if r.state == "STARTED":
        meta = r.info or {}
        return {"status": "STARTED", "step": meta.get("step", "")}

    if r.state == "SUCCESS":
        result = r.result or {}
        return {
            "status": "SUCCESS",
            "result": {
                "pages": result.get("pages", []),
                "video": result.get("video"),
                "pdf":   result.get("pdf"),
            },
            "errors": result.get("errors", {}),
        }

    if r.state == "FAILURE":
        return {"status": "FAILURE", "error": str(r.result)}

    return {"status": r.state}


# ── GET /jobs/{job_id}/pdf ────────────────────────────────────────────────────
@app.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: str):
    pdf_path = OUTPUTS_DIR / job_id / "tutorial_book.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF not ready yet")
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename="tutorial_book.pdf")
