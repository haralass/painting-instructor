# Phase 1 — Implementation Note

> **STATUS (2026-07-12): COMPLETE.** All items below shipped on
> `feature/phase1-foundations` (commits `9e2f308…a324507`); full suite 268
> passed, `next build` clean, live-verified in the browser (landing =
> gallery = workspace = 14 studies from the registry, "Full Detail"
> everywhere, resume-from-disk works without Redis). Extra fix found during
> verification: `GET /jobs/{id}` now completes from the on-disk manifest, so
> saved projects reopen after the Celery result expires. Remaining Phase-1
> non-goals move to Phase 2+ as planned; Phase 2 (viewer) starts next.
>
> **PHASE 2 — STARTED (commit `991674b`).** Shipped: OpenSeadragon viewer in
> Explore Layers (zoom/pan/fit/100%/flip/minimap, aligned overlay images with
> live opacity) and region click-select against the existing merge tree via
> new per-level RGB-encoded label maps + regions.json (verified live:
> click → region → value family / colour family / area / parent mass).
> **PHASE 2 CONTINUED (commit `d6840f1`).** Shipped: single coordinate
> module `app/lib/imageCoords.ts` (+13 vitest round-trip tests, `npm test`);
> full control row + keyboard shortcuts (+ − 0 1 F H Esc); region hover
> highlight + click/Shift-click multi-selection with mask overlays in image
> coordinates; hierarchy breadcrumb with clickable parent/children; view
> modes Reference / Overlay / Before-After split / synced Side-by-Side on
> one shared viewer; viewport persisted per project; OSD container-leak fix.
> Remaining Phase 2: rectangle/polygon/lasso free selection + refinement,
> "analyse this area" local re-analysis of the full-res crop (backend
> endpoint + child-project mounting), SVG vector overlays where PNG masks
> fall short, restoring compare mode from project state (currently
> localStorage viewport only). Known dev-only noise: StrictMode's
> first-mount teardown logs an OSD drawer assert.

Companion to `REDESIGN_AUDIT.md`. Brief by design; the audit holds the rationale.

## Files / modules

**New (backend):** `backend/capabilities.py` (registry + step info + detail
levels + migration map) · `backend/schemas/lesson.py` (Lesson / LessonStep /
Checkpoint) · `backend/projects/store.py` (sqlite3 project state) ·
`scripts/generate_frontend_contract.py` · tests `test_capabilities.py`,
`test_contract_drift.py`, `test_projects.py`, `test_lesson_schema.py`.

**New (frontend):** `frontend/app/lib/contract.generated.ts` (checked-in,
generated — capabilities, page labels, step labels/stages, level labels,
medium fallbacks).

**Changed:** `api/main.py` (+`/capabilities`, `/projects*`) ·
`workers/tasks.py` (steps read registry; classic PBN/dot-to-dot removed;
video sources colour blocking from hierarchy PBN) · `analysis/renderer.py`
(level-5 label) · `app/page.tsx` (tiles/levels/mediums from contract;
Advanced disclosure; resume strip) · `app/gallery/page.tsx` (from contract) ·
`results/[jobId]/lib/manifest.ts` (re-export contract; drop hand catalogues)
· `results/[jobId]/page.tsx` (h-screen shell, video/observations demoted).

**Deleted:** `backend/pipeline/color_by_number/`, `backend/pipeline/dot_to_dot/`,
`backend/pipeline/pixel_grid/`, `backend/pipeline/journaling/` (dead/duplicated);
`OIL_FALLBACK` in `page.tsx`; hand-maintained `PAGE_LABELS` /
`CLASSIC_PAGE_KEYS` / `STEP_LABELS` / `STEP_STAGE` / `LEVEL_LABELS`.

## Registry schema (essence)

```
Capability{ id, name, category(analysis|coaching|exercise|deliverable|internal),
  description, why, tip, implemented, advertised, workspace,
  modes{study,lesson,check}, supports{local_region,manual_correction,checkpoint},
  outputs[{kind,key}], pipeline_step?, sample?, replaces[] }
StepInfo{ step → pct, message, loading_stage }     # single source for progress
DetailLevel{ level, label, description, regions_hint }
```

