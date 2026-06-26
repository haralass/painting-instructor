from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, field_validator


JobStatus = Literal["queued", "processing", "completed", "failed"]


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
    result: Optional[JobResult] = None
    error: Optional[str] = None


class CreateJobResponse(BaseModel):
    job_id: str


VALID_MEDIUMS = {"oil", "watercolor", "acrylic", "pencil", "charcoal"}
VALID_VALUE_ZONES = {3, 5, 7}


def validate_medium(medium: str) -> str:
    if medium not in VALID_MEDIUMS:
        raise ValueError(f"medium must be one of {sorted(VALID_MEDIUMS)}, got {medium!r}")
    return medium


def validate_palette_size(v: int) -> int:
    if not (6 <= v <= 32):
        raise ValueError(f"palette_size must be between 6 and 32, got {v}")
    return v


def validate_detail_level(v: int) -> int:
    if not (1 <= v <= 5):
        raise ValueError(f"detail_level must be between 1 and 5, got {v}")
    return v


def validate_value_zones(v: int) -> int:
    if v not in VALID_VALUE_ZONES:
        raise ValueError(f"value_zones must be 3, 5, or 7, got {v}")
    return v
