"use client";
import { useState } from "react";
import LayerStack from "./LayerStack";
import { absUrl, outputUrl, type Manifest, type MicroStep } from "../lib/manifest";

// Dev-only mock so the micro-step checklist can be eyeballed before the backend
// merges `image_micro_steps`. The real code path reads `step.image_micro_steps`
// from the manifest; flip this to true only for local visual inspection.
const DEV_MOCK_MICRO_STEPS = false;
const MOCK_MICRO_STEPS: MicroStep[] = [
  { order: 1, region_id: 3, location: "upper-left sky", value_label: "light", colour_name: "pale cerulean", area_frac: 0.22, action: "Block in the sky with a flat, even light-blue wash.", mix_hint: "cerulean + white + a touch of yellow" },
  { order: 2, region_id: 7, location: "foreground grass", value_label: "mid", colour_name: "olive green", area_frac: 0.14, action: "Lay the mid-value grass mass, keeping edges soft.", mix_hint: null },
  { order: 3, region_id: 12, location: "tree trunk", value_label: "dark", colour_name: "burnt umber", area_frac: 0.03, action: "Add the darkest accents on the trunk last.", mix_hint: "burnt umber + ultramarine" },
];

// ── Lesson player — the guided, step-by-step teacher ─────────────────────────
export default function LessonPlayer({
  manifest,
  referenceUrl,
  videoReady,
}: {
  manifest: Manifest;
  referenceUrl: string;
  videoReady: boolean;
}) {
  const steps = [...(manifest.lesson_plan ?? [])].sort((a, b) => a.order - b.order);
  const [idx, setIdx] = useState(0);
  const [showRef, setShowRef] = useState(false);
  // Checked micro-steps, keyed by `${stepOrder}:${microOrder}` so state is
  // stable across step navigation.
  const [checkedMicro, setCheckedMicro] = useState<Record<string, boolean>>({});
  const step = steps[idx];
  const brief = manifest.image_brief;

  if (!step) return null;

  const assets = Object.values(step.assets ?? {}).map(outputUrl).filter(Boolean);
  const stepLabel = step.order === 0 ? "Warm-up" : step.order === 99 ? "Final check" : `Step ${step.order}`;

  const microSteps: MicroStep[] = (step.image_micro_steps && step.image_micro_steps.length > 0)
    ? step.image_micro_steps
    : (DEV_MOCK_MICRO_STEPS ? MOCK_MICRO_STEPS : []);

  function toggleMicro(microOrder: number) {
    const key = `${step.order}:${microOrder}`;
    setCheckedMicro(prev => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="p-4 md:p-6 space-y-5">

      {/* The teacher's brief — image-specific, computed from THIS photo */}
      {(brief?.overview || manifest.personal_observations) && idx === 0 && (
        <div className="rounded-xl p-4"
             style={{ background: "rgba(180,81,31,0.06)", border: "1px solid rgba(180,81,31,0.22)" }}>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
            Before you start — about your photo
          </p>
          {brief?.overview && (
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{brief.overview}</p>
          )}
          {manifest.personal_observations && (
            <p className="text-sm leading-relaxed mt-2" style={{ color: "var(--text-dim)" }}>
              {manifest.personal_observations}
            </p>
          )}
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-5">

        {/* Visual for this step */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>
              {showRef ? "Reference photo" : "What to look at for this step"}
            </p>
            <button onClick={() => setShowRef(!showRef)}
                    className="px-3 py-1 rounded border text-xs transition-colors"
                    style={{
                      background:  showRef ? "var(--accent)" : "var(--surface)",
                      color:       showRef ? "var(--paper)" : "var(--text-dim)",
                      borderColor: "var(--border)",
                    }}>
              {showRef ? "Show analysis" : "Show reference"}
            </button>
          </div>
          {showRef || assets.length === 0 ? (
            <img src={referenceUrl} alt="Reference"
                 className="w-full rounded-xl object-contain layer-transition" style={{ maxHeight: 500 }} />
          ) : (
            <LayerStack assets={assets}
                        imageWidth={manifest.image?.width} imageHeight={manifest.image?.height}
                        maxHeight={500} />
          )}
        </div>

        {/* Teaching column */}
        <div className="w-full lg:w-80 flex-shrink-0 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
              {stepLabel} of {steps.filter(s => 1 <= s.order && s.order < 90).length}
              {manifest.input?.skill_level ? ` · ${manifest.input.skill_level}` : ""}
            </p>
            <h2 className="text-xl font-bold mb-2" style={{ color: "var(--text)" }}>{step.name}</h2>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{step.description}</p>
          </div>

          {/* For YOUR photo — the personal part */}
          {step.image_notes && step.image_notes.length > 0 && (
            <div className="rounded-xl p-3"
                 style={{ background: "rgba(180,81,31,0.07)", border: "1px solid rgba(180,81,31,0.28)" }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
                For your photo
              </p>
              <ul className="space-y-2">
                {step.image_notes.map((n, i) => (
                  <li key={i} className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Ordered micro-steps — a granular, checkable painting checklist */}
          {microSteps.length > 0 && (
            <div className="panel rounded-xl p-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--accent)" }}>
                Do these in order
              </p>
              <ol className="space-y-2">
                {[...microSteps].sort((a, b) => a.order - b.order).map(ms => {
                  const key = `${step.order}:${ms.order}`;
                  const checked = Boolean(checkedMicro[key]);
                  return (
                    <li key={key}>
                      <label className="flex gap-2.5 items-start cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleMicro(ms.order)}
                          className="mt-1 accent-orange-700 flex-shrink-0"
                        />
                        <span className="font-display text-xs mt-0.5 flex-shrink-0 tabular-nums"
                              style={{ color: "var(--accent)", minWidth: 20 }}>
                          {String(ms.order).padStart(2, "0")}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-start gap-2">
                            <span className="text-sm leading-snug flex-1"
                                  style={{ color: "var(--text)", opacity: checked ? 0.5 : 1, textDecoration: checked ? "line-through" : "none" }}>
                              {ms.action}
                            </span>
                            <span className="chip flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full tabular-nums"
                                  style={{ background: "var(--paper)", border: "1px solid var(--border)", color: "var(--text-dim)" }}>
                              {Math.round(ms.area_frac * 100)}%
                            </span>
                          </span>
                          {ms.mix_hint && (
                            <span className="block text-xs mt-0.5 leading-snug" style={{ color: "var(--text-dim)" }}>
                              {ms.mix_hint}
                            </span>
                          )}
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}

          {/* Why */}
          {step.why && (
            <div className="rounded-xl p-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>
                Why this step
              </p>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>{step.why}</p>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center gap-2">
            <button onClick={() => setIdx(Math.max(0, idx - 1))} disabled={idx === 0}
                    className="px-4 py-2 rounded-lg border text-sm transition-colors"
                    style={{
                      borderColor: "var(--border)", color: "var(--text)",
                      opacity: idx === 0 ? 0.35 : 1, cursor: idx === 0 ? "default" : "pointer",
                      background: "var(--surface)",
                    }}>
              ← Back
            </button>
            <button onClick={() => setIdx(Math.min(steps.length - 1, idx + 1))}
                    disabled={idx === steps.length - 1}
                    className="flex-1 px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
                    style={{
                      background: idx === steps.length - 1 ? "var(--surface)" : "var(--accent)",
                      color:      idx === steps.length - 1 ? "var(--text-dim)" : "var(--paper)",
                      cursor:     idx === steps.length - 1 ? "default" : "pointer",
                    }}>
              {idx === steps.length - 1 ? "Lesson complete" : "Next step →"}
            </button>
          </div>

          {/* Step dots */}
          <div className="flex gap-1.5 justify-center flex-wrap">
            {steps.map((s, i) => (
              <button key={s.order} onClick={() => setIdx(i)} title={s.name}
                      className="rounded-full transition-all"
                      style={{
                        width: i === idx ? 22 : 8, height: 8,
                        background: i === idx ? "var(--accent)" : i < idx ? "var(--accent-dim)" : "var(--border)",
                        border: "none", cursor: "pointer",
                      }} />
            ))}
          </div>
        </div>
      </div>

      {/* Tutorial video at the end of the lesson */}
      {videoReady && manifest.video && idx === steps.length - 1 && (
        <div className="pt-2">
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
            Watch the full progression
          </p>
          <video src={absUrl(manifest.video)} controls className="w-full rounded-xl"
                 style={{ background: "#000", maxHeight: 380 }} />
        </div>
      )}
    </div>
  );
}
