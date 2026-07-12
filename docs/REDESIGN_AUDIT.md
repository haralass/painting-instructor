# Redesign Audit — Painting Instructor → Interactive Painting Teacher

Date: 2026-07-12 · Audited at commit `31787ff` (main, clean tree)
Scope: required pre-implementation audit (brief §23) before the "interactive
instructor" redesign. No code was changed in this pass.

---

## 1. Current frontend architecture

Next.js 16 (App Router, Turbopack), TypeScript, Tailwind, GSAP. Three routes:

- **`app/page.tsx` (757 lines)** — marketing landing + the entire setup form in
  one client component. Scroll choreography (GSAP), `EvolvingCanvas` /
  `ArtTile` / `AtelierHero` procedural graphics, live medium-stage fetch from
  `/mediums/{id}` with a hard-coded `OIL_FALLBACK` copy of the backend oil
  config. The form posts multipart to `POST /jobs/` and redirects to
  `/results/{job_id}`.
- **`app/gallery/page.tsx` (169 lines)** — static showcase of 11 committed
  sample JPGs under `public/samples/demo1/`. Its study list is a third,
  hand-maintained copy of the study catalogue.
- **`app/results/[jobId]/` (~2 100 lines)** — the workspace. `useJobPolling`
  polls `GET /jobs/{id}` then fetches `manifest.json`. Six view modes switched
  by buttons: Lesson (`LessonPlayer`), Explore Layers (`HierarchicalControls`
  + `ImageDisplay`), Build up (`ProgressiveReveal`), Squint
  (`SquintSimulator`), Classic Analysis (thumbnail list of PNG pages),
  Critique (`CritiquePanel`). `lib/manifest.ts` holds types plus **four more
  hand-maintained catalogues** (`PAGE_LABELS`, `CLASSIC_PAGE_KEYS`,
  `STEP_LABELS`, `STEP_STAGE`) that must be kept in sync with backend step
  names by hand — this exact class of bug shipped four times (PRs #15–#17).

Image display is stacked `<img>` elements with CSS opacity
(`ImageDisplay.tsx`, 92 lines). There is **no pan/zoom viewport, no SVG
overlay layer, no region selection**. `InspectLoupe.tsx` is a canvas
magnifier for point sampling only. Layout is a real three-column
app-shell (left nav / centre / `TeachingAside` right), but the centre column
stacks observations + video + slider controls + image into one long scroll.

## 2. Current backend architecture

FastAPI (`api/main.py`, 316 lines) + Celery/Redis. Endpoints: `POST /jobs/`,
`GET /jobs/{id}`, `POST /jobs/{id}/critique`, `GET /jobs/{id}/pdf`,
`GET /brands`, `GET /mediums[/{id}]`. Static `/outputs` mount serves all
artefacts.

Everything else lives in **one 790-line Celery task**
(`workers/tasks.py:run_pipeline`): loading, ~15 study generators (6 run in a
thread pool), the hierarchical analysis, lesson-plan build, LLM observations
(optional, keys off `ANTHROPIC_API_KEY`), video, PDF, manifest. **Celery's
result backend is the job store** — there is no database, no project entity,
no lesson-progress state. `manifest.json` per job directory is the de-facto
data model. The adaptive painter profile is flat JSON under
`outputs/profiles/{user}/` keyed by a localStorage id.

## 3. Current image-analysis pipeline

Per job: U²-Netp subject mask (bundled ONNX) → Depth-Anything-V2-vits planes
(bundled ONNX) → six parallel classic studies (line art, notan, colour
temperature, K-means palette, light direction, paint-by-numbers) → six
coaching studies (subject focus, depth planes, local-vs-light Retinex split,
value traps, edge coach, composition/focal competition) → skeleton-traced
dot-to-dot → **hierarchical analysis** (`analysis/pipeline.py`): value zones,
MiniBatchKMeans colour families, **single SLIC base + agglomerative merge
tree** cut at 5 levels (`regions.py`), classical edge extraction bucketed
into primary/secondary/decorative/texture with per-level ancestor filtering
(`edges.py`), LUT renders of outlines/values/colours/regions per level
(`renderer.py`), hierarchy-based paint-by-numbers + study overlay + smart
dot-to-dot → image brief (`teaching/planner.py`) → 36-band spectral
Kubelka-Munk mixing recipes (`teaching/mixing.py` + `analysis/spectral.py`,
real brand tube DBs) → Im2Oil-style stroke video → PDF book.

All outputs are computed on a resized working copy; the original upload is
copied untouched to `outputs/{job}/reference.{ext}` and the workspace does
display it (compare modes). ~29 s wall clock per job on this machine.

## 4. Current data models

Pydantic models in `analysis/models.py` (`Region`, `Edge`, `ColourFamily`,
`ValueZone`, `DetailLevel`, `MediumStrategy`) serialised to
`regions.json` / `edges.json` / `edges.svg` per job — regions carry
`parent_id`, `scale`, `value_zone`, `colour_family_id`, `importance`,
centroid and area, so a real hierarchy **is** stored as structured data.
`schemas/jobs.py` holds API DTOs. The manifest embeds detail levels, palette
(with mixing recipes), colour families, value zones, lesson plan,
image brief, timings and truncated errors. There is **no capability
registry, no project/lesson-progress model, and no checkpoint model.**

## 5. Current lesson-generation logic

`teaching/mediums/*.py` — six static per-medium configs of exactly 6 stages
(oil: toned ground → block-in → value masses → colour modelling → edge
refinement → detail), each naming `analysis_layers`.
`teaching/lesson.py:build_lesson_plan` resolves those keys against generated
assets; skill level only prepends a value warm-up (beginner) or appends a
self-critique step (advanced); the adaptive profile adds emphasis /
watch-outs / a session goal. `teaching/planner.py` derives a genuinely
per-image brief (masses with location/value/colour/size, block-in order,
light direction, focal area, busy areas) and ordered `image_micro_steps`
with mix hints.

**The teaching sequence starts at painting.** There is no Phase A/B at all —
no crop/placement step, no envelope, no silhouette, no landmark or proportion
teaching, no checkpoint gating drawing before values (brief problems E, F,
G). Lesson progress ("step 3 of 6 done") exists only as ephemeral component
state; nothing gates or records completion.

## 6. Inconsistency between landing, gallery, workspace, backend

Four hand-maintained catalogues that already disagree:

| Surface | Count | Source | Notes |
|---|---|---|---|
| Landing `ANALYSIS_TILES` | **14** | hard-coded in `page.tsx` | previews are **procedural fake graphics** (`ArtTile` modes), not real outputs; "Tutorial Video & PDF" listed as a study |
| Gallery `STUDIES` | **11** | hard-coded, static JPGs | missing dot-to-dot, study overlay, video/PDF; its one sample reference is a photo-of-a-screen |
| Workspace `CLASSIC_PAGE_KEYS` | **15** | `lib/manifest.ts` | includes `study_overlay`, which neither landing nor gallery mention; is an *active filter* — anything missing from it silently disappears (bug class shipped 4×) |
| Backend | ~17 steps | `_PROGRESS` dict + pipeline code | plus 5×4 hierarchy renders, video, PDF |

Also duplicated across the boundary: `OIL_FALLBACK` (verbatim copy of
`mediums/oil.py`), `STEP_LABELS`/`STEP_STAGE` vs `_PROGRESS` messages,
`LEVEL_LABELS` vs `_LEVEL_LABELS`.

## 7. Feature classification

**Real and good (keep):**
- SLIC + merge-tree hierarchy — contrary to the brief's assumption (§2.I),
  levels are already **nested cuts of one merge tree**, not independent
  re-segmentations; boundaries are stable across levels. What's missing is a
  semantic layer (Background/Figure/Head), vector paths, and stopping the
  `region_complexity` knob from rebuilding the tree.
- 36-band spectral Kubelka-Munk mixing + real brand tube DBs — physically
  honest, our own implementation.
- Critique alignment chain (canvas-corner rectify → ORB homography → resize
  fallback, with confidence) + 6 signed metrics + adaptive painter profile.
- Subject mask (U²-Netp) and depth planes (Depth-Anything-V2-vits), bundled
  ONNX, CPU-fast.
- Image brief + micro-steps (per-image, deterministic).
- Stroke-by-stroke video renderer; PDF book; value zones; edge
  type-bucketing with per-level persistence filtering.

**Partial:**
- Lesson plan — real assets and per-image notes attached to **static 6-stage
  templates that begin at painting**; no drawing phase, no checkpoints, no
  per-step completion checks or stop conditions.
- Edge hierarchy — persistence + strength based (good) but purely
  photometric; no depth/reflectance/illumination cause attribution despite
  both signals existing in the pipeline.
- Critique — good alignment and metrics, but grid-cell based; it cannot say
  "the figure is too narrow" (no silhouette/placement/proportion
  comparison) and returns a flat feedback list rather than one prioritized
  correction.
- Regions view — a decorative recolour, not the interactive clickable map of
  §12 (the data to support clicking exists in `regions.json`).

**Static / misleading:**
- Landing tiles: procedural graphics presented as product output.
- Level 5 labelled **"Full Reference"** but rendered as quantized LUT
  colours/values — misleading name (the *actual* original is preserved and
  shown separately, so brief §2.D/J is a labelling fix, not a data fix).
- "Structural Dots" description ("most structurally significant edges") —
  the generator is a real skeleton-tracer, but the dots are not structural
  landmarks; naming conflates two different features (§14).
- Local Colour vs Light — a real Retinex/bilateral split presented without
  labels for illumination/shading/uncertainty; overclaims (§16).
- "Warm lights, cool shadows", "10% detail", fixed brush advice — asserted
  universally in medium configs and PAGE_LABELS (§2.H).

**Duplicated:**
- Two dot-to-dots (classic skeleton + hierarchy "smart"), two
  paint-by-numbers (classic BiSeNet/RAG + hierarchy render) with
  replace-if-exists logic; three unrelated value renderings (notan page,
  `value_zones.png`, per-level values); `palette` vs `colour_families` both
  derived from the same K-means but surfaced inconsistently; the four
  frontend catalogue copies above.

**Broken / risky:**
- Gallery sample set is a photo-of-a-screen (known).
- Classic `color_by_number` depends on optional heavy ML (facexlib/BiSeNet)
  and silently degrades.
- Setup form exposes implementation jargon: superpixel-seeded "region
  complexity" slider, texture/background edge toggles, raw 6–32 palette
  slider (§4).

## 8. Code to reuse (as-is or near)

`analysis/regions.py` (merge tree), `values.py`, `colours.py` (as the
*observed-families* input, renamed), `spectral.py`, `teaching/mixing.py`,
`paint_brands.py`, `subject.py`, `depth.py`, `critique/engine.py` alignment +
metrics, `critique/profile.py`, `planner.py` brief/micro-steps,
`pipeline/stroke_paint/`, `pdf_book.py`, the visual identity (globals.css,
AtelierHero, panels, typography), LoadingScreen/EvolvingCanvas.

## 9. Code to refactor

- `workers/tasks.py` — split into analysis-job vs. extras-job (video/PDF
  become on-demand); progress steps come from the capability registry.
- `teaching/mediums/*` — from 6 static stages to medium *execution logic*
  feeding the new lesson engine (phase graph, per-medium constraints like
  whites-preservation, fat-over-lean, premixing).
- `results/[jobId]` — keep the shell; replace `ImageDisplay` with the real
  viewer; make the right panel fully contextual; remove mode buttons that
  are really lessons.
- `critique/engine.py` — add silhouette/placement/proportion comparison on
  top of the existing alignment; emit one prioritized correction (structure
  → values → colour → edges), keep the rest as "later" items.
- Palette presentation — split into observed families / value families /
  tube palette / working mixtures / region usage (the data already exists;
  merge perceptually-close clusters with ΔE before display).

## 10. Code to replace or delete

- The four frontend catalogues + `OIL_FALLBACK` → generated from one backend
  capability registry.
- Classic BiSeNet paint-by-numbers and classic dot-to-dot → delete (the
  hierarchy versions supersede them); heavy optional ML deps
  (controlnet_aux, facexlib, rembg-as-import) drop out of requirements.
- CSS-stacked `ImageDisplay` → real viewer (below).
- "Structural Dots" → landmarks feature + real numbered dot-to-dot exercise
  with difficulty levels (§14) built from the edge/contour paths.
- Level-5 "Full Reference" render → the level is the original photo;
  quantized renders remain as levels 1–4 bases + overlays.
- Landing `ANALYSIS_TILES` fake previews → real capability cards using the
  gallery's sample assets.

## 11. Recommended stack per subsystem

- **Viewer/overlay (Phase 2):** OpenSeadragon (BSD-3) + its SVG overlay for
  zoom/pan/minimap/flip/synced views over plain (non-tiled) images, with
  **Annotorious v3** (BSD-3) for rectangle/polygon/lasso selection. Rationale:
  proven combo, no GPU, works with our single-image case, and Annotorious has
  a maintained SAM plugin path. Alternative `react-zoom-pan-pinch` rejected:
  no annotation model, we'd rebuild selection from scratch.
- **Click-to-select segmentation:** SAM2.1-hiera-tiny (Apache-2.0) decoder in
  onnxruntime-web, encoder run once per image server-side (CPU ~1–2 s) — or
  defer entirely and ship superpixel/region-tree click-select first (zero new
  deps; the merge tree already answers "what region is here" at every level).
  Recommendation: **tree-click first, SAM2 as an upgrade**.
- **Semantic grouping for the hierarchy:** subject mask + depth planes we
  already compute, used as *must-not-merge constraints* in the existing merge
  tree; no new model required for v1.
- **Edges:** keep classical extraction; add cause attribution from signals we
  already have (depth gradient → depth edge, Retinex albedo gradient →
  reflectance edge, shading gradient → illumination edge). TEED (MIT, ~58 K
  params, CPU-fast) optional later for boundary strength; RINDNet/EDTER
  rejected (heavy torch, stale, GPU-oriented).
- **Contours/paths/landmarks:** OpenCV `findContours` on region masks +
  Douglas-Peucker / `shapely` simplification → ordered SVG paths with region
  ownership; corner/curvature extrema → landmarks; this also feeds
  dot-to-dot point placement (dense on curvature, sparse on straights).
  vtracer/diffvg/LIVE/CLIPasso rejected — art-style vectorisers or GPU
  research code, wrong tool for measured teaching paths.
- **Colour:** keep colour-science + our spectral K-M. **mixbox rejected** (CC
  BY-NC — commercial risk, and we already have physically-grounded mixing).
- **Progress alignment:** keep the existing rectify→ORB chain; LightGlue
  (Apache) only if real-world failure rate demands it. RoMa rejected (heavy).
- **Persistence:** SQLite via SQLModel (stdlib-adjacent, zero-ops) for
  Project / LessonState / Checkpoint / Attempt; outputs dir stays the blob
  store. Celery result backend stops being the source of truth.
- **Capability registry:** one Python module → `GET /capabilities` → a
  checked-in generated TS file consumed by landing, gallery, workspace.

## 12. Licence and compatibility risks

- mixbox CC BY-NC — do not adopt.
- ArtistAssistApp (AGPL) and Im2Oil (no licence) — already reimplemented, not
  copied; keep it that way.
- Depth-Anything-V2: **Small is Apache-2.0; Base/Large are CC BY-NC** — stay
  on Small.
- facexlib BiSeNet weights: research-grade provenance — removing the classic
  paint-by-numbers eliminates this.
- SAM2, LightGlue, TEED, OpenSeadragon, Annotorious, SQLModel — permissive,
  no issue. All recommended pieces run CPU/Apple-Silicon.

## 13. Staged implementation plan

Each phase is independently shippable and keeps the test suite green.

**Phase 1 — Consistency & foundations.** Capability registry (backend module
+ endpoint + generated TS) replacing all four frontend catalogues and the
gallery/landing lists; honest landing cards (real sample images, video/PDF
moved to a "deliverables" section); rename Level 5 to the true original;
plain-language setup form (medium / guidance style / colour strategy / value
simplification — region-complexity, texture/background toggles and the raw
palette slider become internal defaults); SQLite project model wrapping
existing job outputs so projects list + resume works; centre-column layout
fix (video and observations move out of the main scroll).

**Phase 2 — Viewer & region interaction.** OpenSeadragon viewer with SVG
overlay in image coordinates (one shared coordinate system, natural-pixel
space of the original); overlays re-rendered as SVG from `regions.json` /
`edges.svg` instead of full-size PNGs where feasible; zoom/pan/fit/100 %/
minimap/flip/opacity/before-after; region click → info card (object, parent
mass, value family, colour family, mixture, lesson step); rectangle/polygon/
lasso selection + "analyse this area" endpoint that crops the *original*
full-res image, runs the hierarchy locally, and mounts the result as a child
node with offset coordinates.

**Phase 3 — Structured drawing analysis.** Vector contour paths with
ownership/level/importance; structural landmarks (bounds, axis, curvature
extrema, widest/narrowest); envelope + negative-space masks; semantic
must-not-merge constraints (subject/depth) in the merge tree; edge cause
attribution; real numbered dot-to-dot with difficulty levels; delete the two
superseded classic generators.

**Phase 4 — Lesson engine.** New step schema (§7: objective, action, region,
overlay, completion check, common mistake, stop condition, checkpoint,
dependency); phases A–E generated from the analysis (composition → drawing →
value foundation → form → edges); the progressive contour lesson (§8) from
Phase-3 paths; per-step overlay bindings to the viewer; guidance style
controls step granularity and checkpoint count — never image fidelity;
lesson progress persisted per project.

**Phase 5 — Medium-specific execution.** Medium modules restructure the
phase graph (watercolour: whites plan + light-to-dark; oil: imprimatura +
fat-over-lean; acrylic: premix/timing; pencil/charcoal: mark-making;
digital: selections/masks), conditional advice replaces absolute rules
("this image's lights measure warmer than its shadows — so…").

**Phase 6 — Progress checking.** Checkpoints gate phase transitions (the
drawing checkpoint before values, §2.G); reuse the alignment chain; add
silhouette/placement/proportion/negative-space comparison; emit ONE priority
correction (structure before value before colour before edges) with
secondary items collapsed; attempts stored per checkpoint.

**Phase 7 — Save & continue.** Project dashboard (list, resume, per-project
state: settings, corrections, selections, local analyses, lesson progress,
attempts, current priority correction); versioned progress photos; the
landing gains "continue where you left off".

Suggested order of PRs: 1 → 2 → 3 → 4 (the core value), then 5/6/7 (5 and 6
can proceed in parallel after 4).

## Acceptance-criteria mapping (§25)

Criteria 1, 7 → Phase 1 · 2–5 → Phase 2 · 6, 19 → Phase 3 · 10, 11, 18, 20 →
Phase 4 · 17 → Phase 5 · 12, 13 → Phase 6 · 14 → Phase 7 · 8, 9 → Phases 1+4
(palette split) · 15, 16 → Phase 1.
