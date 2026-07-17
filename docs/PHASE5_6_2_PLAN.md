# Phases 5 + 6 + Phase-2 leftovers — parallel batch

> **STATUS (2026-07-13): COMPLETE & INTEGRATED** on `feature/phase1-foundations`
> (commits `55f1aca…73d98cc`, pushed). Backend suite **318 passed** (was 287),
> frontend 13 vitest + `tsc` clean + `next build` clean, all three live-verified.
> Built by three parallel agents in isolated git worktrees, integrated here.

## Phase 5 — medium-specific execution (`teaching/lesson_engine.py`)

Execution now differs by medium in **steps**, not just wording, while the
composition + drawing phases stay byte-identical across mediums and the
drawing checkpoint still gates before values:

- **watercolour** — new pivotal "Reserve the whites" step at the head of the
  value phase (no other medium has it); value step demands strict
  light-to-dark, judging only when dry, holding back unrecoverable darks.
- **oil** — imprimatura retained; fat-over-lean / thin-darks in value + form.
- **acrylic** — work-in-sections, premix generously (dries darker), glaze
  rather than rework once dry.
- **pencil / charcoal** — the paint-mixing step is *replaced* by "Set your
  value range" (3 value masses); charcoal lifts lights from the toned sheet.
- **digital** — selections/masks, colour-pick from reference, non-destructive.

18 lesson-engine tests (was 8). One pre-existing test was correctly narrowed:
it asserted the whole per-step phase list was identical across mediums, which
is no longer true now that watercolour legitimately adds a step — it now
asserts identical composition/drawing titles + canonical phase ordering.

## Phase 6 — prioritized progress critique (`critique/priority.py`, new)

Compares components **independently** and emits ONE ranked correction instead
of a flat list or a global score. Ordering: **placement → proportion → value →
colour → edges**. Structural comparison uses the reference `subject_bounds`
from `drawing.json` vs the attempt's foreground extent after alignment
(largest connected blob, so background clutter can't skew the box).

Honesty rule: structural findings only win when `alignment_confidence ≥ 0.35`;
below that `priority` falls back to value/colour, sets `structure_checked:
false`, and says placement/proportion couldn't be checked. The existing
alignment chain (`_align_attempt_ex`) is reused, **not** replaced;
`feedback`/`scores`/`metric_scores` are preserved for back-compat.
`critique_attempt` gained an optional `drawing` param; the API loads
`drawing.json` and passes it. CritiquePanel leads with a "Fix this first"
card; `secondary` collapses below.

## Phase-2 leftovers — selection + "Analyse this area"

- `Viewer.tsx`: a "Select area" toggle suspends OSD mouse-nav and turns drag
  into a rectangle (converted to **ORIGINAL-image px** via `bboxToCropRect`);
  region click-select still works when the toggle is off.
- `backend/analysis/local.py` + `POST /jobs/{job_id}/local-analysis`: crops
  from the **ORIGINAL full-res** `reference.*` (never a preview/overlay),
  clamps the bbox, downscales only the *crop* for runtime, and returns
  `offset`/`scale` so `parent_px = offset + local_px / scale`. Result assets
  land in `outputs/{job}/local/{selection_id}/`.
- `page.tsx` shows the real returned analysis in a result panel.
- Live-verified: a 509×634 px selection produced a real local analysis whose
  assets are exactly the crop size (400×400 for a 400×400 bbox at scale 1.0),
  proving the crop came from the original, not a downscaled preview.

## Integration notes

All three agents' worktrees branched off `main`/Phase-4 HEAD; both
cherry-picks **auto-merged `backend/api/main.py` with no conflict** (Agent A's
`drawing.json` load in `critique_job` and Agent C's new endpoint sit in
different regions; the Phase-1 attempt-recording survived intact). Agent C
stalled during its own live-test *before* verifying — its work was recovered
from the uncommitted worktree and verified here instead; its selection UI and
endpoint both work.

## Remaining

Phase 7 polish (versioned progress, resume UX), user landmark editing, local
crops producing a child *DrawingAnalysis* (currently a child hierarchy only),
lasso/polygon selection (rectangle only today), SVG vector overlays where PNG
masks fall short. Branch is **not merged to main and no PR is open**.
