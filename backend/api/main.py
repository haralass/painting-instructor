from __future__ import annotations
import json
import os
import uuid
from pathlib import Path

from ..utils.paths import outputs_root

from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..workers.tasks import run_pipeline, celery_app
from ..schemas.jobs import (
    CreateJobResponse,
    JobResponse,
    JobResult,
    validate_medium,
    validate_palette_size,
    validate_initial_view_level,
    validate_value_zones,
    validate_skill_level,
)
from ..teaching.mediums import MEDIUMS, get_medium as _get_medium_cfg
from ..teaching.mixing import list_brands

from ..capabilities import registry_payload, validate_registry

app = FastAPI(title="Painting Instructor API", version="0.4.0")

# The registry is code — fail loudly at import time if its invariants break.
_registry_problems = validate_registry()
if _registry_problems:
    raise RuntimeError(f"Capability registry invalid: {_registry_problems}")

# ── CORS ─────────────────────────────────────────────────────────────────────
_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file serving ───────────────────────────────────────────────────────
OUTPUTS_DIR = outputs_root()
OUTPUTS_DIR.mkdir(exist_ok=True)


class _CorpStaticFiles(StaticFiles):
    """Serve /outputs with Cross-Origin-Resource-Policy: cross-origin.

    The reference image and analysis assets are served from the API origin
    (:8000) but consumed on the frontend origin (:3000), including inside the
    OpenSeadragon WebGL viewer and canvas readbacks (label-map decode, mask
    overlays). Without CORP the browser blocks the cross-origin resource in
    those contexts (net::ERR_FAILED) — and a plain <img> pre-caching the same
    URL without CORS poisons the cache for the viewer's later CORS request.
    Setting CORP (alongside the app's CORS middleware) makes every asset
    usable in every context, cache mode included."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
        response.headers["Vary"] = "Origin"
        return response


app.mount("/outputs", _CorpStaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

UPLOAD_DIR = OUTPUTS_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

# Map Celery states → canonical lowercase status
_CELERY_TO_STATUS = {
    "PENDING":  "queued",
    "RECEIVED": "queued",
    "STARTED":  "processing",
    "PROGRESS": "processing",
    "SUCCESS":  "completed",           # may be refined to completed_with_warnings below
    "FAILURE":  "failed",
    "RETRY":    "processing",
    "REVOKED":  "failed",
}


# ── POST /jobs/ ───────────────────────────────────────────────────────────────
@app.post("/jobs/", response_model=CreateJobResponse)
async def create_job(
    file:          UploadFile,
    medium:        str = Form("oil"),
    # Accept both palette_size (canonical) and n_colors (backward-compat)
    palette_size:  int = Form(0),
    n_colors:      int = Form(0),
    initial_view_level: int = Form(3),
    value_zones:   int = Form(5),
    texture_detail:     bool = Form(True),
    background_detail:  bool = Form(False),
    region_complexity:  int  = Form(3),   # A6: 1–5 hierarchy resolution
    skill_level:        str  = Form("intermediate"),
    user_id:            str | None = Form(None),
    brand_id:           str | None = Form(None),
):
    """Upload a reference photo and start the painting instructor pipeline."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}")

    # Resolve palette_size: canonical wins; fall back to n_colors; default 12
    resolved_palette = palette_size or n_colors or 12

    if not (1 <= region_complexity <= 5):
        raise HTTPException(422, f"region_complexity must be 1–5, got {region_complexity}")

    try:
        medium        = validate_medium(medium)
        resolved_palette = validate_palette_size(resolved_palette)
        initial_view_level = validate_initial_view_level(initial_view_level)
        value_zones   = validate_value_zones(value_zones)
        skill_level   = validate_skill_level(skill_level)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    job_id = str(uuid.uuid4())
    suffix = Path(file.filename or "img.jpg").suffix or ".jpg"
    img_path = UPLOAD_DIR / f"{job_id}{suffix}"
    img_path.write_bytes(await file.read())

    # Every upload is a resumable project (brief §18). The worker copies the
    # untouched original to outputs/{job}/reference{suffix}; we record that
    # canonical location now. A store failure must never block the job.
    try:
        from ..projects import store as project_store
        project_store.create_project(
            job_id=job_id,
            reference_path=f"{job_id}/reference{suffix}",
            medium=medium,
            skill_level=skill_level,
            value_zones=value_zones,
            settings={
                "palette_size":       resolved_palette,
                "initial_view_level": initial_view_level,
                "region_complexity":  region_complexity,
                "texture_detail":     texture_detail,
                "background_detail":  background_detail,
                "brand_id":           brand_id,
                "user_id":            user_id,
            },
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("project row creation failed", exc_info=True)

    run_pipeline.apply_async(
        args=[str(img_path), job_id],
        kwargs={
            "medium":              medium,
            "palette_size":        resolved_palette,
            "initial_view_level":  initial_view_level,
            "value_zones":         value_zones,
            "texture_detail":      texture_detail,
            "background_detail":   background_detail,
            "region_complexity":   region_complexity,
            "skill_level":         skill_level,
            "user_id":             user_id,
            "brand_id":            brand_id,
        },
        task_id=job_id,
    )

    return CreateJobResponse(job_id=job_id)


# ── GET /jobs/{job_id} ────────────────────────────────────────────────────────
def _manifest_fallback(job_id: str) -> JobResponse | None:
    """Resume path (brief §18): the manifest on disk is the durable record of
    a finished job. Celery results expire from Redis (default 24 h) and Redis
    may have restarted — a saved project must still open, so a final manifest
    answers 'completed' without consulting the broker at all."""
    m_path = outputs_root() / job_id / "manifest.json"
    if not m_path.exists():
        return None
    try:
        m = json.loads(m_path.read_text())
    except Exception:
        return None
    if m.get("status") == "analysis_ready":
        # Prelim manifest: analysis done, extras possibly still rendering —
        # only used when the broker no longer knows the job.
        return JobResponse(
            job_id=job_id, status="processing", progress=80, step="analysis_ready",
            message="Analysis ready — extras may still be rendering",
            analysis_ready=True,
        )
    return JobResponse(
        job_id=job_id, status="completed", progress=100, step="completed",
        message="Tutorial ready",
        result=JobResult(
            manifest=f"/outputs/{job_id}/manifest.json",
            pages=[f"/outputs/{p}" for p in m.get("pages", [])],
            video=f"/outputs/{m['video']}" if m.get("video") else None,
            pdf=f"/outputs/{m['pdf']}" if m.get("pdf") else None,
        ),
    )


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str) -> JobResponse:
    """Poll job status. Returns canonical status + progress + result when done."""
    from celery.result import AsyncResult

    # Durable fast path: a FINAL manifest on disk means completed, regardless
    # of what (or whether) the result backend remembers.
    disk = _manifest_fallback(job_id)
    if disk is not None and disk.status == "completed":
        return disk

    try:
        r = AsyncResult(job_id, app=celery_app)
        state = r.state
    except Exception:
        # Result backend unreachable — fall back to whatever disk knows.
        return disk or JobResponse(
            job_id=job_id, status="queued", progress=0, step="queued",
            message="Waiting to start",
        )

    if state in ("PENDING", "RECEIVED"):
        # An expired/forgotten job that reached analysis_ready still resumes.
        if disk is not None:
            return disk
        return JobResponse(job_id=job_id, status="queued", progress=0, step="queued", message="Waiting to start")

    if state in ("STARTED", "PROGRESS"):
        meta        = r.info or {}
        progress_n  = int(meta.get("progress", 5))
        step        = str(meta.get("step", ""))
        message     = str(meta.get("message", "Processing…"))
        analysis_rdy = progress_n >= 80 or step in ("analysis_ready", "rendering_extras", "video", "pdf", "manifest")
        return JobResponse(
            job_id=job_id,
            status="processing",
            progress=progress_n,
            step=step,
            message=message,
            analysis_ready=analysis_rdy,
        )

    if state == "SUCCESS":
        result = r.result or {}
        pages  = result.get("pages", [])
        # Convert absolute paths to /outputs/... URLs
        pages_urls = [_path_to_url(p, job_id) for p in pages if p]
        manifest_url = f"/outputs/{job_id}/manifest.json"
        warnings = result.get("warnings", [])
        status_str = "completed_with_warnings" if warnings else "completed"
        message = f"Tutorial ready (warnings: {', '.join(warnings)})" if warnings else "Tutorial ready"
        return JobResponse(
            job_id=job_id,
            status=status_str,
            progress=100,
            step="completed",
            message=message,
            result=JobResult(
                manifest=manifest_url,
                pages=pages_urls,
                video=_path_to_url(result.get("video"), job_id),
                pdf=_path_to_url(result.get("pdf"), job_id),
            ),
        )

    if state == "FAILURE":
        return JobResponse(
            job_id=job_id, status="failed", progress=0, step="failed",
            message="Pipeline failed", error=str(r.result),
        )

    return JobResponse(job_id=job_id, status="processing", progress=5, step=state.lower(), message="Processing…")


