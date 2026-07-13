"use client";
// Progressive drawing-construction lesson (Phase 3, Study mode).
//
// Steps through the stored construction order — canvas/placement → bounds →
// landmarks → axis → slopes → envelope → negative space → proportion →
// refined silhouette → internal structure → checkpoint — drawing each stage
// as a vector overlay on the Phase-2 viewer (analysis-px coordinates, so it
// stays aligned through zoom/pan). The finished contour is NEVER the starting
// point: earlier stages are drawn faintly, the current stage emphasised.
//
// Guidance level changes how many landmarks / internal lines are shown — it
// never changes the geometry (spec §1.6).
import { useEffect, useMemo, useState } from "react";
import Viewer from "./Viewer";
import { outputUrl, type DrawingAnalysis, type Manifest } from "../lib/manifest";
import { buildConstructionSvg, GUIDE_CAPS, type Guidance } from "../lib/constructionSvg";

export default function ConstructionView({
  jobId, referenceUrl, manifest,
}: { jobId: string; referenceUrl: string; manifest: Manifest | null }) {
  const [drawing, setDrawing] = useState<DrawingAnalysis | null>(null);
  const [failed, setFailed]   = useState(false);
  const [step, setStep]       = useState(0);
  const [guidance, setGuidance] = useState<Guidance>("full");

  useEffect(() => {
    const url = manifest?.drawing_json
      ? outputUrl(manifest.drawing_json) : outputUrl(`${jobId}/drawing.json`);
    fetch(url).then(r => (r.ok ? r.json() : Promise.reject()))
      .then((d: DrawingAnalysis) => setDrawing(d))
      .catch(() => setFailed(true));
  }, [jobId, manifest?.drawing_json]);

  const stages = drawing?.construction_order ?? [];
  const stage = stages[step];
  const caps = GUIDE_CAPS[guidance];

  const svg = useMemo(
    () => (drawing ? buildConstructionSvg(drawing, step, caps) : ""),
    [drawing, step, caps]
  );

  if (failed) {
    return <div className="flex-1 flex items-center justify-center text-sm"
                style={{ color: "var(--text-dim)" }}>
      No drawing construction available for this project.
    </div>;
  }
  if (!drawing) {
    return <div className="flex-1 flex items-center justify-center text-sm"
                style={{ color: "var(--text-dim)" }}>Loading construction…</div>;
  }

  const b = drawing.subject_bounds;
  const stageLandmarks = stage
    ? drawing.landmarks.filter(l => stage.landmark_ids.includes(l.id))
    : [];
  const stageProps = stage
    ? drawing.proportion_checks.filter(p => stage.proportion_check_ids.includes(p.id))
    : [];

  return (
    <div className="flex flex-1 min-h-0 gap-3">
      {/* Centre: viewer + vector construction overlay */}
      <div className="flex-1 min-w-0 flex flex-col min-h-0">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <button className="btn-ghost" style={pill}
                  onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}>← Back</button>
          <span className="text-sm font-medium" style={{ color: "var(--ink)" }}>
            Step {step + 1} / {stages.length}
          </span>
          <button className="btn-primary" style={pill}
                  onClick={() => setStep(s => Math.min(stages.length - 1, s + 1))}
                  disabled={step >= stages.length - 1}>Next →</button>
          <div className="ml-auto flex items-center gap-1">
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>Guidance</span>
            {(["full", "balanced", "autonomy"] as Guidance[]).map(g => (
              <button key={g} onClick={() => setGuidance(g)}
                      className="px-2 py-1 rounded text-xs" style={{
                        background: guidance === g ? "var(--accent)" : "var(--surface)",
                        color: guidance === g ? "var(--paper)" : "var(--text-dim)",
                        border: "1px solid var(--border)", cursor: "pointer",
                      }}>{g === "full" ? "Full" : g === "balanced" ? "Balanced" : "Autonomy"}</button>
            ))}
          </div>
        </div>
        <Viewer
          jobId={jobId} referenceUrl={referenceUrl}
          overlays={[]} opacity={1} mode="reference"
          imageWidth={drawing.image_width} imageHeight={drawing.image_height}
          svgOverlay={svg} disableSelection manifest={manifest}
        />
      </div>

      {/* Right: contextual stage panel */}
      <aside className="w-72 flex-shrink-0 overflow-y-auto pl-1 hidden lg:block">
        {/* Stage rail */}
        <ol className="space-y-1 mb-4">
          {stages.map((s, i) => (
            <li key={s.id}>
              <button onClick={() => setStep(i)}
                      className="w-full text-left px-2 py-1.5 rounded text-xs flex items-center gap-2"
                      style={{
                        background: i === step ? "var(--accent)" : i < step ? "var(--surface)" : "transparent",
                        color: i === step ? "var(--paper)" : i < step ? "var(--text)" : "var(--text-dim)",
                      }}>
                <span style={{ opacity: 0.7 }}>{i < step ? "✓" : String(i + 1).padStart(2, "0")}</span>
                {s.title}{s.is_checkpoint ? " ⚑" : ""}
              </button>
            </li>
          ))}
        </ol>

        {stage && (
          <div className="p-3 rounded-xl" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
              {stage.is_checkpoint ? "Checkpoint" : `Stage ${step + 1}`}
            </p>
            <p className="font-display text-lg mb-1" style={{ color: "var(--ink)" }}>{stage.title}</p>
            <p className="text-sm leading-relaxed mb-2" style={{ color: "var(--text)" }}>{stage.summary}</p>

            {/* Grounded facts for this stage, from the analysis */}
            {stage.id === "canvas" && (
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                Canvas ratio {drawing.canvas_ratio.toFixed(2)} · subject fills{" "}
                {Math.round(b.occupied_fraction * 100)}% of the frame.
              </p>
            )}
            {stage.id === "placement" && (
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                Margins — top {pct(b.margins.top)}, bottom {pct(b.margins.bottom)},
                left {pct(b.margins.left)}, right {pct(b.margins.right)}.
                {b.source !== "subject_mask" &&
                  " (Subject detection was approximate for this image.)"}
              </p>
            )}
            {stageLandmarks.length > 0 && (
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                {stageLandmarks.length} landmark{stageLandmarks.length > 1 ? "s" : ""} shown.
              </p>
            )}
            {stageProps.map(p => (
              <p key={p.id} className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>{p.label}</p>
            ))}
            {stage.id === "silhouette" && drawing.silhouette?.edge_cause?.primary && (
              <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
                The outer edge reads mostly as {causeWord(drawing.silhouette.edge_cause.primary)}
                {drawing.silhouette.edge_cause.confidence < 0.4 ? " (uncertain)." : "."}
              </p>
            )}
            {stage.is_checkpoint && (
              <p className="text-xs mt-2 p-2 rounded" style={{ background: "var(--surface-2)", color: "var(--text)" }}>
                Compare your whole drawing to the reference now — placement, silhouette and
                proportion — before any value or colour. Uploading your attempt for feedback
                arrives in a later step.
              </p>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

const pill: React.CSSProperties = { padding: "5px 14px", fontSize: 13 };
const pct = (f?: number) => `${Math.round((f ?? 0) * 100)}%`;
const causeWord = (c: string) => ({
  object_boundary: "an object boundary", depth: "a depth change",
  illumination: "a light/shadow edge", reflectance: "a colour change",
  texture: "surface texture",
}[c] ?? c);
