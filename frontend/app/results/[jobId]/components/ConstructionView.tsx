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
import {
  outputUrl, type DrawingAnalysis, type DrawStage, type Manifest,
} from "../lib/manifest";

const C = {                       // explicit colours (CSS vars don't resolve in injected SVG)
  accent: "#b4511f", cool: "#3e5c76", ink: "#2b2117",
  sage: "#6f7d5c", paper: "#f8f4ea", faint: "#9a8f7e",
};

type Guidance = "full" | "balanced" | "autonomy";
const GUIDE_CAPS: Record<Guidance, { landmarks: number; internal: number; slopes: number }> = {
  full:     { landmarks: 99, internal: 40, slopes: 8 },
  balanced: { landmarks: 8,  internal: 15, slopes: 4 },
  autonomy: { landmarks: 6,  internal: 6,  slopes: 3 },
};

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
    () => (drawing ? buildSvg(drawing, step, caps) : ""),
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

// ── SVG builder: draw stages 0..step, current emphasised, earlier faint ──────
function buildSvg(d: DrawingAnalysis, step: number, caps: { landmarks: number; internal: number; slopes: number }): string {
  const W = d.image_width, H = d.image_height;
  const u = Math.max(W, H);
  const sw = u * 0.004;                          // base stroke width in image units
  const r = u * 0.008;                           // marker radius
  const lm = new Map(d.landmarks.map(l => [l.id, l]));
  const parts: string[] = [];

  const done = (i: number) => i < step;          // faint if before current stage
  const op = (i: number) => (done(i) ? 0.28 : 1);

  d.construction_order.forEach((s, i) => {
    if (i > step) return;
    const o = op(i);
    const emph = i === step;
    parts.push(stageSvg(s, i, d, lm, { W, H, u, sw, r, o, emph, caps }));
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" `
       + `preserveAspectRatio="xMidYMid meet">${parts.join("")}</svg>`;
}

function stageSvg(
  s: DrawStage, i: number, d: DrawingAnalysis, lm: Map<string, any>,
  ctx: { W: number; H: number; u: number; sw: number; r: number; o: number; emph: boolean; caps: any },
): string {
  const { W, H, sw, r, o, emph, caps } = ctx;
  const p: string[] = [];
  const cur = (c: string) => (emph ? c : C.faint);
  const dot = (x: number, y: number, col: string, rr = r) =>
    `<circle cx="${x}" cy="${y}" r="${rr}" fill="${col}" fill-opacity="${o}"/>`;
  const line = (a: number[], b: number[], col: string, w = sw, dash = "") =>
    `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="${col}" stroke-width="${w}" `
    + `stroke-opacity="${o}" stroke-linecap="round" ${dash ? `stroke-dasharray="${dash}"` : ""}/>`;
  const poly = (pts: number[][], col: string, w: number, fill = "none", dash = "") =>
    `<polygon points="${pts.map(q => q.join(",")).join(" ")}" fill="${fill}" fill-opacity="${o * 0.15}" `
    + `stroke="${col}" stroke-width="${w}" stroke-opacity="${o}" ${dash ? `stroke-dasharray="${dash}"` : ""}/>`;
  const b = d.subject_bounds;

  switch (s.id) {
    case "canvas":
      p.push(`<rect x="0" y="0" width="${W}" height="${H}" fill="none" stroke="${cur(C.ink)}" stroke-width="${sw}" stroke-opacity="${o}"/>`);
      break;
    case "placement":
      p.push(`<rect x="${b.x_min}" y="${b.y_min}" width="${b.x_max - b.x_min}" height="${b.y_max - b.y_min}" fill="none" stroke="${cur(C.accent)}" stroke-width="${sw}" stroke-opacity="${o}" stroke-dasharray="${sw * 3} ${sw * 2}"/>`);
      break;
    case "bounds":
      ["subject_top", "subject_bottom", "subject_left", "subject_right"].forEach(cat => {
        d.landmarks.filter(l => l.category === cat).forEach(l => {
          p.push(dot(l.x, l.y, cur(C.accent), r * 1.2));
          if (cat === "subject_top" || cat === "subject_bottom")
            p.push(line([0, l.y], [W, l.y], cur(C.cool), sw * 0.5, `${sw} ${sw * 2}`));
          else
            p.push(line([l.x, 0], [l.x, H], cur(C.cool), sw * 0.5, `${sw} ${sw * 2}`));
        });
      });
      break;
    case "occupied_area":
      if (d.occupied_area.length >= 3)
        p.push(poly(d.occupied_area, cur(C.sage), sw, C.sage));
      break;
    case "landmarks": {
      const shown = d.landmarks
        .filter(l => ["widest_point", "narrowest_point", "major_corner"].includes(l.category))
        .sort((a, z) => z.importance - a.importance).slice(0, caps.landmarks);
      shown.forEach(l => p.push(dot(l.x, l.y, cur(C.accent))));
      break;
    }
    case "axis":
      if (d.main_axis)
        p.push(line(d.main_axis.start, d.main_axis.end, cur(C.accent), sw * 1.3));
      break;
    case "slopes":
      d.dominant_slopes.slice(0, caps.slopes).forEach(a =>
        p.push(line(a.start, a.end, cur(C.cool), sw, `${sw * 2} ${sw}`)));
      break;
    case "envelope":
      if (d.envelope && d.envelope.vertices.length >= 3) {
        p.push(poly(d.envelope.vertices, cur(C.accent), sw * 1.2));
        d.envelope.vertices.forEach(v => p.push(dot(v[0], v[1], cur(C.accent), r * 0.8)));
      }
      break;
    case "negative_space":
      d.negative_spaces.forEach(n =>
        n.polygon.length >= 3 && p.push(poly(n.polygon, cur(C.cool), sw * 0.8, C.cool, `${sw} ${sw}`)));
      break;
    case "proportion":
      d.proportion_checks.filter(pc => pc.kind === "thirds").forEach(pc => {
        if (pc.reference_points.length >= 2)
          p.push(line(pc.reference_points[0], pc.reference_points[1], cur(C.sage), sw * 0.7, `${sw * 1.5} ${sw}`));
      });
      break;
    case "silhouette":
      if (d.silhouette && d.silhouette.points.length >= 2)
        p.push(poly(d.silhouette.points, cur(C.ink), sw * 1.4));
      break;
    case "internal_divisions":
    case "secondary_structure": {
      const want = s.id === "internal_divisions" ? "internal_division" : "secondary_structure";
      d.internal_paths.filter(pp => pp.category === want)
        .sort((a, z) => z.importance - a.importance).slice(0, caps.internal)
        .forEach(pp => {
          const pts = pp.points.map(q => q.join(",")).join(" ");
          p.push(`<polyline points="${pts}" fill="none" stroke="${cur(want === "internal_division" ? C.ink : C.faint)}" stroke-width="${sw * (want === "internal_division" ? 1 : 0.7)}" stroke-opacity="${o}" stroke-linecap="round"/>`);
        });
      break;
    }
    case "checkpoint":
      if (d.silhouette)
        p.push(poly(d.silhouette.points, C.ink, sw * 1.4));
      break;
  }
  return p.join("");
}
