"use client";
import { type Manifest } from "../lib/manifest";

// ── Right-hand teaching column — accompanies the explorer/classic modes only.
// The lesson player and critique view carry their own teaching column.
export default function TeachingAside({
  manifest,
  setViewMode,
  setDetailLevel,
  setCompareMode,
}: {
  manifest: Manifest;
  setViewMode: (m: "hierarchical_lesson") => void;
  setDetailLevel: (n: number) => void;
  setCompareMode: (m: "analysis") => void;
}) {
  if (!manifest.input) return null;

  return (
    <aside className="w-72 flex-shrink-0 border-l overflow-y-auto hidden lg:block"
           style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
      <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
        <p className="text-xs font-semibold uppercase tracking-widest mb-1"
           style={{ color: "var(--accent)" }}>
          {manifest.input.medium.charAt(0).toUpperCase() + manifest.input.medium.slice(1)} · Lesson Steps
        </p>
        <p className="text-xs" style={{ color: "var(--text-dim)" }}>
          {manifest.image?.width} × {manifest.image?.height}px
        </p>
      </div>

      {/* Teaching stages — each backed by a real lesson_plan step when available */}
      {manifest?.teaching_stages && manifest.teaching_stages.length > 0 && (
        <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
          <p className="text-xs font-semibold uppercase tracking-widest mb-3"
             style={{ color: "var(--text-dim)" }}>Lesson stages</p>
          <div className="space-y-3">
            {manifest.teaching_stages.map(stage => {
              const step = manifest.lesson_plan?.find(s => s.order === stage.order);
              return (
                <div key={stage.order} className="flex gap-2">
                  <div className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold mt-0.5"
                       style={{ background: "var(--accent)", color: "var(--paper)" }}>
                    {stage.order}
                  </div>
                  <div>
                    <p className="text-xs font-semibold" style={{ color: "var(--text)" }}>
                      {stage.name}
                    </p>
                    <p className="text-xs mt-0.5 leading-relaxed" style={{ color: "var(--text-dim)" }}>
                      {stage.description}
                    </p>
                    {step && (
                      <button
                        onClick={() => {
                          setViewMode("hierarchical_lesson");
                          setDetailLevel(step.level);
                          setCompareMode("analysis");
                        }}
                        className="text-xs mt-1 underline"
                        style={{ color: "var(--accent)" }}>
                        View this step (Level {step.level}) →
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Teaching instructions */}
      {manifest?.teaching_instructions && Object.keys(manifest.teaching_instructions).length > 0 && (
        <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2"
             style={{ color: "var(--text-dim)" }}>Key principles</p>
          <div className="space-y-2">
            {Object.entries(manifest.teaching_instructions).map(([key, value]) => (
              <p key={key} className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>
                <span className="font-medium" style={{ color: "var(--accent)" }}>
                  {key.replace("_note", "").replace(/_/g, " ")}:
                </span>{" "}
                {value}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Value zones */}
      {manifest.value_zones && manifest.value_zones.length > 0 && (
        <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2"
             style={{ color: "var(--text-dim)" }}>Value zones</p>
          <div className="flex gap-1">
            {manifest.value_zones.map(z => (
              <div key={z.id} className="flex-1 flex flex-col items-center gap-1">
                <div className="w-full rounded" style={{ height: 24, background: `rgb(${z.grey_value},${z.grey_value},${z.grey_value})` }} />
                <p className="text-xs" style={{ color: "var(--text-dim)", fontSize: 9 }}>{z.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Full palette */}
      {manifest.palette && manifest.palette.length > 0 && (
        <div className="p-4">
          <p className="text-xs font-semibold uppercase tracking-widest mb-2"
             style={{ color: "var(--text-dim)" }}>Colour palette</p>
          <div className="space-y-2">
            {manifest.palette.slice(0, 16).map(c => (
              <div key={c.id} className="flex items-start gap-2">
                <div style={{
                  width: 24, height: 16, borderRadius: 3, flexShrink: 0, marginTop: 2,
                  background: `rgb(${c.base_rgb.join(",")})`,
                  border: "1px solid var(--border)",
                }} />
                <div className="min-w-0">
                  <span className="text-xs block truncate" style={{ color: "var(--text-dim)" }}>
                    {c.name} ({Math.round(c.area_fraction * 100)}%)
                  </span>
                  {c.mixing && (
                    <span className="text-[10px] block leading-snug" style={{ color: "var(--accent)" }}>
                      mix: {c.mixing.text}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}