`/capabilities` returns all three. `tasks.py` `_PROGRESS`+messages and the
generated TS both derive from `STEP_INFO`, so backend and frontend cannot
drift independently. Drift test regenerates the TS and diffs against the
committed file.

## Capability migration table

| Old id / surface | Decision | New id | Compatibility |
|---|---|---|---|
| `color_by_number` (classic BiSeNet generator) | **retire generator, keep id** | `color_by_number` (hierarchy render only — already writes the same `color_by_number.png`) | none: filename, manifest key, page id unchanged |
| `dot_to_dot` (classic skeleton generator) | **retire generator, keep id** | `dot_to_dot` (hierarchy smart dots — already overwrote the same PNG) | none: filename/id unchanged; old manifests still resolve |
| `pixel_grid`, `journaling` | **delete** (dead code, zero references) | — | none |
| `value_zones.png` (hierarchy value map) | **keep, mark internal** | `value_zones` (internal; lesson asset) | never advertised; `notan` stays the user-facing values study |
| notan / level-N values | **keep both** | — | different roles (study vs per-level mass render); documented, not merged in Phase 1 |
| Landing tile "Tutorial Video & PDF" | **retire as study** | `video`, `pdf` (category `deliverable`) | display-only change |
| Level-5 label "Full Reference" | **rename** | label **"Full Detail"** | old manifests store the old label string; frontend renders labels by level *number* from the contract, so old jobs display correctly |
| `OIL_FALLBACK` (frontend copy) | **replace** | generated `MEDIUM_FALLBACKS` | fallback only; live fetch unchanged |

Persisted identifiers (page stems, manifest keys, `outputs/` filenames) are
all preserved. Nothing renames on disk.

## Project-state schema (sqlite, stdlib `sqlite3`, WAL, at `outputs/projects.db`)

```
projects(id PK, job_id UNIQUE, title, reference_path, medium, skill_level,
         value_zones, settings_json, current_capability, created_at, updated_at)
lesson_progress(project_id, step_id, status, data_json, updated_at,
                PK(project_id, step_id))
checkpoints(id PK, project_id, type, status, data_json, created_at, updated_at)
corrections(id PK, project_id, capability_id, data_json, created_at)
attempts(id PK, project_id, checkpoint_id?, path, critique_json, created_at)
```

Created transparently by `POST /jobs/`; critique uploads record attempts.
Endpoints: `GET /projects`, `GET /projects/{id}`, `PATCH /projects/{id}`,
`POST /projects/{id}/progress`. Landing gains a "Continue" strip.

## Lesson / checkpoint schema (pydantic, `backend/schemas/lesson.py`)

`LessonStep{ id, capability_id, phase(composition|drawing|value|colour|form|
edges|detail), order, title, objective, explanation, action, region_ids,
overlays[{kind,asset,region_ids}], tool?, mixture?, completion_check{kind,
criteria}?, common_mistake?, stop_condition?, checkpoint_id?, depends_on[] }`
· `Checkpoint{ id, type(placement|silhouette|proportion|values|colour_masses|
edges|final), title, instructions, required, accepts[] }` ·
`Lesson{ id, capability_id, medium, guidance, steps[], checkpoints[] }`.
Schemas + tests only; no generation engine in Phase 1.

## Tests to add

Registry invariants (unique ids; workspace capabilities have image outputs;
pipeline_step ∈ STEP_INFO; advertised capabilities have existing sample
assets) · contract drift (regenerate == committed) · project store CRUD +
progress/checkpoint/attempt round-trips · lesson schema validation · updated
`test_analysis.py` / `test_integration.py` after generator retirement.

## Non-goals (Phase 1)

No lesson-generation engine, no critique changes, no region-algorithm
changes (merge tree untouched; `region_complexity` stays in the API/debug
path, only hidden from the normal form), no SAM/new ML models, no visual
redesign, no OpenSeadragon (that is Phase 2, started only after Phase 1 is
green).
