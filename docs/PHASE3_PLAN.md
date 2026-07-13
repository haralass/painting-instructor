# Phase 3 — Implementation Note (Structured Drawing Analysis)

Builds on Phase 1 (registry, schemas, project store) and Phase 2 (viewer,
coordinate system, region selection). Goal: turn the existing edge/region/
depth/subject signals into a **stored, structured account of how the drawing
is constructed** — not another PNG filter.

## What already exists (reused, not rebuilt)

- `analysis/edges.py` — classified `Edge` paths (primary/secondary/decorative/
  texture) with region context, strength, importance. **This is the contour
  source; Phase 3 does not re-run edge detection.**
- `analysis/regions.py` — the stable merge tree (bbox, centroid, area,
  importance, parent_id, scale).
- `analysis/subject.py` — U²-Net foreground mask (float [0,1]).
- `analysis/depth.py` — depth planes (0=far…2=near).
- value zones + `cache` (L*, gradient, lab).

## New this phase

**`backend/schemas/drawing.py`** — pydantic models: `DrawingAnalysis`,
`Landmark`, `Axis`, `VectorPath`, `NegativeSpace`, `Envelope`, `ProportionCheck`,
`ConstructionStage`. Coordinate space = analysis pixels (same grid as
`regions.json` / label maps; the frontend rescales to the original via the
Phase-2 `imageCoords` utilities). Envelope is stored **separately** from the
refined silhouette so the progression is preserved.

**`backend/analysis/drawing.py`** — `build_drawing_analysis(...)` computes, from
the untouched-reference-derived signals only:
1. canvas ratio + subject bounds + margins (subject mask, region fallback),
2. top/bottom/left/right limits + widest/narrowest → landmarks,
3. main occupied-area hull, main axis (PCA), dominant slopes (primary-edge
   orientation clustering),
4. simplified **envelope** (coarse approxPolyDP) → refined **silhouette**
   (fine approxPolyDP), stored as distinct paths,
5. negative spaces (bbox ∩ ¬subject components),
6. proportion references (thirds along the axis),
7. internal divisions (primary edges inside subject) + secondary structure,
8. **edge-cause estimates** per path from depth/value/chroma diffs — soft
   scores + a confidence, never a hard claim,
9. a pedagogical `construction_order` (NOT left-to-right / shortest-first).

**Pipeline wiring** — `analysis/pipeline.py` calls it after the hierarchy
(edges + regions + subject already in hand), writes `drawing.json`, and the
manifest gains a `drawing` block. Registry gets a `drawing_construction`
capability (Study now; Lesson/Check are Phase 4/6).

**Frontend** — a "Construction" study in the explorer that steps through
`bounding limits → landmarks → envelope → refined silhouette → internal
structure` as SVG overlays on the Phase-2 viewer, with the contextual right
panel explaining each stage. Guidance level changes how many landmarks /
sub-steps show — never the geometry.

## Non-goals (later phases)

Full lesson-step generation + checkpoints (Phase 4), medium-specific
execution (Phase 5), progress critique against the construction (Phase 6),
user correction of landmarks (Phase 4 editing). No new ML model; no
user-facing CV parameters; no layer panel.

## Commits

1. models + this note · 2. analysis module + pipeline + manifest + tests ·
3. edge-cause attribution · 4. frontend construction view · 5. verify + docs.
