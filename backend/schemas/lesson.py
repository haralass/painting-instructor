"""
Shared lesson-step and checkpoint schemas (brief §7 / Phase-1 adjustment #2).

These are the data contracts the Phase-4 lesson engine will emit and the
project store already persists against. Defining them now means the
capability registry, project model and API do not need another redesign
when lesson generation lands.

Nothing here generates lessons yet — the schemas are the contract only.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# The teaching flow, whole-to-part (how painters actually work): plan small
# studies off-canvas, draw the outlines FIRST (envelope → silhouette →
# internal → shadow line), then paint in whole-canvas passes — block-in
# (value+colour together), develop, render (focal only) — and finish.
LessonPhase = Literal[
    "plan",          # thumbnails, small notan study, palette plan (off-canvas)
    "composition",   # crop, placement, subject bounds, axes  (legacy alias kept)
    "drawing",       # envelope, silhouette, internal + tonal outlines, proportion
    "block_in",      # first whole-canvas pass: big masses, value+colour together
    "develop",       # second pass: medium shapes, form, temperature
    "render",        # third pass: focal only — edges, detail, accents
    "finish",        # final check + upload for critique
    # legacy phases (older lessons still parse):
    "value", "colour", "form", "edges", "detail",
]

CheckpointType = Literal[
    "placement", "silhouette", "proportion", "values",
    "colour_masses", "edges", "final",
]

# How a checkpoint or completion check can be satisfied.
AttemptKind = Literal["upload", "trace", "confirm"]


class OverlayRef(BaseModel):
    """A contextual overlay bound to a lesson step (brief §10: overlays are
    contextual, never a user-facing layer panel)."""
    kind: Literal[
        "silhouette", "landmarks", "value_mask", "edge_guides",
        "colour_regions", "region_boundaries", "correction_arrows",
        "outline", "image", "svg",
    ]
    asset: Optional[str] = None          # outputs-relative path when rendered
    region_ids: list[int] = Field(default_factory=list)  # hierarchy region ids
    opacity: float = 1.0


class CompletionCheck(BaseModel):
    kind: AttemptKind = "confirm"
    criteria: str = ""                   # human-readable "you are done when…"


class Checkpoint(BaseModel):
    """A gate the learner must pass before dependent steps unlock — e.g. the
    drawing must be validated before values begin (brief §2.G)."""
    id: str
    type: CheckpointType
    title: str
    instructions: str = ""
    required: bool = True
    accepts: list[AttemptKind] = Field(default_factory=lambda: ["upload", "confirm"])


class LessonStep(BaseModel):
    """One concrete teaching action, traceable to image regions and overlays
    (brief §7's step schema)."""
    id: str
    capability_id: str                   # registry id this step teaches
    phase: LessonPhase
    order: int
    title: str
    objective: str
    explanation: str = ""
    action: str                          # the exact thing the user does
    region_ids: list[int] = Field(default_factory=list)
    overlays: list[OverlayRef] = Field(default_factory=list)
    tool: Optional[str] = None           # brush/pencil where relevant
    mixture: Optional[str] = None        # working-mixture name where relevant
    completion_check: Optional[CompletionCheck] = None
    common_mistake: Optional[str] = None
    stop_condition: Optional[str] = None # "stop before you…"
    checkpoint_id: Optional[str] = None  # checkpoint required after this step
    depends_on: list[str] = Field(default_factory=list)  # step ids


GuidanceStyle = Literal["full", "balanced", "autonomy"]


class Lesson(BaseModel):
    """A generated, medium-aware lesson: ordered steps + checkpoint gates.
    Guidance style changes step granularity and checkpoint count — never the
    truth of the image (brief §2.Q)."""
    id: str
    capability_id: str
    medium: str
    guidance: GuidanceStyle = "balanced"
    steps: list[LessonStep] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)

    def validate_graph(self) -> list[str]:
        """Structural sanity: unique ids, resolvable dependencies/checkpoints,
        and no step of a later phase unlocked before a required checkpoint of
        an earlier phase. Returns problems (empty = healthy)."""
        problems: list[str] = []
        step_ids = [s.id for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            problems.append("duplicate step ids")
        cp_ids = {c.id for c in self.checkpoints}
        if len(cp_ids) != len(self.checkpoints):
            problems.append("duplicate checkpoint ids")
        known = set(step_ids)
        for s in self.steps:
            for dep in s.depends_on:
                if dep not in known:
                    problems.append(f"step {s.id}: unknown dependency {dep!r}")
            if s.checkpoint_id is not None and s.checkpoint_id not in cp_ids:
                problems.append(f"step {s.id}: unknown checkpoint {s.checkpoint_id!r}")
        orders = [s.order for s in self.steps]
        if orders != sorted(orders):
            problems.append("steps are not in ascending order")
        return problems
