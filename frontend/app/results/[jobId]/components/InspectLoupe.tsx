"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────
// Structurally compatible with the entries in `manifest.palette` — we only rely
// on the fields we read here, so richer palette objects pass through unchanged.
export type PaletteEntry = {
  base_rgb: [number, number, number];
  name: string;
  mixing?: { text?: string } | null;
};

type Sample = {
  rgb: [number, number, number];
  hex: string;
  valuePct: number;         // 0-100 perceptual value (luminance)
  valueLabel: string;       // e.g. "a low midtone"
  grey: string;             // css rgb() of the isolated grey chip
  temperature: "warm" | "cool" | "neutral";
  tempDetail: string;       // short qualifier, e.g. "leaning yellow"
  nearest: PaletteEntry | null;
  mix: string | null;       // mixing recipe text for the nearest palette entry
  hint: string;             // one-line teaching hint
  // Position of the pointer relative to the wrapper (px), for panel placement.
  x: number;
  y: number;
  // Natural-image coordinates of the sampled point, for the zoom crop.
  natX: number;
  natY: number;
};

// ── Colour maths (all deterministic, client-side) ─────────────────────────────
function luminance(r: number, g: number, b: number): number {
  return 0.299 * r + 0.587 * g + 0.114 * b; // 0-255
}

function toHex(r: number, g: number, b: number): string {
  const h = (n: number) => Math.round(n).toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}

