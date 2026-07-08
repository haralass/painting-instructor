"use client";
import { useEffect, useRef, useState, useCallback } from "react";

// ── Squint Simulator ─────────────────────────────────────────────────────────
// Learn to SEE values. Squinting is how painters kill detail and group the
// picture into a few big value masses. Here it becomes a draggable control:
// drag right and the reference progressively blurs (Gaussian) AND posterises
// (luminance quantised to N bands, N dropping from many → 2), collapsing the
// image into its underlying notan. All local, on a <canvas>, no backend.

type SquintSimulatorProps = {
  referenceUrl: string;
  // Optional value-study / notan asset URL from the manifest, used by the
  // "reveal the true notan" button for a side-by-side sanity check.
  notanUrl?: string;
};

// The slider (0→1) is mapped to a number of value groups. At 0 we leave the
// image untouched (many bands / full detail); as it rises we drop toward the
// classic 2–3 mass notan. Discrete steps so the caption and band count feel
// deliberate rather than continuous mush.
const MAX_BANDS = 8; // treated as "no quantisation" at the low end
function bandsForSquint(t: number): number {
  // 0 → 8 (off), then 6, 5, 4, 3, and 2 at the far right.
  if (t < 0.12) return MAX_BANDS;
  if (t < 0.30) return 6;
  if (t < 0.48) return 5;
  if (t < 0.66) return 4;
  if (t < 0.84) return 3;
  return 2;
}

function captionForBands(bands: number): string {
  switch (bands) {
    case MAX_BANDS: return "Eyes wide open — every detail is still shouting for attention.";
    case 6:         return "A gentle squint. Fine texture starts dissolving into shapes.";
    case 5:         return "Half-closed. Small forms are merging into their neighbours.";
    case 4:         return "Squinting now — four broad masses carry the whole picture.";
    case 3:         return "Almost shut. Three values: your lights, your mids, your darks.";
    default:        return "Squint harder — can you see just 2 masses? Pure light and shadow.";
  }
}

