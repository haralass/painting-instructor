# Phases 5, 6, 7 — Implementation Notes

> **STATUS (2026-07-13): COMPLETE.** All on `feature/phase1-foundations`,
> full suite 320 passed, `next build` clean, live-verified. Phases 5, 6 and
> the Phase-2 selection leftover were built by three parallel worktree
> subagents and integrated here; Phase 7 followed. Branch pushed; not merged
> to main / no PR opened.

## Phase 5 — Medium-specific execution (commit `55f1aca`, `b82a593`)

`teaching/lesson_engine.py` now varies STEPS, not just wording, where the
physical process differs — while composition + drawing stay medium-agnostic
and the drawing-checkpoint-before-values invariant holds:
- watercolour: a new pivotal "Reserve the whites" step before the light/
  shadow split; value step is strictly light-to-dark, judged when dry, darks
  held back as unrecoverable.
- oil: imprimatura + fat-over-lean/thin-darks note in the form phase.
- acrylic: work-in-sections / premix-generously / glaze-don't-rework.
- pencil & charcoal: replace the paint-mixing step with "Set your value
  range" (3 value masses); charcoal lifts lights from a toned sheet.
- digital: selections/masks, colour-pick, non-destructive.
`tests/test_lesson_engine.py`: 8 → 18 tests.

## Phase 6 — Prioritized progress critique (commit `750811d`)

New `critique/priority.py` compares components independently against the
reference and the Phase-3 `drawing.json` (subject bounds) and emits ONE
ranked correction: **placement → proportion → value → colour → edges**.
`critique_attempt` gained an optional `drawing` param, emits `priority`
(component + message) and `secondary` (collapsed list), sets
`first_fix = priority.message`; the existing alignment chain and metrics are
reused untouched. Honesty rule: structural findings only win when
`alignment_confidence ≥ 0.35`, else it downgrades to a value/colour priority
with a note. `CritiquePanel.tsx` leads with the one "Fix this first" card;
`secondary` collapses below. `api/main.py:critique_job` loads `drawing.json`
and passes it (auto-merged cleanly with the Phase-1 attempt-recording).

## Phase 2 leftover — Selection + local analysis (commit `73d98cc`)

`analysis/local.py:run_local_analysis` crops from the ORIGINAL full-res
`reference.*` (never a preview), downscaling only the crop while remembering
the exact `scale`/`offset` so `parent_px = offset + local_px/scale`. Endpoint
`POST /jobs/{id}/local-analysis`. `Viewer.tsx` gains a "Select area" drag-
rectangle mode (coords via `imageCoords`), coexisting with region click-
select; `page.tsx` wires "Analyse this area" and shows the real returned
crop analysis. Verified live: a 400×400 original-px crop returns 400×400
assets at scale 1.0.

## Phase 7 — Save & continue (commit `055fb43`)

Project store gains a `selections` table and a resume summary (completed-step
count + latest prioritized correction) on `GET /projects`; `GET /projects/{id}`
returns selections; the local-analysis endpoint records each deeper look.
New `/projects` dashboard lists saved paintings with thumbnail, medium,
progress, the "Fix next" correction and a resume link; a Projects nav link
joins Gallery. Most of the persistence spine (project rows, lesson progress,
checkpoints, attempts, resume-from-disk) already existed from Phase 1.

## Parallel-integration note

Two subagents' worktrees branched from `main` (pre-Phase-1); they were
integrated by cherry-picking their single commits onto the Phase-1–4 branch.
The only shared file, `backend/api/main.py`, auto-merged with no conflict in
both cases (each agent's edits were localized to different endpoints, as
instructed). Registry/drift/contract tests stayed green — the guard against
the recurring "new step half-registered across surfaces" bug class.

## Remaining / not done

No PR opened, not merged to main. Deferred (brief §22 keeps scope tight):
user landmark editing, local-crop producing a full child `DrawingAnalysis`
(currently returns hierarchy assets, not a nested drawing), and a separate
uncertainty dashboard (intentionally omitted).
