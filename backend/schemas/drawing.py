"""
Structured drawing-construction models (Phase 3).

The point of this phase is that the drawing is not a PNG: it is a stored,
inspectable account of HOW the contour is built — bounds, landmarks, axis,
envelope, silhouette, internal structure — in a pedagogical order. These
models are what `analysis/drawing.py` fills and `drawing.json` serialises,
and what the Phase-4 lesson engine and Phase-6 critique will read.

Coordinate space: analysis pixels — the same grid as regions.json and the
per-level label maps. The frontend rescales to the untouched original via
the Phase-2 `imageCoords` utilities, so one shared coordinate system holds.
`normalized` fields ([0,1]) are a convenience, never a replacement for pixel
space.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Pt = tuple[float, float]

# ── Vocabularies ──────────────────────────────────────────────────────────────

LandmarkCategory = Literal[
    "subject_top", "subject_bottom", "subject_left", "subject_right",
    "major_corner", "direction_change", "widest_point", "narrowest_point",
    "axis_endpoint", "major_intersection", "internal_division",
    "proportion_reference", "alignment_reference",
]

PathCategory = Literal[
    "silhouette", "envelope_segment", "internal_division",
    "secondary_structure", "alignment", "axis",
]

# The construction stages, in the order the drawing must be built (spec §2).
ConstructionStageId = Literal[
    "canvas", "placement", "bounds", "occupied_area", "landmarks", "axis",
    "slopes", "envelope", "negative_space", "proportion", "silhouette",
    "internal_divisions", "secondary_structure", "checkpoint",
]

# Soft edge-cause estimate — never asserted as certain (spec §3 / §16).
EdgeCause = Literal["object_boundary", "depth", "illumination", "reflectance", "texture"]


# ── Leaf models ───────────────────────────────────────────────────────────────

class Landmark(BaseModel):
    id: str
    category: LandmarkCategory
    x: float                         # analysis-image pixels
    y: float
    normalized: Pt                   # [0,1] convenience
    importance: float = 0.5          # 0..1
    confidence: float = 0.5          # 0..1 — how sure the detector is
    related_path_ids: list[str] = Field(default_factory=list)
    related_region_ids: list[int] = Field(default_factory=list)
    parent_landmark_id: Optional[str] = None
    visibility_level: int = 1        # smallest detail level at which it shows (1..5)
    lesson_order: int = 0
    user_x: Optional[float] = None   # user-corrected position (Phase 4)
    user_y: Optional[float] = None


class Axis(BaseModel):
    id: str
    start: Pt                        # analysis px
    end: Pt
    orientation_deg: float           # 0 = horizontal, 90 = vertical
    role: Literal["main_axis", "dominant_slope", "alignment"]
    related_landmark_ids: list[str] = Field(default_factory=list)
    related_region_ids: list[int] = Field(default_factory=list)
    importance: float = 0.5
    visibility_level: int = 1
    lesson_order: int = 0


class EdgeCauseEstimate(BaseModel):
    """Soft attribution of what the contour edge is caused by. Scores are a
    distribution over causes; `primary` is the arg-max but is only meaningful
    when `confidence` is high. Ambiguous edges stay ambiguous (spec §3)."""
    scores: dict[EdgeCause, float] = Field(default_factory=dict)
    primary: Optional[EdgeCause] = None
    confidence: float = 0.0


class VectorPath(BaseModel):
    id: str
    category: PathCategory
    points: list[Pt]                 # analysis px, ordered
    closed: bool = False
    start_landmark_id: Optional[str] = None
    end_landmark_id: Optional[str] = None
    region_ids: list[int] = Field(default_factory=list)   # ownership
    parent_path_id: Optional[str] = None
    child_path_ids: list[str] = Field(default_factory=list)
    hierarchy_level: int = 1         # 1 (coarsest) .. 5
    importance: float = 0.5
    persistence: float = 0.0         # how many hierarchy levels it survives (0..1)
    edge_cause: Optional[EdgeCauseEstimate] = None
    stage: ConstructionStageId = "silhouette"
    lesson_order: int = 0
    suggested_direction: Optional[Literal["forward", "reverse"]] = None
    user_edited: bool = False


class NegativeSpace(BaseModel):
    id: str
    polygon: list[Pt]                # analysis px
    touches_edges: list[Literal["top", "bottom", "left", "right"]] = Field(default_factory=list)
    neighbour_path_ids: list[str] = Field(default_factory=list)
    area_fraction: float = 0.0       # of the subject bounding box
    importance: float = 0.5
    proportion_check_id: Optional[str] = None
    visibility_level: int = 2
    lesson_order: int = 0


class Envelope(BaseModel):
    """The simplified outer construction shape — a small number of major
    straight segments/broad curves. Stored SEPARATELY from the refined
    silhouette so the progression envelope → silhouette is preserved
    (spec §4.F); never overwritten."""
    id: str
    vertices: list[Pt]               # analysis px, ordered (closed loop)
    segment_count: int = 0
    landmark_ids: list[str] = Field(default_factory=list)


class ProportionCheck(BaseModel):
    id: str
    kind: Literal["ratio", "alignment", "negative_space", "thirds"]
    label: str                       # human-readable, image-specific
    value: Optional[float] = None    # e.g. height/width ratio
    reference_points: list[Pt] = Field(default_factory=list)
    landmark_ids: list[str] = Field(default_factory=list)
    lesson_order: int = 0


class ConstructionStage(BaseModel):
    """One step in the pedagogical build order — the spine the Phase-4 lesson
    engine hangs concrete instructions on. References the geometry it reveals
    by id; carries no instruction text itself (that is generated per medium /
    guidance later)."""
    id: ConstructionStageId
    order: int
    title: str
    summary: str                     # neutral description of what this stage establishes
    landmark_ids: list[str] = Field(default_factory=list)
    axis_ids: list[str] = Field(default_factory=list)
    path_ids: list[str] = Field(default_factory=list)
    negative_space_ids: list[str] = Field(default_factory=list)
    proportion_check_ids: list[str] = Field(default_factory=list)
    is_checkpoint: bool = False


class SubjectBounds(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    margins: dict[str, float]        # top/bottom/left/right, as fractions of canvas
    occupied_fraction: float         # subject area / canvas area
    source: Literal["subject_mask", "region_fallback", "whole_frame"]
    confidence: float = 0.5


class DrawingAnalysis(BaseModel):
    id: str
    project_id: Optional[str] = None
    job_id: Optional[str] = None
    source_selection_id: Optional[str] = None   # set when this is a local crop
    parent_analysis_id: Optional[str] = None
    coord_space: Literal["analysis_px"] = "analysis_px"
    image_width: int
    image_height: int
    canvas_ratio: float                          # width / height
    subject_bounds: SubjectBounds
    occupied_area: list[Pt] = Field(default_factory=list)     # hull polygon
    main_axis: Optional[Axis] = None
    dominant_slopes: list[Axis] = Field(default_factory=list)
    alignments: list[Axis] = Field(default_factory=list)
    landmarks: list[Landmark] = Field(default_factory=list)
    negative_spaces: list[NegativeSpace] = Field(default_factory=list)
    proportion_checks: list[ProportionCheck] = Field(default_factory=list)
    envelope: Optional[Envelope] = None
    silhouette: Optional[VectorPath] = None
    internal_paths: list[VectorPath] = Field(default_factory=list)
    construction_order: list[ConstructionStage] = Field(default_factory=list)
    algorithm_version: str = "drawing-1"
    parameters: dict = Field(default_factory=dict)
    source_assets: dict[str, str] = Field(default_factory=dict)
    generated_at: Optional[str] = None

    def all_paths(self) -> list[VectorPath]:
        paths = list(self.internal_paths)
        if self.silhouette:
            paths.append(self.silhouette)
        return paths
