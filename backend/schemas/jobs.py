from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, field_validator


JobStatus = Literal["queued", "processing", "completed", "completed_with_warnings", "failed"]


class JobResult(BaseModel):
    manifest: str
    pages: list[str]
    video: Optional[str] = None
    pdf: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = 0
    step: str = ""
    message: str = ""
    analysis_ready: bool = False   # NEW — preliminary manifest available
    result: Optional[JobResult] = None
    error: Optional[str] = None


class CreateJobResponse(BaseModel):
    job_id: str


VALID_MEDIUMS = {"oil", "watercolor", "acrylic", "pencil", "charcoal", "digital"}
VALID_VALUE_ZONES = {3, 5, 7}
VALID_SKILL_LEVELS = {"beginner", "intermediate", "advanced"}


def validate_medium(medium: str) -> str:
    if medium not in VALID_MEDIUMS:
        raise ValueError(f"medium must be one of {sorted(VALID_MEDIUMS)}, got {medium!r}")
    return medium


def validate_skill_level(skill_level: str) -> str:
    if skill_level not in VALID_SKILL_LEVELS:
        raise ValueError(f"skill_level must be one of {sorted(VALID_SKILL_LEVELS)}, got {skill_level!r}")
    return skill_level


def validate_palette_size(v: int) -> int:
    if not (6 <= v <= 32):
        raise ValueError(f"palette_size must be between 6 and 32, got {v}")
    return v


def validate_initial_view_level(v: int) -> int:
    """
    initial_view_level only picks which of the 5 always-generated detail
    levels the frontend opens on first — it does not change what gets
    analysed or rendered.
    """
    if not (1 <= v <= 5):
        raise ValueError(f"initial_view_level must be between 1 and 5, got {v}")
    return v


def validate_value_zones(v: int) -> int:
    if v not in VALID_VALUE_ZONES:
        raise ValueError(f"value_zones must be 3, 5, or 7, got {v}")
    return v


def validate_texture_detail(v: bool) -> bool:
    return bool(v)

def validate_background_detail(v: bool) -> bool:
    return bool(v)
