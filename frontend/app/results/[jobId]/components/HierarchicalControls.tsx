"use client";
import {
  LEVEL_LABELS, LAYER_LABELS, OUTLINE_SUBLAYER_LABELS,
  type Manifest, type CompareMode,
} from "../lib/manifest";

// ── Hierarchical detail slider, layer/sublayer toggles and compare-mode row ──
// All display state lives in the parent so it can drive the image composition;
// this component is the presentational controls surface for that state.
export default function HierarchicalControls({
  manifest,
  detailLevel,
  setDetailLevel,
  setViewMode,
  layers,
  toggleLayer,
  hasEdgeMaps,
  outlineSublayers,
  toggleSublayer,
  compareMode,
  setCompareMode,
  opacity,
  setOpacity,
}: {
  manifest: Manifest;
  detailLevel: number;
  setDetailLevel: (n: number) => void;
  setViewMode: (m: "hierarchical_lesson") => void;
  layers: Record<string, boolean>;
  toggleLayer: (key: string) => void;
  hasEdgeMaps: boolean;
  outlineSublayers: Record<string, boolean>;
  toggleSublayer: (key: string) => void;
  compareMode: CompareMode;
  setCompareMode: (m: CompareMode) => void;
  opacity: number;
  setOpacity: (n: number) => void;
}) {
  return (
    <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold uppercase tracking-widest"
           style={{ color: "var(--text-dim)" }}>Detail level</p>
        <span className="text-sm font-medium" style={{ color: "var(--accent)" }}>
          {LEVEL_LABELS[detailLevel] ?? `Level ${detailLevel}`}
        </span>
      </div>
      <input type="range" min={1} max={5} step={1} value={detailLevel}
             onChange={e => { setDetailLevel(Number(e.target.value)); setViewMode("hierarchical_lesson"); }}
             className="w-full accent-orange-700" />
      <div className="flex justify-between text-xs mt-1" style={{ color: "var(--text-dim)" }}>
        <span>{LEVEL_LABELS[1]}</span><span>{LEVEL_LABELS[5]}</span>
      </div>

      {/* Independent layer toggles */}
      <div className="flex gap-2 mt-3 flex-wrap">
        {Object.entries(layers).map(([key, vis]) => (
          <button
            key={key}
            onClick={() => { toggleLayer(key); setViewMode("hierarchical_lesson"); }}
            style={{
              background:   vis ? "var(--accent)" : "var(--surface)",
              color:        vis ? "var(--paper)"       : "var(--text)",
              border:       `1px solid ${vis ? "var(--accent)" : "var(--border)"}`,
              padding:      "6px 14px",
              borderRadius: 8,
              fontSize:     13,
              fontWeight:   500,
              cursor:       "pointer",
            }}
          >
            {vis ? "✓ " : ""}{LAYER_LABELS[key] ?? key}
          </button>
        ))}
      </div>

      {/* A4: Individual outline sublayer toggles — only when edge_maps available */}
      {hasEdgeMaps && layers.outlines && (
        <div className="mt-2">
          <p className="text-xs mb-1" style={{ color: "var(--text-dim)" }}>Outline sublayers:</p>
          <div className="flex gap-1.5 flex-wrap">
            {Object.entries(outlineSublayers).map(([key, vis]) => (
              <button
                key={key}
                onClick={() => toggleSublayer(key)}
                style={{
                  background:   vis ? "var(--accent)" : "var(--surface)",
                  color:        vis ? "var(--paper)"       : "var(--text-dim)",
                  border:       `1px solid ${vis ? "var(--accent)" : "var(--border)"}`,
                  padding:      "4px 10px",
                  borderRadius: 6,
                  fontSize:     12,
                  cursor:       "pointer",
                }}
              >
                {OUTLINE_SUBLAYER_LABELS[key] ?? key}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Background/texture analysis indicators */}
      <div className="flex gap-3 mt-1">
        {manifest?.input?.texture_detail !== undefined && (
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>
            Texture: <span style={{ color: manifest.input.texture_detail ? "var(--accent)" : "var(--text-dim)" }}>
              {manifest.input.texture_detail ? "on" : "off"}
            </span>
          </span>
        )}
        {manifest?.input?.background_detail !== undefined && (
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>
            Background: <span style={{ color: manifest.input.background_detail ? "var(--accent)" : "var(--text-dim)" }}>
              {manifest.input.background_detail ? "on" : "off"}
            </span>
          </span>
        )}
      </div>

      {/* Compare mode */}
      <div className="flex gap-2 mt-2 flex-wrap">
        {(["analysis", "reference", "overlay", "side_by_side", "split"] as CompareMode[]).map(m => (
          <button key={m}
                  onClick={() => setCompareMode(m)}
                  className="px-3 py-1 rounded border text-xs transition-colors"
                  style={{
                    background:  compareMode === m ? "var(--accent)" : "var(--surface)",
                    color:       compareMode === m ? "var(--paper)"       : "var(--text-dim)",
                    borderColor: "var(--border)",
                  }}>
            {m === "analysis"    ? "Analysis"
           : m === "reference"  ? "Reference"
           : m === "side_by_side" ? "Side by Side"
           : m === "split"      ? "Before/After"
           : "Overlay"}
          </button>
        ))}
        {compareMode === "overlay" && (
          <div className="flex items-center gap-2 ml-2">
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>Opacity</span>
            <input type="range" min={0} max={1} step={0.05} value={opacity}
                   onChange={e => setOpacity(Number(e.target.value))}
                   style={{ width: 80 }} className="accent-orange-700" />
          </div>
        )}
      </div>
    </div>
  );
}
