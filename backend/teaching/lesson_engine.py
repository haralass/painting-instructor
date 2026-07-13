"""
Lesson engine (Phase 4).

Generates a real, per-image `Lesson` (the Phase-1 schemas/lesson.py contract)
from the Phase-3 drawing analysis and the existing value/colour/edge/brief
signals — a composition-first sequence with a drawing checkpoint before any
value, the progressive contour lesson, and a concrete objective / action /
completion-check / common-mistake / stop-condition on every step.

Design rules (from the brief):
- Structural phases (composition, drawing) come before value, colour, form,
  edges — the engine never teaches paint on an unverified drawing (§2.E/G).
- Guidance changes granularity + checkpoint count, never the geometry (§1.6).
- Medium changes execution notes, not the drawing order (§5).
- Instructions are grounded in THIS image (bounds, masses, value coverage,
  focal), and stay honest when a signal is weak.
"""
from __future__ import annotations

from typing import Any, Literal

from ..schemas.lesson import (
    Checkpoint, CompletionCheck, Lesson, LessonStep, OverlayRef,
)

Guidance = Literal["full", "balanced", "autonomy"]

# skill level (existing form) → guidance style (brief §4)
SKILL_TO_GUIDANCE: dict[str, Guidance] = {
    "beginner": "full", "intermediate": "balanced", "advanced": "autonomy",
}


# ── Medium execution notes (only the painting phases differ by medium) ────────
_MEDIUM_EXEC: dict[str, dict[str, str]] = {
    "oil": {
        "surface": "Tone the canvas with a thin mid-value wash (an imprimatura) and wipe it back "
                   "where the lights will go, so you are not judging colour against white.",
        "value":   "Work thin-to-thick and generally dark-to-light, fat over lean: keep your early, "
                   "leaner darks thin (more solvent, less oil) and let fatter, richer paint carry the "
                   "lights on top, so the paint film dries without cracking.",
        "mixture": "Pre-mix your main strings on the palette before touching the canvas — oil stays "
                   "workable, so mixing ahead keeps the masses consistent.",
        "edges":   "Soften edges by blending wet-into-wet while the paint is open; save your hardest "
                   "edge for the focal point.",
    },
    "watercolor": {
        "surface": "Plan and preserve your whites now — the white of the paper is your lightest "
                   "value and you cannot paint it back later.",
        "value":   "Work strictly light-to-dark in transparent layers, lightest washes first. Judge "
                   "each value only once it has fully dried — watercolour dries lighter than it looks "
                   "wet — and never lay a dark you can't lift back out: hold your deepest, most "
                   "unrecoverable darks back until last.",
        "mixture": "Mix generous dilute washes; test the value on scrap — watercolour dries lighter "
                   "than it looks wet.",
        "edges":   "Control edges by timing: wet-on-wet for soft, wet-on-dry for crisp. A dark laid "
                   "too early is unrecoverable, so commit the deepest darks late.",
    },
    "acrylic": {
        "surface": "A thin toned ground helps, but acrylic dries fast — only tone as much as you can "
                   "work before it sets.",
        "value":   "Pre-mix more than you think you need and work in sections you can finish before "
                   "they set — acrylic dries fast and a shade darker than it looks wet, and won't "
                   "reblend once dry.",
        "mixture": "Keep a wet palette; work in workable sections and glaze thin layers for depth.",
        "edges":   "Blend quickly while wet, or soften afterwards with a thin glaze — you can't move "
                   "dry acrylic the way you move oil.",
    },
    "pencil": {
        "surface": "No ground — but map your value range first so your darkest dark and lightest "
                   "paper are decided before you commit pressure.",
        "value":   "Build value in layered directional strokes; group values into masses rather than "
                   "shading every small change.",
        "mixture": "Your 'mixtures' are pressure and layering — establish 3 value masses before any "
                   "blending.",
        "value_range": "Establish your three value masses now, with a few light swatch patches: the "
                   "white of the paper (lightest), a mid grey, and your darkest dark. Every value you "
                   "lay down afterwards is a layered adjustment between those three anchors.",
        "edges":   "Vary edges with pressure and a blending stump; lift with an eraser for the "
                   "softest transitions and highlights.",
    },
    "charcoal": {
        "surface": "Tone the whole sheet mid-grey with charcoal dust first, then lift the lights out "
                   "with an eraser — you draw in both directions.",
        "value":   "Think in big tonal masses, not lines; compress to a few values and keep the "
                   "darks rich.",
        "mixture": "Blend with a stump for the mid-tones; keep the lightest lights clean by lifting, "
                   "not by leaving paper.",
        "value_range": "Your sheet is already toned mid-grey, so establish the other two masses now: "
                   "lift your lightest lights out of that grey with a kneaded eraser, and block your "
                   "darkest darks with the stick. You're drawing in both directions at once — "
                   "subtracting light, adding dark — from the mid-grey ground.",
        "edges":   "Lost-and-found edges are charcoal's strength — smudge to lose an edge, sharpen "
                   "with a fresh point or eraser to find one.",
    },
    "digital": {
        "surface": "Start on a mid-value background layer, not white, so your value judgements are "
                   "relative to something true.",
        "value":   "Block values on one layer with a large opaque brush; use selections/masks to keep "
                   "masses clean rather than a layer per object.",
        "mixture": "Pick colour from the reference and build a small swatch set; work non-"
                   "destructively so you can correct a mass without repainting.",
        "edges":   "Use a soft brush or a low-opacity eraser for soft edges, a hard brush for the "
                   "focal edge; masks keep edges adjustable.",
    },
}