// sRGB → CIE L*a*b* (D65). We only need a* and b* for temperature.
function rgbToLab(r: number, g: number, b: number): [number, number, number] {
  const lin = (c: number) => {
    c /= 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  const R = lin(r), G = lin(g), B = lin(b);
  // to XYZ (D65)
  let X = R * 0.4124 + G * 0.3576 + B * 0.1805;
  let Y = R * 0.2126 + G * 0.7152 + B * 0.0722;
  let Z = R * 0.0193 + G * 0.1192 + B * 0.9505;
  // normalise by white point
  X /= 0.95047; Y /= 1.0; Z /= 1.08883;
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const fx = f(X), fy = f(Y), fz = f(Z);
  const L = 116 * fy - 16;
  const a = 500 * (fx - fy);
  const bb = 200 * (fy - fz);
  return [L, a, bb];
}

function classifyValue(pct: number): string {
  if (pct < 12) return "a deep dark";
  if (pct < 30) return "a shadow";
  if (pct < 45) return "a low midtone";
  if (pct < 60) return "a midtone";
  if (pct < 75) return "a high midtone";
  if (pct < 90) return "a light";
  return "a highlight";
}

function classifyTemperature(
  a: number,
  b: number
): { temperature: Sample["temperature"]; detail: string } {
  const chroma = Math.hypot(a, b);
  if (chroma < 10) return { temperature: "neutral", detail: "nearly greyed" };
  // b* is the yellow(+)/blue(−) axis; a* is the red(+)/green(−) axis.
  if (b > 6) return { temperature: "warm", detail: a > 6 ? "red-orange" : "leaning yellow" };
  if (b < -6) return { temperature: "cool", detail: a > 6 ? "violet" : "leaning blue" };
  // ambiguous yellow/blue — fall back to the red/green axis
  if (a > 8) return { temperature: "warm", detail: "reddish" };
  if (a < -8) return { temperature: "cool", detail: "greenish" };
  return { temperature: "neutral", detail: "balanced" };
}

function teachingHint(pct: number, temp: Sample["temperature"]): string {
  if (pct < 30 && temp === "warm")
    return "A warm dark — glaze it with transparent earths, keep it luminous, never dead black.";
  if (pct < 30)
    return "Your darkest notes live here — commit fully, weak darks flatten the whole study.";
  if (pct > 82 && temp === "cool")
    return "A cool light — a touch of white plus the faintest blue keeps it from going chalky.";
  if (pct > 82)
    return "A highlight — save your thickest, cleanest paint for these; place them last.";
  if (temp === "warm")
    return "Warm midtone — lean it toward the light; premix a slightly cooler version for its shadow.";
  if (temp === "cool")
    return "Cool midtone — reads as turning away from the light; keep it quieter than the lit planes.";
  return "A quiet neutral — let it rest so your saturated notes elsewhere can sing.";
}

function nearestPalette(
  rgb: [number, number, number],
  palette: PaletteEntry[] | undefined
): PaletteEntry | null {
  if (!palette || palette.length === 0) return null;
  let best: PaletteEntry | null = null;
  let bestD = Infinity;
  for (const p of palette) {
    if (!p.base_rgb) continue;
    const dr = rgb[0] - p.base_rgb[0];
    const dg = rgb[1] - p.base_rgb[1];
    const db = rgb[2] - p.base_rgb[2];
    const d = dr * dr + dg * dg + db * db; // squared RGB distance — no sqrt needed
    if (d < bestD) { bestD = d; best = p; }
  }
  return best;
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function InspectLoupe({
  imageUrl,
  palette,
  imgClassName = "w-full rounded-xl object-contain max-h-[520px]",
  alt = "Reference",
}: {
  imageUrl: string;
  palette?: PaletteEntry[];
  imgClassName?: string;
  alt?: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);   // offscreen sampling buffer
  const zoomRef = useRef<HTMLCanvasElement | null>(null);     // magnified crop display
  const rafRef = useRef<number | null>(null);
  const pendingRef = useRef<{ px: number; py: number } | null>(null);

  const [enabled, setEnabled] = useState(false);
  const [ready, setReady] = useState(false);
  const [blocked, setBlocked] = useState(false); // canvas tainted / CORS failure
  const [sample, setSample] = useState<Sample | null>(null);

  // Load the image into an offscreen canvas so its pixels are readable.
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setReady(false);
    setBlocked(false);
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (cancelled) return;
      try {
        const c = document.createElement("canvas");
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext("2d", { willReadFrequently: true });
        if (!ctx) { setBlocked(true); return; }
        ctx.drawImage(img, 0, 0);
        // Probe once — a tainted canvas throws here rather than at sample time.
        ctx.getImageData(0, 0, 1, 1);
        canvasRef.current = c;
        setReady(true);
      } catch {
        setBlocked(true);
      }
    };
    img.onerror = () => { if (!cancelled) setBlocked(true); };
    img.src = imageUrl;
    return () => { cancelled = true; };
  }, [enabled, imageUrl]);

  // Map a pointer position (relative to the wrapper) onto natural image
  // coordinates, accounting for object-contain letterboxing.
  const sampleAt = useCallback((px: number, py: number): Sample | null => {
    const canvas = canvasRef.current;
    const imgEl = imgRef.current;
    if (!canvas || !imgEl) return null;
    const natW = canvas.width, natH = canvas.height;
    const elW = imgEl.clientWidth, elH = imgEl.clientHeight;
    if (!natW || !natH || !elW || !elH) return null;

    // object-contain: the image is scaled to fit, centred, possibly letterboxed.
    const scale = Math.min(elW / natW, elH / natH);
    const renderW = natW * scale, renderH = natH * scale;
    const offX = (elW - renderW) / 2, offY = (elH - renderH) / 2;

    // Pointer relative to the image element (wrapper === image box here).
    const ix = px - offX, iy = py - offY;
    if (ix < 0 || iy < 0 || ix > renderW || iy > renderH) return null; // in letterbox

    const natX = Math.min(natW - 1, Math.max(0, Math.floor(ix / scale)));
    const natY = Math.min(natH - 1, Math.max(0, Math.floor(iy / scale)));

    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;

    // Average a ~7px patch for stability against noise/JPEG artefacts.
    const R = 3;
    const sx = Math.max(0, natX - R), sy = Math.max(0, natY - R);
    const sw = Math.min(natW - sx, R * 2 + 1), sh = Math.min(natH - sy, R * 2 + 1);
    let rSum = 0, gSum = 0, bSum = 0, n = 0;
    try {
      const data = ctx.getImageData(sx, sy, sw, sh).data;
      for (let i = 0; i < data.length; i += 4) {
        rSum += data[i]; gSum += data[i + 1]; bSum += data[i + 2]; n++;
      }
    } catch {
      setBlocked(true);
      return null;
    }
    if (n === 0) return null;
    const r = rSum / n, g = gSum / n, b = bSum / n;

    const lum = luminance(r, g, b);
    const valuePct = Math.round((lum / 255) * 100);
    const [, aStar, bStar] = rgbToLab(r, g, b);
    const { temperature, detail } = classifyTemperature(aStar, bStar);
    const nearest = nearestPalette([r, g, b], palette);
    const mix = nearest?.mixing?.text ?? null;
    const greyByte = Math.round(lum);

    return {
      rgb: [r, g, b],
      hex: toHex(r, g, b),
      valuePct,
      valueLabel: classifyValue(valuePct),
      grey: `rgb(${greyByte},${greyByte},${greyByte})`,
      temperature,
      tempDetail: detail,
      nearest,
      mix,
      hint: teachingHint(valuePct, temperature),
      x: px, y: py,
      natX, natY,
    };
  }, [palette]);

  // Throttle sampling to animation frames — one read per painted frame.
  const flush = useCallback(() => {
    rafRef.current = null;
    const p = pendingRef.current;
    if (!p) return;
    const s = sampleAt(p.px, p.py);
    if (s) setSample(s);
  }, [sampleAt]);

  const onMove = useCallback((clientX: number, clientY: number) => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const rect = wrap.getBoundingClientRect();
    pendingRef.current = { px: clientX - rect.left, py: clientY - rect.top };
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(flush);
  }, [flush]);

  useEffect(() => () => { if (rafRef.current != null) cancelAnimationFrame(rafRef.current); }, []);

  // Draw the magnified crop whenever the sample point changes.
  useEffect(() => {
    const zc = zoomRef.current, src = canvasRef.current;
    if (!zc || !src || !sample) return;
    const ctx = zc.getContext("2d");
    if (!ctx) return;
    const CROP = 26;              // source pixels around the point
    const D = zc.width;           // display size (square)
    const sx = Math.max(0, Math.min(src.width - CROP, sample.natX - CROP / 2));
    const sy = Math.max(0, Math.min(src.height - CROP, sample.natY - CROP / 2));
    ctx.imageSmoothingEnabled = true;
    try {
      ctx.clearRect(0, 0, D, D);
      ctx.drawImage(src, sx, sy, CROP, CROP, 0, 0, D, D);
    } catch { /* tainted — swatch fallback still shown */ }
    // crosshair
    ctx.strokeStyle = "rgba(255,255,255,0.9)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(D / 2, D / 2 - 7); ctx.lineTo(D / 2, D / 2 + 7);
    ctx.moveTo(D / 2 - 7, D / 2); ctx.lineTo(D / 2 + 7, D / 2);
    ctx.stroke();
    ctx.strokeStyle = "rgba(0,0,0,0.55)";
    ctx.strokeRect(D / 2 - 4, D / 2 - 4, 8, 8);
  }, [sample]);

  // Escape dismisses the loupe.
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setEnabled(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);

  // ── Panel placement — flip to keep it inside the wrapper ─────────────────────
  const PANEL_W = 248, PANEL_H = 250;
  let panelLeft = 0, panelTop = 0;
  if (sample && wrapRef.current) {
    const w = wrapRef.current.clientWidth, h = wrapRef.current.clientHeight;
    panelLeft = sample.x + 18;
    if (panelLeft + PANEL_W > w) panelLeft = sample.x - PANEL_W - 18;
    if (panelLeft < 0) panelLeft = Math.max(0, Math.min(w - PANEL_W, sample.x - PANEL_W / 2));
    panelTop = sample.y + 18;
    if (panelTop + PANEL_H > h) panelTop = Math.max(0, sample.y - PANEL_H - 18);
  }

  const tempColor = (t: Sample["temperature"]) =>
    t === "warm" ? "var(--accent)" : t === "cool" ? "var(--cool)" : "var(--text-dim)";

  return (
    <div>
      {/* Toggle chip — enabling the loupe never disturbs normal viewing */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <button
          type="button"
          className="chip"
          data-active={enabled}
          aria-pressed={enabled}
          onClick={() => { setEnabled(v => !v); setSample(null); }}
        >
          {enabled ? "Inspecting — click to stop" : "Inspect any point"}
        </button>
        {enabled && !blocked && (
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>
            Hover or tap the image to read its value, temperature &amp; mix.
          </span>
        )}
        {enabled && blocked && (
          <span className="text-xs" style={{ color: "var(--crimson)" }}>
            Can&apos;t read this image&apos;s pixels (cross-origin). Loupe unavailable.
          </span>
        )}
      </div>

      <div
        ref={wrapRef}
        className="relative"
        style={{ touchAction: enabled ? "none" : undefined, cursor: enabled && ready ? "crosshair" : undefined }}
        onMouseMove={enabled ? (e) => onMove(e.clientX, e.clientY) : undefined}
        onMouseLeave={enabled ? () => setSample(null) : undefined}
        onTouchMove={enabled ? (e) => { const t = e.touches[0]; if (t) onMove(t.clientX, t.clientY); } : undefined}
        onTouchStart={enabled ? (e) => { const t = e.touches[0]; if (t) onMove(t.clientX, t.clientY); } : undefined}
        onClick={enabled ? (e) => onMove(e.clientX, e.clientY) : undefined}
      >
        <img ref={imgRef} src={imageUrl} alt={alt} className={imgClassName} />

        {/* Live region for screen readers — announces the current reading */}
        <span className="sr-only" aria-live="polite">
          {sample
            ? `Value ${sample.valuePct} percent, ${sample.valueLabel}. ${sample.temperature}${sample.nearest ? `. Nearest palette colour ${sample.nearest.name}` : ""}.`
            : ""}
        </span>

        {/* Floating loupe panel */}
        {enabled && ready && sample && (
          <div
            role="dialog"
            aria-label="Colour inspection"
            className="panel absolute z-20 pointer-events-none"
            style={{ left: panelLeft, top: panelTop, width: PANEL_W, padding: 12 }}
          >
            <div className="flex items-center gap-3 mb-2">
              {/* Magnified crop — "see it better" */}
              <canvas
                ref={zoomRef}
                width={64}
                height={64}
                className="rounded-lg flex-shrink-0"
                style={{ width: 64, height: 64, border: "1px solid var(--border-strong)" }}
              />
              {/* Flat sampled swatch */}
              <div className="flex-shrink-0 rounded-lg"
                   style={{ width: 44, height: 44, background: `rgb(${sample.rgb.map(Math.round).join(",")})`, border: "1px solid var(--border-strong)" }} />
              <div className="min-w-0">
                <p className="font-display text-sm leading-tight" style={{ color: "var(--text)" }}>
                  {sample.hex.toUpperCase()}
                </p>
                <p className="text-xs" style={{ color: tempColor(sample.temperature) }}>
                  {sample.temperature}{sample.tempDetail ? ` · ${sample.tempDetail}` : ""}
                </p>
              </div>
            </div>

            {/* Value + isolated grey chip */}
            <div className="flex items-center gap-2 mb-2">
              <span className="rounded flex-shrink-0"
                    style={{ width: 18, height: 18, background: sample.grey, border: "1px solid var(--border)" }} />
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                value <strong style={{ color: "var(--text)" }}>{sample.valuePct}%</strong> ({sample.valueLabel})
              </p>
            </div>

            {/* Nearest palette colour + mix recipe */}
            {sample.nearest && (
              <div className="mb-2 pt-2" style={{ borderTop: "1px solid var(--border)" }}>
                <div className="flex items-center gap-2">
                  <span className="rounded flex-shrink-0"
                        style={{ width: 18, height: 18, background: `rgb(${sample.nearest.base_rgb.join(",")})`, border: "1px solid var(--border)" }} />
                  <p className="text-xs truncate" style={{ color: "var(--text)" }}>{sample.nearest.name}</p>
                </div>
                {sample.mix && (
                  <p className="text-xs mt-1" style={{ color: "var(--accent)" }}>
                    to mix: {sample.mix}
                  </p>
                )}
              </div>
            )}

            {/* Teaching hint */}
            <p className="text-xs leading-snug pt-2" style={{ color: "var(--text-dim)", borderTop: "1px solid var(--border)" }}>
              {sample.hint}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
