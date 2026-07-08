"use client";
import { useMemo, useState } from "react";
import LayerStack from "./LayerStack";
import { outputUrl, LEVEL_LABELS, type Manifest } from "../lib/manifest";

// ── Progressive-Reveal reference (anti-premature-detail) ─────────────────────
// Detail is a reward, not a right. This view withholds refinement until the
// learner has committed to the big shapes: it starts at detail level 1 (a few
// big masses) and only reveals levels 2→5 one at a time, each behind a
// deliberate button press. Busy areas stay coarse until the final reveal,
// because detail added on wrong shapes only makes the wrongness permanent.

// One short teaching note per detail level — keyed by the manifest's 1..5.
const STAGE_NOTES: Record<number, string> = {
  1: "Big masses only. Block these in before you earn the next level of detail — detail added on wrong shapes only makes the wrongness permanent.",
  2: "Still shapes, not things. Confirm each mass sits in the right place and reads at the right value before you refine a single edge.",
  3: "Now the major forms divide. Keep measuring against the big masses — a correct small shape on a wrong big shape is still wrong.",
  4: "Edges and transitions arrive. Add detail only where the underlying shape is already true; leave busy areas coarse a little longer.",
  5: "Full reference. Every fine mark here rides on masses you already got right — that is why it holds together.",
};

const FALLBACK_NOTE =
  "Block these masses in before you earn the next level of detail — detail added on wrong shapes only makes the wrongness permanent.";

export default function ProgressiveReveal({
  manifest,
  referenceUrl,
}: {
  manifest: Manifest | null;
  referenceUrl: string;
}) {
  // The ordered list of available detail levels (numbers), ascending.
  const levels = useMemo(() => {
    const dl = manifest?.detail_levels ?? {};
    return Object.values(dl)
      .map(l => l.level)
      .filter((n): n is number => typeof n === "number")
      .sort((a, b) => a - b);
  }, [manifest]);

  const minLevel = levels[0] ?? 1;
  const maxLevel = levels[levels.length - 1] ?? minLevel;

  // The highest level the learner has earned so far. Starts at the coarsest.
  const [revealed, setRevealed] = useState(minLevel);
  const atFinal = revealed >= maxLevel;

  const levelData = manifest?.detail_levels?.[String(revealed)];

  // Compose the current level: colours as the base, values and outlines
  // multiplied over — the same layer order the explorer uses, so a level looks
  // identical here. Coarse levels are coarse because the backend built them so.
  const assets = useMemo(() => {
    if (!levelData) return [];
    return [levelData.colours, levelData.values, levelData.outlines]
      .map(p => (p ? outputUrl(p) : ""))
      .filter(Boolean);
  }, [levelData]);

  const note = STAGE_NOTES[revealed] ?? FALLBACK_NOTE;

  if (levels.length === 0) {
    return (
      <div className="p-4 md:p-6 max-w-3xl">
        <div className="panel p-6 text-center" style={{ borderRadius: 18 }}>
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>
            No detail levels are available for this image yet.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-3xl">
      {/* ── Heading ─────────────────────────────────────────────────────── */}
      <div>
        <p className="eyebrow mb-1">Build up</p>
        <h2 className="text-xl font-bold font-display mb-1" style={{ color: "var(--text)" }}>
          Earn your <em style={{ color: "var(--accent)" }}>detail</em>
        </h2>
        <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>
          Detail is a reward, not a right. Start with the big masses and only
          unlock finer levels once the shapes underneath are true — refining the
          wrong shape just makes the mistake permanent.
        </p>
      </div>

      {/* ── Level stepper ───────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap" role="list" aria-label="Detail levels">
        {levels.map((lv, i) => {
          const unlocked = lv <= revealed;
          const current = lv === revealed;
          return (
            <div key={lv} className="flex items-center gap-2" role="listitem">
              {i > 0 && (
                <span
                  aria-hidden
                  style={{
                    width: 18, height: 2, borderRadius: 2,
                    background: lv <= revealed ? "var(--accent)" : "var(--border)",
                  }}
                />
              )}
              <div
                title={LEVEL_LABELS[lv] ?? `Level ${lv}`}
                aria-current={current ? "step" : undefined}
                style={{
                  display: "flex", alignItems: "center", justifyContent: "center",
                  width: 34, height: 34, borderRadius: 999, fontWeight: 700, fontSize: 14,
                  background: current ? "var(--accent)" : unlocked ? "var(--surface)" : "transparent",
                  color: current ? "var(--paper)" : unlocked ? "var(--text)" : "var(--text-dim)",
                  border: `1px solid ${unlocked ? "var(--accent)" : "var(--border)"}`,
                  opacity: unlocked ? 1 : 0.55,
                  transition: "all 0.3s ease",
                }}
              >
                {unlocked ? lv : "🔒"}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── The current level ───────────────────────────────────────────── */}
      <div className="panel p-3" style={{ borderRadius: 18 }}>
        <p className="label-xs mb-2">
          Level {revealed} · {levelData?.label ?? LEVEL_LABELS[revealed] ?? ""}
        </p>
        <LayerStack
          assets={assets}
          imageWidth={manifest?.image?.width}
          imageHeight={manifest?.image?.height}
          maxHeight={480}
        />

        {/* At the final reveal, the real reference is the culmination — the
            detail you earned by getting every mass beneath it right. */}
        {atFinal && referenceUrl && (
          <div className="mt-3">
            <p className="label-xs mb-2">The full reference — earned</p>
            <img
              src={referenceUrl}
              alt="Full reference"
              className="w-full rounded-xl object-contain layer-transition"
              style={{ maxHeight: 360, background: "var(--surface-2)" }}
            />
          </div>
        )}
      </div>

      {/* ── Teaching note for this stage ────────────────────────────────── */}
      <p className="text-sm leading-relaxed px-4 py-3 rounded-xl"
         style={{ background: "rgba(180,81,31,0.07)", border: "1px solid rgba(180,81,31,0.22)", color: "var(--text)" }}>
        {note}
      </p>

      {/* ── Reveal control ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 flex-wrap">
        {!atFinal ? (
          <button
            type="button"
            onClick={() => setRevealed(r => {
              const next = levels.find(lv => lv > r);
              return next ?? r;
            })}
            className="btn-primary"
            style={{ padding: "10px 22px", fontSize: 14 }}
          >
            Reveal next stage →
          </button>
        ) : (
          <span className="chip" data-active aria-disabled>
            Fully revealed
          </span>
        )}
        {revealed > minLevel && (
          <button
            type="button"
            onClick={() => setRevealed(minLevel)}
            className="btn-ghost"
            style={{ padding: "10px 18px", fontSize: 13 }}
          >
            Start over
          </button>
        )}
      </div>
    </div>
  );
}
