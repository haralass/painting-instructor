"use client";
// Structured lesson player (Phase 4).
//
// Walks manifest.lesson (schemas/lesson.py) — a composition-first sequence
// with the progressive contour lesson and a drawing checkpoint before any
// value. Each step's overlay renders on the Phase-2 viewer: construction SVG
// for the drawing phases (reusing the Phase-3 builder), asset images for
// value/colour/edge. Per-step completion and checkpoint state persist through
// the Phase-1 project store, so a lesson resumes where it was left.
import { useEffect, useMemo, useRef, useState } from "react";
import Viewer from "./Viewer";
import {
  API, outputUrl, type DrawingAnalysis, type Manifest,
} from "../lib/manifest";
import { buildStageSvgById, GUIDE_CAPS, type Guidance } from "../lib/constructionSvg";

type LessonStep = NonNullable<Manifest["lesson"]>["steps"][number];

const PHASE_LABEL: Record<string, string> = {
  plan: "Plan", composition: "Composition", drawing: "Drawing",
  block_in: "Block-in", develop: "Develop", render: "Render", finish: "Finish",
  // legacy lessons
  value: "Value", colour: "Colour", form: "Form", edges: "Edges", detail: "Detail",
};

export default function GuidedLessonPlayer({
  jobId, referenceUrl, manifest, onOpenCritique,
}: {
  jobId: string; referenceUrl: string; manifest: Manifest | null;
  onOpenCritique?: () => void;
}) {
  const lesson = manifest?.lesson ?? null;
  const guidance = (lesson?.guidance ?? "balanced") as Guidance;
  const [step, setStep] = useState(0);
  const [drawing, setDrawing] = useState<DrawingAnalysis | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [doneSteps, setDoneSteps] = useState<Set<string>>(new Set());
  const [passedCps, setPassedCps] = useState<Set<string>>(new Set());
  const saving = useRef(false);

  // Drawing geometry for the construction overlays.
  useEffect(() => {
    const url = manifest?.drawing_json ? outputUrl(manifest.drawing_json)
                                       : outputUrl(`${jobId}/drawing.json`);
    fetch(url).then(r => (r.ok ? r.json() : null)).then(setDrawing).catch(() => {});
  }, [jobId, manifest?.drawing_json]);

  // Resolve the project and hydrate saved progress.
  useEffect(() => {
    fetch(`${API}/projects/by-job/${jobId}`)
      .then(r => (r.ok ? r.json() : null))
      .then(p => {
        if (!p) return;
        setProjectId(p.id);
        setDoneSteps(new Set((p.lesson_progress ?? [])
          .filter((r: { status: string }) => r.status === "completed")
          .map((r: { step_id: string }) => r.step_id)));
        setPassedCps(new Set((p.checkpoints ?? [])
          .filter((c: { status: string }) => c.status === "passed")
          .map((c: { type: string }) => `cp_${c.type}`)));
      }).catch(() => {});
  }, [jobId]);

  const steps = lesson?.steps ?? [];
  const cur = steps[step];
  const checkpoints = useMemo(
    () => new Map((lesson?.checkpoints ?? []).map(c => [c.id, c])),
    [lesson]
  );

  const overlaySvg = useMemo(() => {
    if (!drawing || !cur) return "";
    const svgOv = cur.overlays?.find(o => o.kind === "svg" && o.asset?.startsWith("construction:"));
    if (!svgOv?.asset) return "";
    return buildStageSvgById(drawing, svgOv.asset.replace("construction:", ""), GUIDE_CAPS[guidance]);
  }, [drawing, cur, guidance]);

  // Raster overlay (value/colour/edge steps) — an asset image path.
  const rasterOverlay = useMemo(() => {
    if (!cur || overlaySvg) return [];
    const img = cur.overlays?.find(o => o.asset && !o.asset.startsWith("construction:"));
    return img?.asset ? [outputUrl(img.asset)] : [];
  }, [cur, overlaySvg]);

  if (!lesson || steps.length === 0) {
    return <div className="flex-1 flex items-center justify-center text-sm"
                style={{ color: "var(--text-dim)" }}>
      No structured lesson available for this project.
    </div>;
  }

  async function persistStepDone(stepId: string) {
    setDoneSteps(prev => new Set(prev).add(stepId));
    if (!projectId || saving.current) return;
    saving.current = true;
    try {
      await fetch(`${API}/projects/${projectId}/progress`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_id: stepId, status: "completed" }),
      });
    } catch { /* offline — local state still advances */ }
    finally { saving.current = false; }
  }

  async function persistCheckpoint(cpId: string, cpType: string) {
    setPassedCps(prev => new Set(prev).add(cpId));
    if (!projectId) return;
    try {
      await fetch(`${API}/projects/${projectId}/checkpoints`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: cpType, status: "passed", checkpoint_id: cpId }),
      });
    } catch { /* offline */ }
  }

  const cp = cur?.checkpoint_id ? checkpoints.get(cur.checkpoint_id) : undefined;
  const isUpload = cur?.completion_check?.kind === "upload";
  const stepDone = cur ? doneSteps.has(cur.id) : false;
  const progressPct = Math.round((doneSteps.size / steps.length) * 100);

  return (
    <div className="flex flex-1 min-h-0 gap-3">
      {/* Centre: viewer with the active step's overlay */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <button className="btn-ghost" style={pill}
                  onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}>← Back</button>
          <span className="text-sm font-medium" style={{ color: "var(--ink)" }}>
            Step {step + 1} / {steps.length}
          </span>
          <button className="btn-primary" style={pill}
                  onClick={() => setStep(s => Math.min(steps.length - 1, s + 1))}
                  disabled={step >= steps.length - 1}>Next →</button>
          <span className="text-xs px-2 py-1 rounded-full ml-2"
                style={{ background: "var(--surface)", color: "var(--text-dim)" }}>
            {lesson.medium} · {guidance} guidance
          </span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>{progressPct}% done</span>
            <div style={{ width: 90, height: 6, borderRadius: 3, background: "var(--surface)" }}>
              <div style={{ width: `${progressPct}%`, height: "100%", borderRadius: 3, background: "var(--accent)" }} />
            </div>
          </div>
        </div>
        <Viewer
          jobId={jobId} referenceUrl={referenceUrl}
          overlays={rasterOverlay} opacity={0.85}
          mode={rasterOverlay.length ? "overlay" : "reference"}
          imageWidth={manifest?.image?.width} imageHeight={manifest?.image?.height}
          svgOverlay={overlaySvg} disableSelection manifest={manifest}
        />
      </div>

      {/* Right: contextual step panel */}
      <aside className="w-80 flex-shrink-0 overflow-y-auto pl-1 hidden lg:block">
        {/* Phase rail */}
        <ol className="space-y-0.5 mb-4">
          {steps.map((s, i) => (
            <li key={s.id}>
              <button onClick={() => setStep(i)}
                      className="w-full text-left px-2 py-1.5 rounded text-xs flex items-center gap-2"
                      style={{
                        background: i === step ? "var(--accent)" : "transparent",
                        color: i === step ? "var(--paper)" : doneSteps.has(s.id) ? "var(--text)" : "var(--text-dim)",
                      }}>
                <span style={{ opacity: 0.7, minWidth: 16 }}>
                  {doneSteps.has(s.id) ? "✓" : String(i + 1).padStart(2, "0")}
                </span>
                <span className="truncate">{s.title}</span>
                {s.checkpoint_id && <span title="checkpoint">⚑</span>}
              </button>
            </li>
          ))}
        </ol>

        {cur && (
          <div className="p-3 rounded-xl" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
              {PHASE_LABEL[cur.phase] ?? cur.phase}
            </p>
            <p className="font-display text-lg mb-1" style={{ color: "var(--ink)" }}>{cur.title}</p>
            <p className="text-sm mb-2" style={{ color: "var(--text)" }}>{cur.objective}</p>

            <p className="text-xs font-semibold mt-2" style={{ color: "var(--text-dim)" }}>DO</p>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{cur.action}</p>

            {cur.explanation && (
              <p className="text-xs leading-relaxed mt-2 pl-3 italic"
                 style={{ color: "var(--text-dim)", borderLeft: "2px solid var(--accent)" }}>
                {cur.explanation}
              </p>
            )}
            {cur.mixture && (
              <p className="text-xs mt-2" style={{ color: "var(--text-dim)" }}>Mix: {cur.mixture}</p>
            )}
            {cur.common_mistake && (
              <p className="text-xs mt-2 p-2 rounded" style={{ background: "rgba(157,47,47,0.08)", color: "var(--crimson)" }}>
                Avoid: {cur.common_mistake}
              </p>
            )}
            {cur.stop_condition && (
              <p className="text-xs mt-2" style={{ color: "var(--accent)" }}>⛔ {cur.stop_condition}</p>
            )}

            {/* Checkpoint gate */}
            {cp && (
              <div className="mt-3 p-2 rounded-lg" style={{ background: "var(--surface-2)", border: "1px dashed var(--border-strong)" }}>
                <p className="text-xs font-semibold" style={{ color: "var(--ink)" }}>
                  ⚑ {cp.title}{passedCps.has(cp.id) ? " — passed" : ""}
                </p>
                <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{cp.instructions}</p>
                {isUpload && onOpenCritique && (
                  <button onClick={onOpenCritique} className="btn-ghost mt-2" style={pill}>
                    Upload my attempt →
                  </button>
                )}
                {!passedCps.has(cp.id) && (
                  <button onClick={() => persistCheckpoint(cp.id, cp.type)}
                          className="btn-ghost mt-2 ml-2" style={pill}>
                    Mark checkpoint passed
                  </button>
                )}
              </div>
            )}

            {/* Completion */}
            <div className="mt-3 flex items-center gap-2">
              {cur.completion_check && (
                <p className="text-xs flex-1" style={{ color: "var(--text-dim)" }}>
                  Done when: {cur.completion_check.criteria}
                </p>
              )}
              <button
                onClick={() => { persistStepDone(cur.id); setStep(s => Math.min(steps.length - 1, s + 1)); }}
                className="btn-primary" style={{ ...pill, opacity: stepDone ? 0.6 : 1 }}>
                {stepDone ? "✓ Done" : "Mark done"}
              </button>
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

const pill: React.CSSProperties = { padding: "5px 14px", fontSize: 13 };
