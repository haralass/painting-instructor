# Phase 4 — Implementation Note (Lesson Engine)

> **STATUS (2026-07-13): COMPLETE.** Shipped on `feature/phase1-foundations`
> (commits `5f6921a…f74da39`); 287 backend + 13 frontend tests green,
> `next build` clean, live-verified. `teaching/lesson_engine.py` generates
> the composition-first `Lesson` (manifest.lesson + lesson.json); the new
> `GuidedLessonPlayer` plays it with construction/asset overlays on the
> Phase-2 viewer, checkpoint gates, and per-step progress persisted via the
> project store (new `GET /projects/by-job/{job_id}`). Registry declares
> lesson mode on the 8 taught capabilities. Verified: 24-step lesson,
> drawing checkpoint before values, marking steps persists to the backend.
> Deferred: the actual upload-critique alignment against the drawing/values
> is Phase 6; user landmark editing and local-crop child lessons remain open.

Turns the Phase-3 drawing analysis + the existing value/colour/edge/brief
signals into a real, generated `Lesson` (the Phase-1 `schemas/lesson.py`
contract): a composition-first sequence with a drawing checkpoint before
values, the progressive contour lesson, and per-step objective / action /
completion-check / common-mistake / stop-condition.

## What already exists (reused)

- `schemas/lesson.py` — `Lesson`, `LessonStep`, `Checkpoint`, `OverlayRef`,
  `CompletionCheck` (Phase 1). The engine only *fills* these.
- `analysis/drawing.py` → `drawing.json` — bounds, landmarks, envelope,
  silhouette, internal paths, construction order (Phase 3).
- `teaching/planner.py:build_image_brief` — masses, block-in order, focal,
  busy areas, value coverage, warm/cool anchors.
- value zones, palette + `teaching/mixing.py` recipes, edge hierarchy.

## New this phase

**`backend/teaching/lesson_engine.py`** — `generate_lesson(drawing, value_zones,
palette, image_brief, medium, guidance, assets)` → `Lesson`. Structure
(brief §6), grounded per-image:

- **Phase A composition** — crop/ratio, subject placement + margins, the four
  limits, main axis. `Checkpoint: placement`.
- **Phase B drawing** — envelope → landmarks → negative-space → proportion
  (`Checkpoint: proportion`) → refined silhouette → internal divisions →
  secondary structure → **drawing `Checkpoint: silhouette` before any value
  (§2.G)**. This is the progressive contour lesson (§8).
- **Phase C value foundation** — medium surface prep, split biggest light/
  shadow families, simplify to N values (`Checkpoint: values`), prepare
  working mixtures, place largest colour masses.
- **Phase D form** — halftones, form vs cast shadow, local-colour/temperature
  (`Checkpoint: colour_masses`).
- **Phase E edges/completion** — focal area, hard/soft/lost edges, reduce
  edges, selected detail, final accents, upload for prioritized correction
  (`Checkpoint: final`).

Overlays reference real geometry: drawing-phase steps point at construction
stages (`overlay.kind="svg"`, asset `construction:<stage_id>`) so the
frontend reuses the Phase-3 SVG builder; value/colour/edge steps point at
existing manifest assets.

**Guidance** (from skill level: beginner→full, intermediate→balanced,
advanced→autonomy) changes step granularity + checkpoint count + explanation
depth — never the geometry or the truth of the image (§1.6).

**Medium** changes execution notes (oil imprimatura/fat-over-lean, watercolour
preserve-whites/light-to-dark, acrylic premix/timing, pencil/charcoal
mark-making, digital selections) — the drawing phases stay medium-agnostic
(drawing is drawing).

## Wiring

`pipeline.py` returns the drawing dict; `tasks.py` calls the engine, writes
`lesson.json`, adds `manifest.lesson`. Registry: `drawing_construction`,
`notan`, `color_by_number`, `edge_coach`, `composition` gain the `lesson`
mode where the engine now teaches them; a `guided_lesson` capability already
covers the whole. The legacy medium-stage `lesson_plan` stays for the old
LessonPlayer until the new player fully replaces it.

## Frontend

New structured lesson player: walks `Lesson.steps`, renders each step's
overlay (construction SVG for drawing phase; asset image for value/colour/
edge), shows objective/action/mistake/stop, gates checkpoints, and persists
per-step completion + checkpoint state via the Phase-1 `/projects/{id}/
progress` + `/checkpoints` endpoints.

## Non-goals (later)

Progress critique against the drawing/values (Phase 6 — the "Check" upload
does the alignment there); user landmark editing; local-crop child lessons.

## Commits

1. engine + note · 2. pipeline/manifest/registry + tests · 3. frontend
player + progress persistence · 4. verify + docs.
