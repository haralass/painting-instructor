from __future__ import annotations
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..workers.tasks import run_pipeline

app = FastAPI(title="Personal Art Book API", version="0.1.0")

UPLOAD_DIR = Path("outputs/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "error"]
    pages: list[str] = []
    error: str | None = None


@app.post("/jobs/", response_model=JobStatus)
async def create_job(file: UploadFile) -> JobStatus:
    """Upload a photo and start the art-book pipeline."""
    if file.content_type not in ("image/jpeg", "image/png", "image/webp", "image/heic"):
        raise HTTPException(400, "Unsupported image type")

    job_id  = str(uuid.uuid4())
    img_path = UPLOAD_DIR / f"{job_id}{Path(file.filename or 'img.jpg').suffix}"
    img_path.write_bytes(await file.read())

    task = run_pipeline.delay(str(img_path), job_id)

    return JobStatus(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> JobStatus:
    """Poll job status and retrieve output page paths when done."""
    from celery.result import AsyncResult
    from ..workers.tasks import celery_app

    result = AsyncResult(job_id, app=celery_app)

    if result.state == "PENDING":
        return JobStatus(job_id=job_id, status="queued")
    if result.state == "STARTED":
        return JobStatus(job_id=job_id, status="processing")
    if result.state == "SUCCESS":
        return JobStatus(job_id=job_id, status="done", pages=result.result or [])
    if result.state == "FAILURE":
        return JobStatus(job_id=job_id, status="error", error=str(result.result))

    return JobStatus(job_id=job_id, status="processing")


@app.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: str):
    """Download the assembled PDF for a completed job."""
    pdf_path = Path(f"outputs/{job_id}/art_book.pdf")
    if not pdf_path.exists():
        raise HTTPException(404, "PDF not ready")
    return FileResponse(pdf_path, media_type="application/pdf", filename="art_book.pdf")