def _exec(medium: str, key: str) -> str:
    return _MEDIUM_EXEC.get(medium, _MEDIUM_EXEC["oil"]).get(key, "")


def _form_phase_note(medium: str) -> str:
    """Extra process note for the form-modelling step, where the physical
    medium changes how you build form (not just the wording): oil's fat-
    over-lean sequencing and acrylic's glaze-don't-rework habit."""
    if medium == "oil":
        return (" Keep the early, leaner passes thin (more solvent, less oil) and let later, richer "
                "passes go fatter on top — fat over lean — so the paint film dries without cracking; "
                "your darks especially should stay thin.")
    if medium == "acrylic":
        return (" Acrylic won't reblend once it's dry, so once a passage has set, deepen or shift it "
                "with a thin glaze rather than trying to rework it wet.")
    return ""


class _Builder:
    """Accumulates steps and checkpoints with auto-incrementing order/ids."""

    def __init__(self, guidance: Guidance) -> None:
        self.steps: list[LessonStep] = []
        self.checkpoints: list[Checkpoint] = []
        self.guidance = guidance
        self._n = 0

    def checkpoint(self, cp_type: str, title: str, instructions: str) -> str:
        # Autonomy keeps only the two structural gates (silhouette, final).
        if self.guidance == "autonomy" and cp_type not in ("silhouette", "final"):
            return ""
        cid = f"cp_{cp_type}"
        self.checkpoints.append(Checkpoint(
            id=cid, type=cp_type, title=title, instructions=instructions,
            required=cp_type in ("silhouette", "final"),
            accepts=["upload", "confirm"],
        ))
        return cid

    def step(self, *, capability_id: str, phase: str, title: str, objective: str,
             action: str, explanation: str = "", overlays: list[OverlayRef] | None = None,
             tool: str | None = None, mixture: str | None = None,
             completion: CompletionCheck | None = None, mistake: str | None = None,
             stop: str | None = None, checkpoint_id: str | None = None,
             importance: str = "normal") -> None:
        # Granularity: autonomy keeps only pivotal steps; balanced adds the
        # normal ones; full adds the fine "micro" steps too. Same geometry and
        # truth throughout — only how finely it is broken up changes (§1.6).
        if self.guidance == "autonomy" and importance != "pivotal":
            return
        if self.guidance == "balanced" and importance == "micro":
            return
        self._n += 1
        self.steps.append(LessonStep(
            id=f"s{self._n:02d}", capability_id=capability_id, phase=phase,
            order=self._n, title=title, objective=objective,
            explanation=explanation if self.guidance != "autonomy" else "",
            action=action, overlays=overlays or [],
            tool=tool, mixture=mixture, completion_check=completion,
            common_mistake=mistake, stop_condition=stop, checkpoint_id=checkpoint_id or None,
        ))


def _svg_overlay(stage_id: str, region_ids: list[int] | None = None) -> OverlayRef:
    """Points the frontend at the Phase-3 construction SVG for a given stage."""
    return OverlayRef(kind="svg", asset=f"construction:{stage_id}", region_ids=region_ids or [])