# ── POST /jobs/{job_id}/critique ──────────────────────────────────────────────
@app.post("/jobs/{job_id}/critique")
async def critique_job(job_id: str, file: UploadFile, user_id: str | None = Form(None)):
    """
    Upload a photo of the student's own painting attempt and get localised,
    actionable feedback against this job's reference image. Runs synchronously
    — it is plain CV (value bands, LAB temperature/chroma, edge density), no
    ML models. Each upload gets its own numbered attempt directory, so the
    student can track successive attempts at the same lesson.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported image type: {file.content_type}")

    job_out = outputs_root() / job_id
    reference = next(iter(job_out.glob("reference.*")), None)
    if reference is None:
        raise HTTPException(404, "Reference image not found — has the job finished analysing?")

    critique_root = job_out / "critique"
    attempt_no = 1 + sum(1 for d in critique_root.glob("attempt_*") if d.is_dir()) if critique_root.exists() else 1
    attempt_dir = critique_root / f"attempt_{attempt_no}"
    attempt_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "attempt.jpg").suffix or ".jpg"
    attempt_path = attempt_dir / f"attempt{suffix}"
    attempt_path.write_bytes(await file.read())

    # Medium + value zones from the job's manifest, if it exists yet
    medium, n_bands = "oil", 5
    manifest_path = job_out / "manifest.json"
    if manifest_path.exists():
        try:
            m_input = json.loads(manifest_path.read_text()).get("input", {})
            medium = m_input.get("medium", medium)
            n_bands = int(m_input.get("value_zones", n_bands))
        except Exception:
            pass

    from ..critique.engine import critique_attempt, save_critique

    # Drawing analysis (subject bounds / silhouette) for the structural
    # comparison, if this job produced one. Missing/unreadable is fine.
    drawing = None
    drawing_path = job_out / "drawing.json"
    if drawing_path.exists():
        try:
            drawing = json.loads(drawing_path.read_text())
        except Exception:
            drawing = None

    try:
        result = critique_attempt(
            reference_path=reference,
            attempt_path=attempt_path,
            out_dir=attempt_dir,
            n_value_bands=n_bands,
            medium=medium,
            drawing=drawing,
        )
    except Exception as exc:
        raise HTTPException(500, f"Critique failed: {exc}")

    result["attempt"] = attempt_no
    save_critique(result, attempt_dir)

    # Adaptive painter profile — deterministic, no LLM. Only engages when a
    # user_id is supplied; behaviour is otherwise unchanged. Never let a
    # profiling failure break the critique response.
    if user_id:
        try:
            from ..critique.profile import record_critique, recompute_profile
            record_critique(user_id, result)
            result["profile"] = recompute_profile(user_id)
        except Exception:
            pass

    # Record the attempt on the project so progress survives the session
    # (save/continue, brief §18). Never let this break the critique response.
    try:
        from ..projects import store as project_store
        project = project_store.get_project_by_job(job_id)
        if project:
            project_store.add_attempt(
                project["id"],
                path=str(attempt_path.relative_to(outputs_root())),
                critique={"priority": result.get("priority"),
                          "metric_scores": result.get("metric_scores")},
            )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("attempt recording failed", exc_info=True)

    # Convert filesystem paths to /outputs URLs for the frontend
    result["assets"] = {k: _path_to_url(v, job_id) for k, v in result["assets"].items()}
    result["attempt_image"] = _path_to_url(str(attempt_path), job_id)
    return result


# ── GET /jobs/{job_id}/pdf ────────────────────────────────────────────────────
@app.get("/jobs/{job_id}/pdf")
def download_pdf(job_id: str):
    # Resolve outputs_root() fresh (like create_job / critique_job) so an
    # env override applied after import is respected, instead of the stale
    # module-level OUTPUTS_DIR captured at import time.
    pdf_path = outputs_root() / job_id / "tutorial_book.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, "PDF not ready yet")
    return FileResponse(pdf_path, media_type="application/pdf", filename="tutorial_book.pdf")


# ── Projects: save & continue (brief §18 — Phase-1 foundation) ───────────────
from pydantic import BaseModel as _BaseModel


class _ProjectPatch(_BaseModel):
    title: str | None = None
    current_capability: str | None = None


class _StepStatus(_BaseModel):
    step_id: str
    status: str  # pending|in_progress|completed|skipped
    data: dict = {}


class _CheckpointUpsert(_BaseModel):
    type: str    # schemas/lesson.py CheckpointType
    status: str = "open"
    data: dict = {}
    checkpoint_id: str | None = None


@app.get("/projects")
def list_projects(limit: int = 20):
    from ..projects import store as project_store
    return project_store.list_projects(limit=min(max(limit, 1), 100))


@app.get("/projects/by-job/{job_id}")
def get_project_by_job(job_id: str):
    """Resolve the project for a job (the workspace knows the job id, not the
    project id) so the lesson player can read/write progress + checkpoints."""
    from ..projects import store as project_store
    project = project_store.get_project_by_job(job_id)
    if project is None:
        raise HTTPException(404, "No project for this job")
    project["lesson_progress"] = project_store.get_lesson_progress(project["id"])
    project["checkpoints"]     = project_store.get_checkpoints(project["id"])
    return project


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    from ..projects import store as project_store
    project = project_store.get_project(project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    project["lesson_progress"] = project_store.get_lesson_progress(project_id)
    project["checkpoints"]     = project_store.get_checkpoints(project_id)
    project["corrections"]     = project_store.get_corrections(project_id)
    project["attempts"]        = project_store.get_attempts(project_id)
    project["selections"]      = project_store.get_selections(project_id)
    return project


@app.patch("/projects/{project_id}")
def patch_project(project_id: str, body: _ProjectPatch):
    from ..projects import store as project_store
    if body.current_capability is not None:
        from ..capabilities import resolve_capability_id
        if resolve_capability_id(body.current_capability) is None:
            raise HTTPException(422, f"Unknown capability: {body.current_capability!r}")
    project = project_store.update_project(
        project_id, title=body.title, current_capability=body.current_capability,
    )
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@app.post("/projects/{project_id}/progress")
def set_progress(project_id: str, body: _StepStatus):
    from ..projects import store as project_store
    if project_store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    try:
        return project_store.set_step_status(project_id, body.step_id, body.status, body.data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/projects/{project_id}/checkpoints")
def upsert_checkpoint(project_id: str, body: _CheckpointUpsert):
    from ..projects import store as project_store
    if project_store.get_project(project_id) is None:
        raise HTTPException(404, "Project not found")
    try:
        return project_store.upsert_checkpoint(
            project_id, body.type, body.status, body.data, body.checkpoint_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/capabilities")
def get_capabilities():
    """The shared capability contract: what the product can do, which
    interaction modes each capability supports, pipeline step metadata and
    detail-level labels. The landing page, gallery and workspace are all
    generated from / validated against this payload."""
    return registry_payload()


@app.get("/brands")
def list_paint_brands(medium: str | None = None):
    """Real-paint tube sets for brand-specific mixing recipes.

    Optional ``?medium=`` filters to one medium (oil/acrylic/watercolor).
    Each entry: {"id", "name", "medium", "tube_count"}.
    """
    return list_brands(medium)


@app.get("/mediums/")
def list_mediums():
    """List available painting mediums with their recommended settings."""
    return {
        mid: {
            "name":                     cfg["name"],
            "recommended_value_zones":  cfg["recommended_value_zones"],
            "recommended_palette_size": cfg["recommended_palette_size"],
            "edge_strategy":            cfg["edge_strategy"],
            "texture_strategy":         cfg["texture_strategy"],
            "stage_count":              len(cfg["stages"]),
        }
        for mid, cfg in MEDIUMS.items()
    }


@app.get("/mediums/{medium}")
def get_medium_config(medium: str):
    """Full config for a specific painting medium including ordered stages and instructions."""
    from ..schemas.jobs import VALID_MEDIUMS
    if medium not in VALID_MEDIUMS:
        raise HTTPException(404, f"Unknown medium: {medium!r}")
    return _get_medium_cfg(medium)


# ── POST /jobs/{job_id}/local-analysis ────────────────────────────────────────
# Phase 2 leftover: rectangle region selection + "Analyse this area". Crops
# ONLY from the untouched outputs/{job_id}/reference.* file (never a preview
# or generated overlay) and runs the same hierarchical analysis the
# whole-image lesson uses, scoped to that crop. See backend/analysis/local.py.
class _LocalAnalysisBBox(_BaseModel):
    x: float
    y: float
    w: float
    h: float


@app.post("/jobs/{job_id}/local-analysis")
def local_analysis(job_id: str, body: _LocalAnalysisBBox):
    """Run a local, zoomed-in analysis over a student-selected rectangle
    (ORIGINAL image px). Returns asset paths plus the offset/scale needed to
    map the local result's pixels back onto the parent image."""
    from ..analysis.local import run_local_analysis, LocalAnalysisError

    try:
        result = run_local_analysis(job_id, body.model_dump())
    except FileNotFoundError:
        raise HTTPException(404, "Reference image not found — has the job finished analysing?")
    except LocalAnalysisError as exc:
        raise HTTPException(422, str(exc))

    # Persist the deeper-look selection on the project so it survives a resume
    # (brief §18: local deep analyses are part of the saved state). Best-effort.
    try:
        from ..projects import store as project_store
        project = project_store.get_project_by_job(job_id)
        if project:
            project_store.add_selection(project["id"], {
                "selection_id": result.get("selection_id"),
                "bbox": result.get("bbox"),
                "offset": result.get("offset"),
                "scale": result.get("scale"),
            })
    except Exception:
        import logging
        logging.getLogger(__name__).warning("selection recording failed", exc_info=True)

    return result


# ── helpers ───────────────────────────────────────────────────────────────────
def _path_to_url(path: str | None, job_id: str) -> str | None:
    if not path:
        return None
    p = Path(path)
    try:
        # Convert outputs/{job_id}/foo.png → /outputs/{job_id}/foo.png.
        # outputs_root() is read at call time so nested paths (e.g.
        # critique/attempt_1/...) survive an OUTPUTS_DIR override in tests.
        rel = p.relative_to(outputs_root())
        return f"/outputs/{rel}"
    except ValueError:
        return f"/outputs/{job_id}/{p.name}"
