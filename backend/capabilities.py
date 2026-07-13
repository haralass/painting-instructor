"""
The shared capability registry — the single source of truth for what this
product can do.

Every surface reads from here:
  - the FastAPI layer exposes it at GET /capabilities,
  - workers/tasks.py takes its progress steps/messages from STEP_INFO,
  - analysis/renderer.py takes its detail-level labels from DETAIL_LEVELS,
  - scripts/generate_frontend_contract.py emits the checked-in TypeScript
    contract the landing page, gallery and workspace consume.

Nothing may be advertised on any surface unless it is declared here with
`implemented=True`, and tests/test_capabilities.py enforces the invariants
(unique ids, resolvable pipeline steps, existing sample assets). The
migration table records every retired/merged identifier so persisted
outputs keep resolving.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Modes and support flags (brief §7 / §23-adjustments) ─────────────────────

class CapabilityModes(BaseModel):
    """Which of the three interaction modes this capability offers TODAY."""
    study:  bool = False   # the user can inspect a generated result
    lesson: bool = False   # the system teaches its construction step by step
    check:  bool = False   # the user can submit an attempt for feedback


class CapabilitySupports(BaseModel):
    local_region:      bool = False  # can run on a user-selected region
    manual_correction: bool = False  # the user can correct the analysis
    checkpoint:        bool = False  # participates in progress checkpoints


class CapabilityOutput(BaseModel):
    kind: Literal["image", "json", "svg", "video", "pdf"]
    key:  str   # page stem / manifest key, e.g. "notan" → outputs/{job}/notan.png


Category = Literal["analysis", "coaching", "exercise", "teaching", "deliverable", "internal"]


class Capability(BaseModel):
    id:          str
    name:        str
    category:    Category
    order:       int = 0          # display order on landing/gallery
    description: str              # one-line tagline (landing tile / gallery card)
    why:         str = ""         # workspace "WHY?" explanation
    tip:         str = ""         # workspace actionable tip
    implemented: bool = True
    advertised:  bool = True      # shown on landing + gallery
    workspace:   bool = True      # shown in the workspace classic-analysis list
    modes:       CapabilityModes = Field(default_factory=CapabilityModes)
    supports:    CapabilitySupports = Field(default_factory=CapabilitySupports)
    outputs:     list[CapabilityOutput] = Field(default_factory=list)
    pipeline_step: Optional[str] = None   # STEP_INFO key that produces it
    sample:      Optional[str] = None     # /samples/demo1/<file> used by landing+gallery
    replaces:    list[str] = Field(default_factory=list)


# ── Pipeline step info — the ONE progress table ──────────────────────────────
# tasks.py reports progress from this dict and the frontend derives its step
# labels + loading-canvas stages from the same generated data, so a new step
# can never again ship half-registered (the PR #15/#16/#17 bug class).

class StepInfo(BaseModel):
    pct:     int          # progress checkpoint percentage
    message: str          # human message shown during processing
    stage:   int = 0      # evolving-canvas visual stage 0–5


STEP_INFO: dict[str, StepInfo] = {
    "loading":           StepInfo(pct=5,   message="Loading image",                          stage=0),
    "subject_mask":      StepInfo(pct=7,   message="Isolating the subject",                  stage=0),
    "depth":             StepInfo(pct=9,   message="Estimating depth",                       stage=0),
    "line_art":          StepInfo(pct=15,  message="Drawing outlines",                       stage=1),
    "notan":             StepInfo(pct=25,  message="Mapping values",                         stage=2),
    "value_analysis":    StepInfo(pct=30,  message="Analysing values",                       stage=2),
    "color_temperature": StepInfo(pct=35,  message="Analysing warm/cool tones",              stage=3),
    "color_palette":     StepInfo(pct=42,  message="Extracting colour palette",              stage=3),
    "light_direction":   StepInfo(pct=48,  message="Finding light source",                   stage=3),
    # Retained for jobs created before the classic generator was retired —
    # the hierarchy-based paint-by-numbers now renders under "hierarchical".
    "color_by_number":   StepInfo(pct=55,  message="Building paint-by-numbers",              stage=4),
    "subject_focus":     StepInfo(pct=56,  message="Rendering the focal subject",            stage=3),
    "depth_planes":      StepInfo(pct=57,  message="Mapping depth planes",                   stage=3),
    "local_vs_light":    StepInfo(pct=58,  message="Separating colour from light",           stage=3),
    "value_traps":       StepInfo(pct=59,  message="Detecting perceptual traps",             stage=2),
    "edge_coach":        StepInfo(pct=61,  message="Mapping edge hardness",                  stage=4),
    "composition":       StepInfo(pct=63,  message="Checking the composition",               stage=4),
    "dot_to_dot":        StepInfo(pct=65,  message="Building the dot-to-dot exercise",       stage=1),
    "hierarchical":      StepInfo(pct=75,  message="Building hierarchical regions",          stage=4),
    "analysis_ready":    StepInfo(pct=80,  message="Analysis complete — generating extras",  stage=4),
    "observations":      StepInfo(pct=82,  message="Looking at your image",                  stage=4),
    "rendering_extras":  StepInfo(pct=85,  message="Rendering video and PDF",                stage=5),
    "stroke_paint":      StepInfo(pct=86,  message="Painting the brushstrokes",              stage=5),
    "video":             StepInfo(pct=88,  message="Rendering tutorial video",               stage=5),
    "pdf":               StepInfo(pct=93,  message="Assembling PDF book",                    stage=5),
    "manifest":          StepInfo(pct=97,  message="Writing manifest",                       stage=5),
    "completed":         StepInfo(pct=100, message="Tutorial ready",                         stage=5),
}


# ── Detail levels ─────────────────────────────────────────────────────────────
# "Reference" is reserved for the untouched original photograph. Level 5 is
# the FINEST QUANTIZED CUT of the merge tree — an accurate simplification,
# never the photo — so it must never be called "Full Reference".

class DetailLevelInfo(BaseModel):
    level:        int
    label:        str
    description:  str
    regions_hint: str


DETAIL_LEVELS: list[DetailLevelInfo] = [
    DetailLevelInfo(level=1, label="Foundation",
                    description="The largest masses and primary contours — placement and structure only.",
                    regions_hint="4–8 masses"),
    DetailLevelInfo(level=2, label="Simplified",
                    description="Major forms and the key light/shadow divisions.",
                    regions_hint="8–25 regions"),
    DetailLevelInfo(level=3, label="Standard",
                    description="Important internal structure and colour zones — most paintings work here.",
                    regions_hint="25–70 regions"),
    DetailLevelInfo(level=4, label="Detailed",
                    description="Smaller transitions, secondary edges and selected texture.",
                    regions_hint="70–180 regions"),
    DetailLevelInfo(level=5, label="Full Detail",
                    description="Every detected region — the finest simplification the analysis makes. "
                                "For the actual photograph, use the Reference view.",
                    regions_hint="150–400 regions"),
]

LEVEL_LABELS: dict[int, str] = {d.level: d.label for d in DETAIL_LEVELS}


# ── The capabilities ──────────────────────────────────────────────────────────

def _img(key: str) -> list[CapabilityOutput]:
    return [CapabilityOutput(kind="image", key=key)]


CAPABILITIES: list[Capability] = [
    Capability(
        id="line_art", name="Line Art", category="analysis", order=10,
        description="Weighted ink contours — silhouette, interior forms, texture.",
        why="Every painting starts with clear structure. These lines define the silhouette "
            "(thickest, most important), interior forms (medium weight), and background texture (lightest).",
        tip="Transfer these outlines to your canvas with light charcoal. Don't press hard — "
            "you'll erase them as you paint.",
        modes=CapabilityModes(study=True),
        outputs=_img("line_art"), pipeline_step="line_art", sample="line_art.jpg",
    ),
    Capability(
        id="notan", name="Value Study (Notan)", category="analysis", order=20,
        description="Lights and darks resolved first — get these right and the painting reads.",
        why="Notan is a Japanese design concept — before you touch colour, you must get your "
            "lights and darks right. A painting with correct values reads in black and white.",
        tip="Mix 3 values: darkest dark, mid grey, white. Fill the entire canvas with these "
            "before adding colour.",
        modes=CapabilityModes(study=True),
        supports=CapabilitySupports(checkpoint=True),
        outputs=_img("notan"), pipeline_step="notan", sample="notan.jpg",
    ),
    Capability(
        id="color_temperature", name="Colour Temperature", category="analysis", order=30,
        description="Warm and cool tendencies mapped across this image.",
        why="In many lighting setups lit areas trend warm and shadows cool — but it depends on "
            "the light source. This map shows what THIS image actually does, approximated from "
            "LAB b* + chroma.",
        tip="Premix a warm and a cool version of your key colours. Follow the map, not a rule "
            "of thumb — check what the reference really does.",
        modes=CapabilityModes(study=True),
        outputs=_img("color_temperature"), pipeline_step="color_temperature",
        sample="color_temperature.jpg",
    ),
    Capability(
        id="color_palette", name="Colour Palette", category="analysis", order=40,
        description="Dominant colours by area, with real tube-mixing recipes.",
        why="The dominant colours of your reference, sorted by area coverage. A limited palette "
            "forces harmony — mix from these rather than adding new tubes.",
        tip="Lay out this palette before you start. Only these colours — no extras.",
        modes=CapabilityModes(study=True),
        outputs=_img("color_palette"), pipeline_step="color_palette", sample="color_palette.jpg",
    ),
    Capability(
        id="light_direction", name="Light & Shadow Zones", category="analysis", order=50,
        description="Gurney's five zones, from highlight to cast shadow.",
        why="Gurney's 5 zones: Highlight → Halftone → Core Shadow → Reflected Light → Cast "
            "Shadow. The core shadow is your darkest paint.",
        tip="Position your actual light source to match this angle, or mentally commit to it "
            "and never change it.",
        modes=CapabilityModes(study=True),
        outputs=_img("light_direction"), pipeline_step="light_direction",
        sample="light_direction.jpg",
    ),
    Capability(
        id="color_by_number", name="Paint by Numbers", category="exercise", order=60,
        description="Flat colour blocking from the same region hierarchy the lesson teaches.",
        why="Flat colour blocking is how most painters start a canvas. Fill the entire canvas "
            "before blending — if any white shows through, you cannot judge colour relationships.",
        tip="Block in flat colour before blending. Use a large flat brush, cover every zone "
            "completely.",
        modes=CapabilityModes(study=True),
        supports=CapabilitySupports(checkpoint=True),
        outputs=_img("color_by_number"), pipeline_step="hierarchical",
        sample="color_by_number.jpg",
        replaces=["color_by_number_classic"],
    ),
    Capability(
        id="dot_to_dot", name="Dot to Dot", category="exercise", order=70,
        description="Numbered dots along the real region boundaries — connect them to build the drawing.",
        why="These dots follow the actual boundaries of the image's major shapes. Connecting "
            "them in order builds your under-drawing.",
        tip="Connect these dots lightly with a pencil before painting. This is your structural "
            "under-drawing.",
        modes=CapabilityModes(study=True),
        outputs=_img("dot_to_dot"), pipeline_step="hierarchical", sample="dot_to_dot.jpg",
        replaces=["dot_to_dot_classic"],
    ),
    Capability(
        id="subject_focus", name="Focal Subject", category="coaching", order=80,
        description="Your subject isolated — where the eye must land first.",
        why="A local segmentation model isolates your subject from its background. The eye "
            "should land here first — keep this area the sharpest, most saturated, and highest "
            "in contrast.",
        tip="Paint the muted areas first and loosely; save your cleanest colour, hardest edges, "
            "and thickest paint for the subject.",
        modes=CapabilityModes(study=True),
        outputs=_img("subject_focus"), pipeline_step="subject_focus", sample="subject_focus.jpg",
    ),
    Capability(
        id="depth_planes", name="Depth Planes", category="coaching", order=90,
        description="Foreground, middle and background split so distance reads cooler and softer.",
        why="A local depth model splits the scene into foreground, middle-ground and background. "
            "Atmospheric perspective means distance reads as cooler, lighter and lower in contrast.",
        tip="Push the background cooler, lighter and softer than it looks; reserve your warmest, "
            "darkest, hardest-edged notes for the foreground.",
        modes=CapabilityModes(study=True),
        outputs=_img("depth_planes"), pipeline_step="depth_planes", sample="depth_planes.jpg",
    ),
    Capability(
        id="local_vs_light", name="Local Colour vs Light", category="coaching", order=100,
        description="An estimate of the object's colour separated from the light falling on it.",
        why="Left is an ESTIMATE of the local colour with the light divided out; right is the "
            "estimated light alone. A shadow isn't a different colour — it's the same local "
            "colour under less light. The split is approximate, not a physical measurement.",
        tip="Judge an object's true colour from the lit-and-shadowed average, then adjust it "
            "for the light — don't reach for a whole new colour.",
        modes=CapabilityModes(study=True),
        outputs=_img("local_vs_light"), pipeline_step="local_vs_light", sample="local_vs_light.jpg",
    ),
    Capability(
        id="value_traps", name="Value Traps", category="coaching", order=110,
        description="Where simultaneous contrast will fool your eye — flagged before you paint.",
        why="Simultaneous contrast fools the eye: a shape looks darker against a light surround "
            "and lighter against a dark one, so you paint the apparent value, not the true one. "
            "The tinted zones are where the trap is strongest.",
        tip="In these zones, don't trust the local comparison. Judge the value against the "
            "whole picture — hold your darkest dark and lightest light in mind.",
        modes=CapabilityModes(study=True),
        outputs=_img("value_traps"), pipeline_step="value_traps", sample="value_traps.jpg",
    ),
    Capability(
        id="edge_coach", name="Edge Control", category="coaching", order=120,
        description="Hard, soft and lost edges mapped, so sharpness leads the eye.",
        why="The eye locks onto the hardest edge in the picture. Warm marks are your hard/found "
            "edges, cool are soft/lost. They should cluster on the focal subject — equal "
            "sharpness everywhere means nothing leads the eye.",
        tip="Keep your crispest edges on the focal point; soften edges where similar values "
            "meet and everywhere you want the eye to pass over.",
        modes=CapabilityModes(study=True),
        supports=CapabilitySupports(checkpoint=True),
        outputs=_img("edge_coach"), pipeline_step="edge_coach", sample="edge_coach.jpg",
    ),
    Capability(
        id="composition", name="Composition & Focus", category="coaching", order=130,
        description="Where attention is pulled — and any rival that competes for it.",
        why="The warm ring is where the eye is pulled hardest (contrast × detail × colour); a "
            "cool ring marks a rival that competes for attention. A strong picture has one "
            "focal point.",
        tip="If two centres compete, subdue one — lower its contrast, detail or saturation.",
        modes=CapabilityModes(study=True),
        supports=CapabilitySupports(checkpoint=True),
        outputs=_img("composition"), pipeline_step="composition", sample="composition.jpg",
    ),
    Capability(
        id="study_overlay", name="Detail Study", category="analysis", order=140,
        description="Every region boundary traced directly on the reference photograph.",
        why="Every colour-region boundary traced directly on the reference — the digital "
            "version of outlining shapes by hand on a print. Use it to see exactly where one "
            "colour ends and the next begins.",
        tip="Pick one small area, follow its traced shapes, and mix each one separately before "
            "you commit it to the canvas.",
        modes=CapabilityModes(study=True),
        outputs=_img("study_overlay"), pipeline_step="hierarchical", sample="study_overlay.jpg",
    ),
    # ── Teaching surfaces (workspace views, not classic image pages) ─────────
    Capability(
        id="lesson_plan", name="Guided Lesson", category="teaching", order=200,
        description="A staged painting plan for your medium, grounded in this image's own masses.",
        advertised=True, workspace=False,
        modes=CapabilityModes(study=True, lesson=True),
        outputs=[CapabilityOutput(kind="json", key="lesson_plan")],
        pipeline_step="manifest", sample=None,
    ),
    Capability(
        id="critique", name="Progress Critique", category="teaching", order=210,
        description="Photograph your attempt and get measured, localised feedback against the reference.",
        advertised=True, workspace=False,
        modes=CapabilityModes(check=True),
        supports=CapabilitySupports(checkpoint=True),
        outputs=[CapabilityOutput(kind="json", key="critique")],
        pipeline_step=None, sample=None,
    ),
    Capability(
        id="drawing_construction", name="Drawing Construction", category="teaching", order=215,
        description="How the drawing is built — bounds, landmarks, axis, envelope, then the refined "
                    "silhouette and internal structure, in the order you should draw them.",
        why="A painting is only as good as the drawing under it. This shows the construction "
            "order — placement and big shapes first, detail last — instead of a finished outline "
            "to copy blindly.",
        tip="Work in this order: mark the outer limits, block the envelope, check the negative "
            "spaces and proportions, and only then refine the silhouette.",
        advertised=True, workspace=False,
        modes=CapabilityModes(study=True),
        supports=CapabilitySupports(local_region=True, manual_correction=True, checkpoint=True),
        outputs=[CapabilityOutput(kind="json", key="drawing_construction")],
        pipeline_step="hierarchical", sample=None,
    ),
    Capability(
        id="detail_levels", name="Detail Explorer", category="teaching", order=220,
        description="One stable hierarchy of the image, from 5 masses to full detail — never re-segmented.",
        advertised=True, workspace=False,
        modes=CapabilityModes(study=True),
        supports=CapabilitySupports(local_region=False),
        outputs=[CapabilityOutput(kind="json", key="detail_levels")],
        pipeline_step="hierarchical", sample=None,
    ),
    # ── Deliverables — never presented as image studies ──────────────────────
    Capability(
        id="video", name="Tutorial Video", category="deliverable", order=300,
        description="A progressive video lesson: outline → values → colour → stroke by stroke.",
        workspace=False,
        modes=CapabilityModes(study=True),
        outputs=[CapabilityOutput(kind="video", key="video")],
        pipeline_step="video", sample=None,
    ),
    Capability(
        id="pdf", name="Tutorial Book (PDF)", category="deliverable", order=310,
        description="The whole lesson assembled as a printable A4 book.",
        workspace=False,
        modes=CapabilityModes(study=True),
        outputs=[CapabilityOutput(kind="pdf", key="pdf")],
        pipeline_step="pdf", sample=None,
    ),
    # ── Internal (never advertised; kept honest in the registry) ─────────────
    Capability(
        id="value_zones", name="Value Zone Map", category="internal", order=900,
        description="Internal value-simplification map used by the lesson plan and PDF.",
        advertised=False, workspace=False,
        modes=CapabilityModes(),
        outputs=_img("value_zones"), pipeline_step="hierarchical", sample=None,
    ),
]

CAPABILITY_BY_ID: dict[str, Capability] = {c.id: c for c in CAPABILITIES}


# ── Migration map (Phase-1 adjustment #5) ─────────────────────────────────────
# Old persisted/board identifiers → their current home. Filenames on disk
# never changed, so old manifests keep resolving; this table exists so code
# and docs never silently break an identifier.

class CapabilityMigration(BaseModel):
    old_id: str
    action: Literal["keep", "merge", "retire", "rename"]
    new_id: Optional[str] = None
    note:   str = ""


MIGRATIONS: list[CapabilityMigration] = [
    CapabilityMigration(old_id="color_by_number_classic", action="merge", new_id="color_by_number",
                        note="Classic BiSeNet/RAG generator retired; the hierarchy render already "
                             "wrote the same color_by_number.png. No on-disk change."),
    CapabilityMigration(old_id="dot_to_dot_classic", action="merge", new_id="dot_to_dot",
                        note="Classic skeleton-trace generator retired; the hierarchy smart dots "
                             "already overwrote the same dot_to_dot.png. No on-disk change."),
    CapabilityMigration(old_id="pixel_grid", action="retire",
                        note="Dead code — zero references outside its own module."),
    CapabilityMigration(old_id="journaling", action="retire",
                        note="Dead code — empty package, never imported."),
    CapabilityMigration(old_id="tutorial_video_pdf_tile", action="merge", new_id="video",
                        note="Was presented as a 14th 'study' on the landing page; split into the "
                             "video + pdf deliverable capabilities."),
    CapabilityMigration(old_id="full_reference_level", action="rename", new_id="detail_levels",
                        note="Level 5's label 'Full Reference' renamed to 'Full Detail'. Old "
                             "manifests store the old label string; the frontend renders level "
                             "labels by NUMBER from this registry, so old jobs display the new "
                             "accurate name. 'Reference' now always means the untouched original."),
]


def resolve_capability_id(any_id: str) -> Optional[str]:
    """Map any current or historical identifier to the current capability id
    (None if the identifier was retired outright)."""
    if any_id in CAPABILITY_BY_ID:
        return any_id
    for m in MIGRATIONS:
        if m.old_id == any_id:
            return m.new_id
    return None


# ── Registry self-validation (used by tests and at API startup) ──────────────

def validate_registry() -> list[str]:
    """Return a list of invariant violations (empty = healthy)."""
    problems: list[str] = []
    seen: set[str] = set()
    for c in CAPABILITIES:
        if c.id in seen:
            problems.append(f"duplicate capability id: {c.id}")
        seen.add(c.id)
        if c.pipeline_step is not None and c.pipeline_step not in STEP_INFO:
            problems.append(f"{c.id}: pipeline_step {c.pipeline_step!r} not in STEP_INFO")
        if c.workspace and not any(o.kind == "image" for o in c.outputs):
            problems.append(f"{c.id}: workspace capability without an image output")
        if c.advertised and not c.implemented:
            problems.append(f"{c.id}: advertised but not implemented")
        if c.workspace and not c.advertised:
            problems.append(f"{c.id}: shown in workspace but hidden from landing/gallery "
                            f"(surfaces would disagree)")
    for m in MIGRATIONS:
        if m.new_id is not None and m.new_id not in CAPABILITY_BY_ID:
            problems.append(f"migration {m.old_id}: new_id {m.new_id!r} does not exist")
    levels = [d.level for d in DETAIL_LEVELS]
    if levels != [1, 2, 3, 4, 5]:
        problems.append(f"detail levels must be exactly 1..5, got {levels}")
    if any("reference" in d.label.lower() for d in DETAIL_LEVELS):
        problems.append("no detail-level label may contain 'Reference' — that word is "
                        "reserved for the untouched original image")
    return problems


def registry_payload() -> dict:
    """The full contract served at GET /capabilities and consumed by codegen."""
    return {
        "capabilities":  [c.model_dump() for c in sorted(CAPABILITIES, key=lambda c: c.order)],
        "steps":         {k: v.model_dump() for k, v in STEP_INFO.items()},
        "detail_levels": [d.model_dump() for d in DETAIL_LEVELS],
        "migrations":    [m.model_dump() for m in MIGRATIONS],
    }