export default function SquintSimulator({ referenceUrl, notanUrl }: SquintSimulatorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const [squint, setSquint] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [showNotan, setShowNotan] = useState(false);

  const bands = bandsForSquint(squint);

  // ── Load the reference image once (CORS-enabled so we can read pixels) ──────
  useEffect(() => {
    if (!referenceUrl) { setFailed(true); return; }
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => { imgRef.current = img; setLoaded(true); };
    img.onerror = () => setFailed(true);
    img.src = referenceUrl;
    return () => { img.onload = null; img.onerror = null; };
  }, [referenceUrl]);

  // ── The squint render: blur + luminance quantisation ────────────────────────
  const render = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;

    // Fit the image into a bounded canvas, preserving aspect ratio.
    const MAX_W = 720;
    const scale = Math.min(1, MAX_W / img.naturalWidth);
    const w = Math.max(1, Math.round(img.naturalWidth * scale));
    const h = Math.max(1, Math.round(img.naturalHeight * scale));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }

    // 1) Gaussian blur — scaled by the slider. The canvas `filter` gives us a
    //    real Gaussian for free; radius grows with how hard we squint.
    const blurPx = squint * Math.max(w, h) * 0.028; // ~0 → ~20px on a 720px canvas
    ctx.filter = blurPx > 0.2 ? `blur(${blurPx.toFixed(1)}px)` : "none";
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    ctx.filter = "none";

    // 2) Value quantisation (posterise on luminance). Read the blurred pixels,
    //    snap each pixel's luminance to one of `bands` grey levels. We stay in
    //    greyscale so the tool is unambiguously about VALUE, not colour — which
    //    is the whole point of a notan.
    if (bands < MAX_BANDS) {
      const frame = ctx.getImageData(0, 0, w, h);
      const d = frame.data;
      const step = 255 / (bands - 1);
      for (let i = 0; i < d.length; i += 4) {
        // Rec. 601 luma — matches how the eye weights the channels.
        const lum = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        const q = Math.round(Math.round(lum / step) * step);
        d[i] = d[i + 1] = d[i + 2] = q;
      }
      ctx.putImageData(frame, 0, 0);
    }
  }, [squint, bands]);

  useEffect(() => { if (loaded) render(); }, [loaded, render]);

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-3xl">
      {/* ── Heading ─────────────────────────────────────────────────────── */}
      <div>
        <p className="eyebrow mb-1">Squint Simulator</p>
        <h2 className="text-xl font-bold font-display mb-1" style={{ color: "var(--text)" }}>
          Learn to <em style={{ color: "var(--accent)" }}>see values</em>
        </h2>
        <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>
          Squinting is how painters throw away detail and read the picture as a handful of
          big value masses. Drag the control — the reference blurs and collapses into fewer
          and fewer values, revealing the notan underneath.
        </p>
      </div>

      {/* ── Canvas stage ────────────────────────────────────────────────── */}
      <div className="panel p-3 relative overflow-hidden" style={{ borderRadius: 18 }}>
        {failed ? (
          <div className="flex items-center justify-center" style={{ minHeight: 200 }}>
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>
              Could not load the reference image.
            </p>
          </div>
        ) : (
          <>
            <canvas
              ref={canvasRef}
              className="w-full h-auto rounded-xl block"
              style={{ background: "var(--surface-2)", opacity: loaded ? 1 : 0.35, transition: "opacity 0.3s ease" }}
              aria-label={`Reference image squinted to ${bands >= MAX_BANDS ? "full detail" : `${bands} value groups`}`}
              role="img"
            />
            {showNotan && notanUrl && (
              <img
                src={notanUrl}
                alt="True value study (notan)"
                className="absolute inset-3 w-[calc(100%-1.5rem)] h-[calc(100%-1.5rem)] object-contain rounded-xl layer-transition"
                style={{ background: "var(--surface-2)" }}
              />
            )}
          </>
        )}
      </div>

      {/* ── Value-group readout ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <p className="label-xs mb-0.5">Value groups</p>
          <p className="text-3xl font-bold font-display" style={{ color: "var(--accent)" }}>
            {bands >= MAX_BANDS ? "Full detail" : bands}
          </p>
        </div>
        {/* Swatch strip — a live legend of the current value bands */}
        <div className="flex gap-1" aria-hidden="true">
          {Array.from({ length: bands >= MAX_BANDS ? 6 : bands }).map((_, i, arr) => {
            const g = arr.length === 1 ? 0 : Math.round((i / (arr.length - 1)) * 255);
            return (
              <div
                key={i}
                style={{
                  width: 26, height: 26, borderRadius: 6,
                  background: `rgb(${g},${g},${g})`,
                  border: "1px solid var(--border)",
                }}
              />
            );
          })}
        </div>
      </div>

      {/* ── The squint slider ───────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label htmlFor="squint-slider" className="label-xs">Eyes open</label>
          <span className="label-xs">Squinting hard</span>
        </div>
        <input
          id="squint-slider"
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={squint}
          onChange={e => setSquint(parseFloat(e.target.value))}
          className="w-full"
          aria-label="Squint amount"
          aria-valuetext={bands >= MAX_BANDS ? "full detail" : `${bands} value groups`}
        />
      </div>

      {/* ── Caption ─────────────────────────────────────────────────────── */}
      <p className="text-sm leading-relaxed px-4 py-3 rounded-xl"
         style={{ background: "rgba(180,81,31,0.07)", border: "1px solid rgba(180,81,31,0.22)", color: "var(--text)" }}>
        {captionForBands(bands)}
      </p>

      {/* ── Reveal true notan (only when the manifest exposes one) ──────── */}
      {notanUrl && (
        <button
          type="button"
          onClick={() => setShowNotan(v => !v)}
          className="chip"
          data-active={showNotan}
          aria-pressed={showNotan}
        >
          {showNotan ? "Hide the true 3-value notan" : "Reveal the true 3-value notan"}
        </button>
      )}
    </div>
  );
}