def _confirm(criteria: str) -> CompletionCheck:
    return CompletionCheck(kind="confirm", criteria=criteria)


def _upload(criteria: str) -> CompletionCheck:
    return CompletionCheck(kind="upload", criteria=criteria)


def _loc(margins: dict[str, float]) -> str:
    """A plain-language placement note from the subject margins."""
    if not margins:
        return "Match the subject's position in the frame to the reference."
    biggest = max(margins, key=lambda k: margins.get(k, 0))
    if margins.get(biggest, 0) < 0.08:
        return "The subject nearly fills the frame — keep small, even margins."
    return f"The subject sits with the most breathing room on the {biggest}."


def generate_lesson(
    drawing: dict[str, Any] | None,
    value_zones: list[dict],
    palette: list[dict],
    image_brief: dict | None,
    medium: str,
    guidance: Guidance = "balanced",
    assets: dict[str, str] | None = None,
) -> Lesson:
    """Build the full composition-first lesson for one image."""
    assets = assets or {}
    b = _Builder(guidance)
    brief = image_brief or {}
    dr = drawing or {}
    bounds = dr.get("subject_bounds", {})
    margins = bounds.get("margins", {})
    canvas_ratio = dr.get("canvas_ratio")
    n_landmarks = len(dr.get("landmarks", []))
    masses = brief.get("masses", [])
    coverage = brief.get("value_coverage", [])
    focal = brief.get("focal")
    n_values = len(value_zones) or 5

    # ── PHASE A — Composition & placement ─────────────────────────────────────
    cp_place = b.checkpoint("placement", "Placement checkpoint",
                            "Before drawing anything inside the subject, check its size and position "
                            "on the canvas against the reference.")
    if canvas_ratio:
        b.step(
            capability_id="composition", phase="composition", importance="pivotal",
            title="Set the canvas and crop",
            objective=f"Match the reference crop: a canvas of ratio {canvas_ratio:.2f} (width ÷ height).",
            action="Draw the outer rectangle of your canvas at this ratio before anything else.",
            explanation="The crop is a composition decision — fix it now so every proportion you "
                        "measure later is measured against the right rectangle.",
            overlays=[_svg_overlay("canvas")],
            completion=_confirm("Your canvas matches the reference proportions."),
            mistake="Starting on a canvas of the wrong shape, then cramping the subject to fit.",
        )
    b.step(
        capability_id="composition", phase="composition", importance="pivotal",
        title="Place the subject",
        objective="Position the subject in the frame with the same margins it has in the reference.",
        action="Lightly mark the box the subject occupies; leave the margins the reference leaves.",
        explanation=_loc(margins) + (
            "" if bounds.get("source") == "subject_mask"
            else " (Subject detection was approximate here — trust your eye over the guide.)"),
        overlays=[_svg_overlay("placement")],
        completion=_confirm("The subject's size and position match the reference."),
        mistake="Drawing the subject too large or dead-centre so the composition loses its balance.",
        checkpoint_id=cp_place,
    )
    b.step(
        capability_id="drawing_construction", phase="composition",
        title="Mark the four outer limits",
        objective="Fix the top, bottom, left and right extremes of the subject.",
        action="Place a light tick at each of the four limits — the box everything else is measured in.",
        overlays=[_svg_overlay("bounds")],
        completion=_confirm("All four limits sit where they do in the reference."),
        mistake="Guessing the limits instead of measuring — the whole drawing inherits the error.",
    )
    b.step(
        capability_id="drawing_construction", phase="composition",
        title="Find the main axis",
        objective="Establish the dominant direction the subject leans along.",
        action="Draw the single long axis line through the subject; everything hangs off it.",
        overlays=[_svg_overlay("axis")],
        completion=_confirm("Your axis matches the lean of the subject."),
        mistake="Skipping the axis and letting the drawing slowly tilt off-vertical.",
    )

    # ── PHASE B — Drawing & structure (progressive contour) ───────────────────
    cp_prop = b.checkpoint("proportion", "Proportion checkpoint",
                           "Compare the big proportions and negative spaces to the reference before "
                           "you refine a single edge.")
    b.step(
        capability_id="drawing_construction", phase="drawing", importance="pivotal",
        title="Block the simplified envelope",
        objective="Connect the landmarks with a few big straight segments — the envelope, not the final line.",
        action="Draw the coarse straight-sided envelope of the whole subject.",
        explanation="Straight segments are easier to judge and correct than curves. Get the big "
                    "shape right first; the accurate contour comes later.",
        overlays=[_svg_overlay("envelope")],
        completion=_confirm("The envelope captures the big shape with straight segments."),
        mistake="Jumping to detailed curves before the overall shape is correct.",
        stop="Stop before adding any curve or interior line.",
    )
    b.step(
        capability_id="drawing_construction", phase="drawing",
        title="Place the structural landmarks",
        objective=f"Mark the widest and narrowest points and the major corners "
                  f"({n_landmarks} landmarks detected).",
        action="Add the key structural points along the envelope.",
        overlays=[_svg_overlay("landmarks")],
        completion=_confirm("The landmarks line up with the reference."),
        mistake="Placing landmarks by eye without checking them against each other.",
    )
    b.step(
        capability_id="drawing_construction", phase="drawing",
        title="Check the negative spaces",
        objective="Verify the shapes of the spaces AROUND the subject.",
        action="Look at each gap between the subject and the box; correct the outline until the gaps match.",
        explanation="Negative spaces are simpler shapes than the subject, so errors show up faster in them.",
        overlays=[_svg_overlay("negative_space")],
        completion=_confirm("The negative spaces match the reference."),
        mistake="Only ever looking at the object, never the spaces — the classic proportion trap.",
    )
    b.step(
        capability_id="drawing_construction", phase="drawing", importance="pivotal",
        title="Check the proportions",
        objective="Confirm the big proportions before refining.",
        action="Measure height against width and the main divisions; adjust the envelope if they are off.",
        overlays=[_svg_overlay("proportion")],
        completion=_confirm("The proportions match the reference within a small margin."),
        mistake="Refining edges on top of proportions that are already wrong.",
        checkpoint_id=cp_prop,
    )
    b.step(
        capability_id="drawing_construction", phase="drawing", importance="pivotal",
        title="Refine the outer silhouette",
        objective="Turn the straight envelope into the accurate outer contour.",
        action="Replace the envelope segments with the true curves of the silhouette.",
        overlays=[_svg_overlay("silhouette")],
        completion=_confirm("The outer contour is accurate all the way round."),
        mistake="Adding interior detail before the outer shape is finished.",
        stop="Stop before any interior line until the silhouette reads correctly.",
    )
    b.step(
        capability_id="drawing_construction", phase="drawing",
        title="Add the major internal divisions",
        objective="Draw only the largest internal structure — the big planes and form breaks.",
        action="Add the few most important internal lines.",
        overlays=[_svg_overlay("internal_divisions")],
        completion=_confirm("The major internal divisions are placed."),
        mistake="Diving into small detail (features, folds, texture) before the big divisions exist.",
    )
    b.step(
        capability_id="drawing_construction", phase="drawing", importance="micro",
        title="Add secondary structural lines",
        objective="Add secondary structure only where it genuinely helps the drawing read.",
        action="Add the next tier of structural lines, sparingly.",
        overlays=[_svg_overlay("secondary_structure")],
        completion=_confirm("Secondary structure is in, without over-drawing."),
        mistake="Treating every detected edge as a line to draw.",
    )
    cp_draw = b.checkpoint("silhouette", "Drawing checkpoint — before any value",
                           "Compare the whole drawing to the reference — placement, silhouette, "
                           "proportion — and fix the most important error BEFORE you touch value or "
                           "colour. Upload a photo of your drawing for a prioritized correction.")
    b.step(
        capability_id="drawing_construction", phase="drawing", importance="pivotal",
        title="Drawing checkpoint",
        objective="Validate the whole drawing before moving to value.",
        action="Step back, compare to the reference, and correct the single most important structural "
               "error. Then photograph your drawing to check it.",
        explanation="Values and colour painted over a wrong drawing only make the error permanent — "
                    "this is the one checkpoint you must not skip.",
        overlays=[_svg_overlay("checkpoint")],
        completion=_upload("Your drawing's placement, silhouette and proportion match the reference."),
        mistake="Rushing into paint because the drawing is 'close enough'.",
        stop="Do not start value until the drawing is corrected.",
        checkpoint_id=cp_draw,
    )

    # ── PHASE C — Value & painting foundation ─────────────────────────────────
    cp_val = b.checkpoint("values", "Value checkpoint",
                          "Check your value masses read correctly in black and white before colour.")
    b.step(
        capability_id="notan", phase="value",
        title="Prepare the surface",
        objective=f"Set up the surface for {medium}.",
        action=_exec(medium, "surface"),
        completion=_confirm("The surface is ready and you're no longer judging against pure white."),
        mistake="Judging your first values against a blank white surface.",
    )
    if medium == "watercolor":
        # Watercolour is subtractive — the whites are the paper, not paint, and
        # once a wash covers one there is no painting it back. This has to be
        # decided before any light/shadow split, let alone a wash goes down.
        b.step(
            capability_id="notan", phase="value", importance="pivotal",
            title="Reserve the whites",
            objective="Identify and protect every area that must stay paper-white before any wash "
                      "touches the paper.",
            action="Mark every highlight and white area now — with a light pencil line, or masking "
                   "fluid/frisket if you want a hard edge there. Once a wash covers the paper, that "
                   "white is gone for good.",
            overlays=[OverlayRef(kind="value_mask", asset=assets.get("value_zones_map"))],
            completion=_confirm("Every area meant to stay white is marked or masked before the first wash."),
            mistake="Discovering a missed highlight only after a wash has already covered it.",
        )
    dark_frac = brief.get("dark_fraction")
    split_note = ("" if dark_frac is None
                  else f" About {int(dark_frac*100)}% of this image reads as shadow — "
                       "keep that balance.")
    b.step(
        capability_id="notan", phase="value", importance="pivotal",
        title="Separate the biggest light and shadow families",
        objective="Divide the whole subject into just two families: light and shadow.",
        action="Squint until the picture collapses to two values, then map the shadow shape as one mass."
               + split_note,
        overlays=[OverlayRef(kind="value_mask", asset=assets.get("value_zones_map"))],
        completion=_confirm("The shadow family reads as one connected shape."),
        mistake="Chasing individual small darks instead of the one big shadow shape.",
    )
    zone_labels = ", ".join(z.get("label", "") for z in value_zones[:n_values]) or "shadow → light"
    b.step(
        capability_id="notan", phase="value", importance="pivotal",
        title=f"Simplify to {n_values} values",
        objective=f"Resolve the picture into {n_values} clear value steps ({zone_labels}).",
        action=_exec(medium, "value"),
        overlays=[OverlayRef(kind="value_mask", asset=assets.get("value_zones_map"))],
        completion=_confirm("The whole picture reads correctly in these value steps."),
        mistake="Too many half-tones so the value structure turns to mud.",
        checkpoint_id=cp_val,
    )
    if medium in ("pencil", "charcoal"):
        # There is no paint to mix — the equivalent groundwork is deciding the
        # value range itself, so this step replaces "mixtures" rather than
        # reusing its wording.
        b.step(
            capability_id="notan", phase="value",
            title="Set your value range",
            objective="Establish 3 value masses — your lightest light, midtone and darkest dark — "
                      "before rendering any single form.",
            action=_exec(medium, "value_range"),
            completion=_confirm("Your three value masses are established before you refine any single area."),
            mistake="Rendering one area to a finish before the overall value range is decided.",
        )
    else:
        mixture_names = ", ".join(p.get("name", "") for p in palette[:6]) if palette else ""
        b.step(
            capability_id="color_palette", phase="value",
            title="Prepare the working mixtures",
            objective="Mix the main colour strings you'll paint with.",
            action=_exec(medium, "mixture") + (f" Your main colours: {mixture_names}." if mixture_names else ""),
            mixture=mixture_names or None,
            completion=_confirm("Your main mixtures are ready before you start blocking colour."),
            mistake="Mixing every colour from scratch on the canvas, so nothing stays consistent.",
        )
    if masses:
        first = masses[0]
        b.step(
            capability_id="color_by_number", phase="colour", importance="pivotal",
            title="Place the largest colour masses",
            objective="Block in the biggest masses flat, in the right value and colour.",
            action=f"Start with the largest mass — the {first.get('colour_name','main')} "
                   f"{first.get('value_label','')} in the {first.get('location','picture')} — and cover "
                   "the canvas with flat masses before any blending.",
            overlays=[OverlayRef(kind="colour_regions", asset=assets.get("colours"))],
            completion=_confirm("Every area is covered with a flat mass — no white canvas showing."),
            mistake="Rendering one corner to a finish while the rest is bare — you can't judge colour "
                    "relationships against white.",
        )

    # ── PHASE D — Form & modelling ────────────────────────────────────────────
    cp_col = b.checkpoint("colour_masses", "Colour-mass checkpoint",
                          "Check the big colour and temperature relationships before you model form.")
    b.step(
        capability_id="color_by_number", phase="form",
        title="Model the form",
        objective="Add the halftones and transitions that turn flat masses into form.",
        action="Work the transitions between light and shadow; separate form shadow from cast shadow "
               "where the reference shows it." + _form_phase_note(medium),
        completion=_confirm("The main forms read as solid, not flat."),
        mistake="Blending everything smooth so the form goes soft and the drawing is lost.",
    )
    warm, cool = brief.get("warmest_colour"), brief.get("coolest_colour")
    temp_note = (f" This image's warmest note is {warm} and its coolest is {cool} — judge temperature "
                 "against those, not against a rule." if warm and cool else
                 " Judge each temperature shift against the reference, not against a fixed rule.")
    b.step(
        capability_id="color_temperature", phase="form", importance="pivotal",
        title="Refine local colour and temperature",
        objective="Adjust the colour and temperature relationships to match the reference.",
        action="Refine each mass's hue and temperature against its neighbours." + temp_note,
        completion=_confirm("Colour and temperature relationships match the reference."),
        mistake="Applying 'warm light, cool shadow' as a law when this image does something else.",
        checkpoint_id=cp_col,
    )

    # ── PHASE E — Edges & completion ──────────────────────────────────────────
    focal_loc = focal.get("location") if focal else None
    b.step(
        capability_id="composition", phase="edges", importance="pivotal",
        title="Identify the focal area",
        objective="Decide where the eye should land first.",
        action=(f"Commit to the focal area (the reference's is around the {focal_loc}) and plan to keep "
                "your sharpest, highest-contrast note there." if focal_loc
                else "Commit to one focal area and plan your sharpest note there."),
        completion=_confirm("You've chosen a single focal area."),
        mistake="Letting two areas compete so the eye doesn't know where to go.",
    )
    b.step(
        capability_id="edge_coach", phase="edges", importance="pivotal",
        title="Establish the edge hierarchy",
        objective="Set hard, soft and lost edges so sharpness leads the eye.",
        action=_exec(medium, "edges"),
        overlays=[OverlayRef(kind="edge_guides", asset=assets.get("edges"))],
        completion=_confirm("The hardest edges cluster on the focal point; edges soften away from it."),
        mistake="Equal-sharpness edges everywhere, so nothing is emphasised.",
    )
    b.step(
        capability_id="edge_coach", phase="edges", importance="micro",
        title="Reduce unnecessary edges",
        objective="Lose the edges that don't earn their place.",
        action="Soften or drop edges in the shadows and away from the focal area.",
        completion=_confirm("Only the edges that lead the eye remain crisp."),
        mistake="Keeping every edge because it's 'there' in the reference.",
    )
    b.step(
        capability_id="drawing_construction", phase="detail", importance="micro",
        title="Add selected details",
        objective="Add only the details that serve the focal point.",
        action="Place your small detail on and near the focal area; leave the rest implied.",
        completion=_confirm("Detail is concentrated where the eye lands, not spread evenly."),
        mistake="Detailing everywhere, which flattens the focal hierarchy you just built.",
    )
    cp_final = b.checkpoint("final", "Final checkpoint",
                            "Photograph the finished painting and upload it for a prioritized "
                            "correction against the reference.")
    b.step(
        capability_id="critique", phase="detail", importance="pivotal",
        title="Final accents, then check your work",
        objective="Add the final accents and highlights, then compare to the reference.",
        action="Place the lightest lights and darkest darks last, on the focal point. Then photograph "
               "the painting and upload it for feedback.",
        completion=_upload("The finished painting matches the reference in structure, value and colour."),
        mistake="Adding highlights everywhere instead of saving them for the focal accent.",
        checkpoint_id=cp_final,
    )

    return Lesson(
        id="lesson_v2", capability_id="lesson_plan", medium=medium,
        guidance=guidance, steps=b.steps, checkpoints=b.checkpoints,
    )
