// Shared construction-overlay SVG builder (Phase 3 view + Phase 4 lesson).
//
// Renders the drawing construction up to and including a target stage as an
// SVG in analysis-image coordinates (viewBox = image W×H), so it mounts on
// the Phase-2 viewer aligned to the reference. Earlier stages are faint, the
// target stage emphasised — the finished contour is never the starting point.
import type { DrawingAnalysis, DrawStage } from "./manifest";

export const C = {
  accent: "#b4511f", cool: "#3e5c76", ink: "#2b2117",
  sage: "#6f7d5c", paper: "#f8f4ea", faint: "#9a8f7e",
};

export type Guidance = "full" | "balanced" | "autonomy";
// Artistic contour simplification (no CV jargon): which stored silhouette
// level to draw. Busy photos are already auto-simplified server-side.
export type ContourLevel = "simple" | "standard" | "refined";
export const CONTOUR_LABELS: Record<ContourLevel, string> = {
  simple: "Main structure", standard: "Standard", refined: "Refined",
};
export const GUIDE_CAPS: Record<Guidance, { landmarks: number; internal: number; slopes: number }> = {
  full:     { landmarks: 99, internal: 40, slopes: 8 },
  balanced: { landmarks: 8,  internal: 15, slopes: 4 },
  autonomy: { landmarks: 6,  internal: 6,  slopes: 3 },
};

type Caps = { landmarks: number; internal: number; slopes: number; contour?: ContourLevel };

function pickSilhouette(d: DrawingAnalysis, caps: Caps) {
  const lvl = caps.contour ?? "standard";
  return (d.silhouette_levels && d.silhouette_levels[lvl]) || d.silhouette || null;
}

/** SVG showing construction stages 0..stepIndex, current emphasised. */
export function buildConstructionSvg(d: DrawingAnalysis, stepIndex: number, caps: Caps): string {
  const W = d.image_width, H = d.image_height;
  const u = Math.max(W, H);
  const geom = { W, H, u, sw: u * 0.004, r: u * 0.008 };
  const parts: string[] = [];
  d.construction_order.forEach((s, i) => {
    if (i > stepIndex) return;
    parts.push(stageSvg(s, d, { ...geom, o: i < stepIndex ? 0.28 : 1, emph: i === stepIndex, caps }));
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" `
       + `preserveAspectRatio="xMidYMid meet">${parts.join("")}</svg>`;
}

/** SVG for a single stage by id (used by lesson steps whose overlay names it). */
export function buildStageSvgById(d: DrawingAnalysis, stageId: string, caps: Caps): string {
  const idx = d.construction_order.findIndex(s => s.id === stageId);
  return buildConstructionSvg(d, idx < 0 ? d.construction_order.length - 1 : idx, caps);
}

type Ctx = { W: number; H: number; u: number; sw: number; r: number; o: number; emph: boolean; caps: Caps };

function stageSvg(s: DrawStage, d: DrawingAnalysis, ctx: Ctx): string {
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
      if (d.occupied_area.length >= 3) p.push(poly(d.occupied_area, cur(C.sage), sw, C.sage));
      break;
    case "landmarks": {
      const shown = d.landmarks
        .filter(l => ["widest_point", "narrowest_point", "major_corner"].includes(l.category))
        .sort((a, z) => z.importance - a.importance).slice(0, caps.landmarks);
      shown.forEach(l => p.push(dot(l.x, l.y, cur(C.accent))));
      break;
    }
    case "axis":
      if (d.main_axis) p.push(line(d.main_axis.start, d.main_axis.end, cur(C.accent), sw * 1.3));
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
    case "silhouette": {
      const sil = pickSilhouette(d, caps);
      if (sil && sil.points.length >= 2) p.push(poly(sil.points, cur(C.ink), sw * 1.4));
      break;
    }
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
    case "shadow_line":
      // Tonal outlines — the classical "shadow line": value-zone boundaries
      // drawn ON the drawing so the block-in fills ready-made shapes.
      (d.tonal_paths ?? []).forEach(tp => {
        if (tp.points.length >= 3)
          p.push(poly(tp.points, cur(C.cool), sw * 0.9, "none", `${sw * 2.2} ${sw * 1.2}`));
      });
      break;
    case "checkpoint": {
      const silC = pickSilhouette(d, caps);
      if (silC) p.push(poly(silC.points, C.ink, sw * 1.4));
      (d.tonal_paths ?? []).forEach(tp => {
        if (tp.points.length >= 3)
          p.push(poly(tp.points, C.cool, sw * 0.7, "none", `${sw * 2.2} ${sw * 1.2}`));
      });
      break;
    }
  }
  return p.join("");
}
