"use client";
import { useState, useRef } from "react";
import { API, absUrl } from "../lib/manifest";

// ── Critique panel — upload your attempt, get localised feedback ─────────────
type CritiqueResult = {
  scores: { overall: number; values: number; colour: number; structure: number };
  feedback: { kind: string; area: string; message: string; tip: string; severity: number }[];
  first_fix: string;
  assets: { overlay: string; side_by_side: string };
  attempt: number;
  attempt_image?: string;
};

const KIND_COLORS: Record<string, string> = {
  value:       "#b4511f",
  temperature: "#9d2f2f",
  saturation:  "#3e5c76",
  structure:   "#6f7d5c",
};

export default function CritiquePanel({ jobId, referenceUrl }: { jobId: string; referenceUrl: string }) {
  const [busy,   setBusy]   = useState(false);
  const [error,  setError]  = useState<string | null>(null);
  const [result, setResult] = useState<CritiqueResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function upload(f: File) {
    if (!f.type.startsWith("image/")) { setError("Please upload an image of your painting."); return; }
    setBusy(true); setError(null);
    try {
      const form = new FormData();
      form.append("file", f);
      const res = await fetch(`${API}/jobs/${jobId}/critique`, { method: "POST", body: form });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Server error: ${res.status}`);
      }
      setResult(await res.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed. Is the backend running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-4xl">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
          Critique {result ? `· attempt ${result.attempt}` : ""}
        </p>
        <h2 className="text-xl font-bold mb-1" style={{ color: "var(--text)" }}>
          Photograph your painting and upload it
        </h2>
        <p className="text-sm" style={{ color: "var(--text-dim)" }}>
          It is compared against the reference — values, colour temperature, saturation and structure,
          each localised to an area of the picture. Even light, no glare, camera square to the surface.
        </p>
      </div>

      <div
        onClick={() => !busy && inputRef.current?.click()}
        className="rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-colors"
        style={{ borderColor: "var(--border)", background: "var(--surface)", opacity: busy ? 0.6 : 1 }}
      >
        <p className="text-sm font-medium" style={{ color: "var(--text)" }}>
          {busy ? "Comparing against the reference…" : result ? "Upload another attempt" : "Click to upload your attempt"}
        </p>
        <input ref={inputRef} type="file" accept="image/*" className="hidden"
               onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
      </div>

      {error && (
        <p className="text-sm px-4 py-3 rounded-lg" style={{ background: "rgba(157,47,47,0.1)", color: "var(--crimson)" }}>
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-5 layer-transition">

          {/* Scores */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {([["Overall", result.scores.overall], ["Values", result.scores.values],
               ["Colour", result.scores.colour], ["Structure", result.scores.structure]] as const
            ).map(([label, score]) => (
              <div key={label} className="rounded-xl p-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                <p className="text-xs mb-1" style={{ color: "var(--text-dim)" }}>{label}</p>
                <p className="text-2xl font-bold" style={{ color: score >= 80 ? "var(--accent)" : score >= 55 ? "var(--text)" : "var(--crimson)" }}>
                  {Math.round(score)}
                </p>
                <div className="h-1 rounded-full mt-2 overflow-hidden" style={{ background: "var(--border)" }}>
                  <div className="h-full rounded-full" style={{ width: `${score}%`, background: "var(--accent)" }} />
                </div>
              </div>
            ))}
          </div>

          {/* First fix */}
          <div className="rounded-xl p-4" style={{ background: "rgba(180,81,31,0.07)", border: "1px solid rgba(180,81,31,0.28)" }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
              Fix this first
            </p>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{result.first_fix}</p>
          </div>

          {/* Overlay + reference */}
          <div className="grid md:grid-cols-2 gap-3">
            <div>
              <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>
                Your attempt — tinted where the values drift, circled where it matters most
              </p>
              <img src={absUrl(result.assets.overlay)} alt="Critique overlay" className="w-full rounded-xl" />
            </div>
            <div>
              <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>Reference</p>
              <img src={referenceUrl} alt="Reference" className="w-full rounded-xl object-contain" />
            </div>
          </div>

          {/* Feedback list */}
          {result.feedback.length > 0 ? (
            <div className="space-y-2">
              {result.feedback.map((f, i) => (
                <div key={i} className="rounded-xl p-3 flex gap-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
                  <span className="flex-shrink-0 mt-0.5 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                        style={{ background: `${KIND_COLORS[f.kind] ?? "#6f6655"}22`, color: KIND_COLORS[f.kind] ?? "#6f6655",
                                 border: `1px solid ${KIND_COLORS[f.kind] ?? "#6f6655"}55` }}>
                    {f.kind}
                  </span>
                  <div>
                    <p className="text-sm" style={{ color: "var(--text)" }}>{f.message}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--accent)" }}>→ {f.tip}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>
              Nothing above tolerance — this attempt tracks the reference well.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
