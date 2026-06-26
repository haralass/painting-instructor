"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Step labels for the progress display ─────────────────────────────────────
const STEP_LABELS: Record<string, string> = {
  loading:          "Loading image…",
  line_art:         "Drawing outlines…",
  notan:            "Mapping values…",
  color_temperature:"Analysing colour temperature…",
  color_palette:    "Extracting colour palette…",
  light_direction:  "Finding light source…",
  color_by_number:  "Building paint-by-numbers…",
  dot_to_dot:       "Placing structural dots…",
  hierarchical:     "Building hierarchical regions…",
  video:            "Rendering tutorial video…",
  pdf:              "Assembling PDF…",
  manifest:         "Writing manifest…",
  completed:        "Tutorial ready",
};

// ── Page labels for classic analysis outputs ──────────────────────────────────
const PAGE_LABELS: Record<string, { title: string; why: string; tip: string }> = {
  line_art: {
    title: "Line Art",
    why:   "Every painting starts with clear structure. These lines define the silhouette (thickest, most important), interior forms (medium weight), and background texture (lightest).",
    tip:   "Transfer these outlines to your canvas with light charcoal. Don't press hard — you'll erase them as you paint.",
  },
  notan: {
    title: "Value Study (Notan)",
    why:   "Notan is a Japanese design concept — before you touch colour, you must get your lights and darks right. A painting with correct values reads in black and white.",
    tip:   "Mix 3 values: darkest dark, mid grey, white. Fill the entire canvas with these before adding colour.",
  },
  color_temperature: {
    title: "Colour Temperature",
    why:   "Lit areas are warm (yellow/orange), shadows are cool (blue/purple). This is James Gurney's core principle. This map shows an approximation based on LAB b* + chroma.",
    tip:   "Premix a warm and a cool version of every colour. Lean lights warm, shadows cool.",
  },
  color_palette: {
    title: "Colour Palette",
    why:   "The dominant colours of your reference, sorted by area coverage. A limited palette forces harmony — mix from these rather than adding new tubes.",
    tip:   "Lay out this palette before you start. Only these colours — no extras.",
  },
  light_direction: {
    title: "Light & Shadow Zones",
    why:   "Gurney's 5 zones: Highlight → Halftone → Core Shadow → Reflected Light → Cast Shadow. The core shadow is your darkest paint.",
    tip:   "Position your actual light source to match this angle, or mentally commit to it and never change it.",
  },
  color_by_number: {
    title: "Paint by Numbers",
    why:   "Flat colour blocking is how every master painter starts a canvas. Fill the entire canvas before blending — if any white shows through, you cannot judge colour relationships.",
    tip:   "Block in flat colour before blending. Use a large flat brush, cover every zone completely.",
  },
  dot_to_dot: {
    title: "Structural Dots",
    why:   "These dots trace the most structurally significant edges. Connecting them in order builds your under-drawing.",
    tip:   "Connect these dots lightly with a pencil before painting. This is your structural under-drawing.",
  },
};

// ── Level labels for hierarchical detail ─────────────────────────────────────
const LEVEL_LABELS: Record<number, string> = {
  1: "Foundation",
  2: "Simplified",
  3: "Standard",
  4: "Detailed",
  5: "Full Reference",
};

const LAYER_KEYS = ["outlines", "regions", "values", "colours"] as const;
type LayerKey = typeof LAYER_KEYS[number];

const CLASSIC_PAGE_KEYS = [
  "line_art", "notan", "color_temperature", "color_palette",
  "light_direction", "color_by_number", "dot_to_dot",
];

type CompareMode = "analysis" | "reference" | "side_by_side" | "overlay";

// ── Types ─────────────────────────────────────────────────────────────────────
type JobStatus = {
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  step: string;
  message: string;
  result?: {
    manifest: string;
    pages: string[];
    video?: string;
    pdf?:   string;
  };
  error?: string;
};

type Manifest = {
  job_id: string;
  input: { medium: string; palette_size: number; detail_level: number; value_zones: number };
  image: { width: number; height: number };
  pages: string[];
  detail_levels: Record<string, {
    level: number; label: string;
    outlines: string; regions: string; values: string; colours: string;
  }>;
  palette: { id: number; name: string; base_rgb: [number,number,number]; area_fraction: number }[];
  colour_families: unknown[];
  value_zones: { id: number; label: string; grey_value: number }[];
  video?: string;
  pdf?: string;
};

type AnalysisPage = {
  key: string;
  url: string;
  title: string;
  why: string;
  tip: string;
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function absUrl(relPath: string | undefined | null): string {
  if (!relPath) return "";
  if (relPath.startsWith("http")) return relPath;
  return `${API}/${relPath.replace(/^\//, "")}`;
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [jobStatus,    setJobStatus]    = useState<JobStatus>({ status: "queued", progress: 0, step: "", message: "Waiting to start" });
  const [manifest,     setManifest]     = useState<Manifest | null>(null);
  const [classicPages, setClassicPages] = useState<AnalysisPage[]>([]);
  const [selected,     setSelected]     = useState<AnalysisPage | null>(null);
  const [whyOpen,      setWhyOpen]      = useState(false);

  // Hierarchical controls
  const [detailLevel,  setDetailLevel]  = useState(3);
  const [activeLayer,  setActiveLayer]  = useState<LayerKey>("outlines");
  const [compareMode,  setCompareMode]  = useState<CompareMode>("analysis");
  const [opacity,      setOpacity]      = useState(0.5);

  // Layer visibility toggles
  const [layerVis, setLayerVis] = useState<Record<LayerKey, boolean>>({
    outlines: true, regions: true, values: true, colours: true,
  });

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchManifest = useCallback(async (manifestUrl: string) => {
    try {
      const res = await fetch(absUrl(manifestUrl));
      if (res.ok) {
        const data: Manifest = await res.json();
        setManifest(data);

        const ps: AnalysisPage[] = (data.pages ?? []).map(p => {
          const key  = p.split("/").pop()?.replace(".png", "") ?? "";
          const meta = PAGE_LABELS[key] ?? { title: key, why: "", tip: "" };
          return { key, url: absUrl(p), ...meta };
        }).filter(p => CLASSIC_PAGE_KEYS.includes(p.key));
        setClassicPages(ps);
        if (ps.length > 0 && !selected) setSelected(ps[0]);

        // Set default detail level from input
        if (data.input?.detail_level) setDetailLevel(data.input.detail_level);
      }
    } catch { /* non-critical */ }
  }, [selected]);

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`${API}/jobs/${jobId}`);
      const data: JobStatus = await res.json();
      setJobStatus(data);

      if (data.status === "completed" && data.result?.manifest) {
        if (pollRef.current) clearInterval(pollRef.current);
        await fetchManifest(data.result.manifest);
      }
    } catch { /* backend unreachable */ }
  }, [jobId, fetchManifest]);

  useEffect(() => {
    poll();
    pollRef.current = setInterval(() => {
      setJobStatus(prev => {
        if (prev.status === "completed" || prev.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
        return prev;
      });
      poll();
    }, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [poll]);

  // ── Loading / Error states ─────────────────────────────────────────────────
  if (jobStatus.status !== "completed") {
    const isRunning = jobStatus.status === "queued" || jobStatus.status === "processing";
    return (
      <main className="min-h-screen flex flex-col items-center justify-center px-4"
            style={{ background: "var(--bg)" }}>
        <div className="text-center max-w-md">
          {isRunning && (
            <>
              <div className="text-5xl mb-6 animate-pulse">🎨</div>
              <h2 className="text-2xl font-bold mb-3" style={{ color: "var(--accent)" }}>
                Preparing your tutorial
              </h2>
              <p className="text-base mb-2" style={{ color: "var(--text)" }}>
                {STEP_LABELS[jobStatus.step] ?? jobStatus.message ?? "Processing…"}
              </p>
              <p className="text-sm mb-6" style={{ color: "var(--text-dim)" }}>
                {jobStatus.progress > 0 ? `${jobStatus.progress}% complete` : "Starting…"}
              </p>
              <div className="h-2 w-full rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
                <div className="h-full rounded-full transition-all duration-700"
                     style={{ background: "var(--accent)", width: `${Math.max(jobStatus.progress, 4)}%` }} />
              </div>
            </>
          )}
          {jobStatus.status === "failed" && (
            <>
              <div className="text-5xl mb-6">❌</div>
              <h2 className="text-2xl font-bold mb-2">Processing failed</h2>
              <p style={{ color: "var(--text-dim)" }}>{jobStatus.error ?? "Unknown error"}</p>
              <a href="/" className="mt-6 inline-block px-4 py-2 rounded-lg text-sm"
                 style={{ background: "var(--accent)", color: "#0f0e0d" }}>← Try again</a>
            </>
          )}
        </div>
      </main>
    );
  }

  // ── Results layout ─────────────────────────────────────────────────────────
  const videoUrl = manifest?.video ? absUrl(manifest.video) : absUrl(`/outputs/${jobId}/tutorial.mp4`);
  const pdfUrl   = manifest?.pdf   ? absUrl(manifest.pdf)   : absUrl(`/outputs/${jobId}/tutorial_book.pdf`);

  const currentLevelData = manifest?.detail_levels?.[String(detailLevel)];

  // URL for the currently selected hierarchical layer at the current detail level
  function levelLayerUrl(layer: LayerKey): string {
    if (!currentLevelData) return "";
    const p = currentLevelData[layer];
    return p ? absUrl(p) : "";
  }

  // What to show in the main canvas area
  function mainImageUrl(): string {
    if (selected && compareMode === "analysis") return selected.url;
    if (currentLevelData) return levelLayerUrl(activeLayer);
    return selected?.url ?? "";
  }

  return (
    <main className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>

      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0"
              style={{ borderColor: "var(--border)" }}>
        <a href="/" className="font-bold text-lg" style={{ color: "var(--accent)" }}>← New Tutorial</a>
        <div className="flex gap-2 text-sm">
          {manifest?.input && (
            <span className="px-3 py-1 rounded" style={{ background: "var(--surface)", color: "var(--text-dim)" }}>
              {manifest.input.medium} · {manifest.input.palette_size} colours · {manifest.input.value_zones} zones
            </span>
          )}
          <a href={pdfUrl} target="_blank" rel="noreferrer"
             className="px-4 py-2 rounded-lg border transition-colors"
             style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            Download PDF
          </a>
          <a href={videoUrl} download
             className="px-4 py-2 rounded-lg font-semibold"
             style={{ background: "var(--accent)", color: "#0f0e0d" }}>
            Download Video
          </a>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">

        {/* ── Left: classic analysis thumbnails ───────────────────────────── */}
        <nav className="w-44 flex-shrink-0 overflow-y-auto border-r p-2 space-y-1 hidden md:block"
             style={{ borderColor: "var(--border)" }}>
          <p className="text-xs font-semibold uppercase tracking-widest px-1 mb-2"
             style={{ color: "var(--text-dim)" }}>Analysis</p>
          {classicPages.map(p => (
            <button key={p.key}
                    onClick={() => { setSelected(p); setCompareMode("analysis"); setWhyOpen(false); }}
                    className="w-full text-left rounded-lg overflow-hidden border transition-colors"
                    style={{ borderColor: selected?.key === p.key && compareMode === "analysis" ? "var(--accent)" : "transparent" }}>
              <img src={p.url} alt={p.title} className="w-full object-cover" style={{ aspectRatio: "4/3" }} />
              <p className="text-xs px-2 py-1 truncate" style={{ color: "var(--text-dim)" }}>{p.title}</p>
            </button>
          ))}

          {/* Hierarchical palette preview */}
          {manifest?.palette && manifest.palette.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold uppercase tracking-widest px-1 mb-2"
                 style={{ color: "var(--text-dim)" }}>Palette</p>
              <div className="flex flex-wrap gap-1 px-1">
                {manifest.palette.slice(0, 20).map(c => (
                  <div key={c.id} title={c.name}
                       style={{
                         width: 18, height: 18, borderRadius: 3,
                         background: `rgb(${c.base_rgb.join(",")})`,
                         border: "1px solid rgba(255,255,255,0.1)",
                       }} />
                ))}
              </div>
            </div>
          )}
        </nav>

        {/* ── Centre: video + main image + controls ───────────────────────── */}
        <section className="flex-1 flex flex-col overflow-y-auto min-w-0">

          {/* Video */}
          <div className="p-4 border-b flex-shrink-0" style={{ borderColor: "var(--border)" }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-2"
               style={{ color: "var(--text-dim)" }}>Tutorial Video</p>
            <video src={videoUrl} controls className="w-full rounded-xl"
                   style={{ background: "#000", maxHeight: 380 }} />
          </div>

          {/* ── Hierarchical detail slider ──────────────────────────────── */}
          {manifest?.detail_levels && Object.keys(manifest.detail_levels).length > 0 && (
            <div className="p-4 border-b" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold uppercase tracking-widest"
                   style={{ color: "var(--text-dim)" }}>Detail level</p>
                <span className="text-sm font-medium" style={{ color: "var(--accent)" }}>
                  {LEVEL_LABELS[detailLevel] ?? `Level ${detailLevel}`}
                </span>
              </div>
              <input type="range" min={1} max={5} step={1} value={detailLevel}
                     onChange={e => setDetailLevel(Number(e.target.value))}
                     className="w-full accent-yellow-600" />
              <div className="flex justify-between text-xs mt-1" style={{ color: "var(--text-dim)" }}>
                <span>Foundation</span><span>Full Reference</span>
              </div>

              {/* Layer toggle buttons */}
              <div className="flex gap-2 mt-3 flex-wrap">
                {LAYER_KEYS.map(k => (
                  <button key={k}
                          onClick={() => { setActiveLayer(k); setCompareMode("analysis"); setSelected(null); }}
                          className="px-3 py-1 rounded border text-xs transition-colors"
                          style={{
                            background:  (activeLayer === k && compareMode !== "analysis") || (selected === null && activeLayer === k)
                                           ? "var(--accent)" : "var(--surface)",
                            color:       (activeLayer === k && !selected) ? "#0f0e0d" : "var(--text)",
                            borderColor: "var(--border)",
                          }}>
                    {k.charAt(0).toUpperCase() + k.slice(1)}
                  </button>
                ))}
              </div>

              {/* Compare mode */}
              <div className="flex gap-2 mt-2 flex-wrap">
                {(["analysis", "reference", "side_by_side", "overlay"] as CompareMode[]).map(m => (
                  <button key={m}
                          onClick={() => setCompareMode(m)}
                          className="px-3 py-1 rounded border text-xs transition-colors"
                          style={{
                            background:  compareMode === m ? "var(--accent)" : "var(--surface)",
                            color:       compareMode === m ? "#0f0e0d"       : "var(--text-dim)",
                            borderColor: "var(--border)",
                          }}>
                    {m === "analysis"    ? "Analysis"
                   : m === "reference"  ? "Reference"
                   : m === "side_by_side" ? "Side by Side"
                   : "Overlay"}
                  </button>
                ))}
                {compareMode === "overlay" && (
                  <div className="flex items-center gap-2 ml-2">
                    <span className="text-xs" style={{ color: "var(--text-dim)" }}>Opacity</span>
                    <input type="range" min={0} max={1} step={0.05} value={opacity}
                           onChange={e => setOpacity(Number(e.target.value))}
                           style={{ width: 80 }} className="accent-yellow-600" />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Main image display ──────────────────────────────────────── */}
          <div className="p-4 flex-1">
            <ImageDisplay
              compareMode={compareMode}
              analysisUrl={selected ? selected.url : levelLayerUrl(activeLayer)}
              referenceUrl={absUrl(`/outputs/${jobId}/line_art.png`)}
              opacity={opacity}
              levelUrl={levelLayerUrl(activeLayer)}
              title={selected ? selected.title : (currentLevelData?.label ?? "")}
            />

            {/* Classic page WHY explanation */}
            {selected && compareMode === "analysis" && (
              <div className="mt-3 flex items-center gap-2">
                <button onClick={() => setWhyOpen(!whyOpen)}
                        className="px-3 py-1 rounded-lg border text-sm transition-colors"
                        style={{
                          borderColor: whyOpen ? "var(--accent)" : "var(--border)",
                          color:       whyOpen ? "var(--accent)" : "var(--text-dim)",
                        }}>
                  WHY? →
                </button>
                {whyOpen && (
                  <div className="flex-1 p-3 rounded-lg text-sm" style={{ background: "var(--surface)" }}>
                    <p className="mb-2" style={{ color: "var(--text)" }}>{selected.why}</p>
                    <p className="text-xs" style={{ color: "var(--accent)" }}>→ {selected.tip}</p>
                  </div>
                )}
              </div>
            )}

            {/* Mobile thumbnail strip */}
            <div className="flex gap-2 mt-4 overflow-x-auto pb-2 md:hidden">
              {classicPages.map(p => (
                <button key={p.key}
                        onClick={() => { setSelected(p); setCompareMode("analysis"); }}
                        className="flex-shrink-0 rounded overflow-hidden border"
                        style={{ borderColor: selected?.key === p.key ? "var(--accent)" : "var(--border)" }}>
                  <img src={p.url} alt={p.title} className="h-16 w-20 object-cover" />
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* ── Right: teaching instructions panel ──────────────────────── */}
        {manifest?.input && (
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
                <div className="space-y-1">
                  {manifest.palette.slice(0, 16).map(c => (
                    <div key={c.id} className="flex items-center gap-2">
                      <div style={{
                        width: 24, height: 16, borderRadius: 3, flexShrink: 0,
                        background: `rgb(${c.base_rgb.join(",")})`,
                        border: "1px solid rgba(255,255,255,0.1)",
                      }} />
                      <span className="text-xs truncate" style={{ color: "var(--text-dim)" }}>
                        {c.name} ({Math.round(c.area_fraction * 100)}%)
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </aside>
        )}
      </div>
    </main>
  );
}

// ── Image display with comparison modes ───────────────────────────────────────
function ImageDisplay({
  compareMode,
  analysisUrl,
  referenceUrl,
  opacity,
  levelUrl,
  title,
}: {
  compareMode:  CompareMode;
  analysisUrl:  string;
  referenceUrl: string;
  opacity:      number;
  levelUrl:     string;
  title:        string;
}) {
  if (!analysisUrl) return (
    <div className="rounded-xl flex items-center justify-center" style={{ minHeight: 300, background: "var(--surface)" }}>
      <p style={{ color: "var(--text-dim)" }}>No image available</p>
    </div>
  );

  if (compareMode === "reference") {
    return (
      <div>
        <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>Reference photo</p>
        <img src={referenceUrl} alt="Reference" className="w-full rounded-xl object-contain max-h-[520px]" />
      </div>
    );
  }

  if (compareMode === "side_by_side") {
    return (
      <div>
        <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>{title} · Reference</p>
        <div className="flex gap-2">
          <img src={analysisUrl}  alt="Analysis"  className="flex-1 rounded-xl object-contain max-h-[480px]" />
          <img src={referenceUrl} alt="Reference" className="flex-1 rounded-xl object-contain max-h-[480px]" />
        </div>
      </div>
    );
  }

  if (compareMode === "overlay") {
    return (
      <div>
        <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>{title} · overlay at {Math.round(opacity * 100)}%</p>
        <div className="relative rounded-xl overflow-hidden" style={{ maxHeight: 520 }}>
          <img src={referenceUrl} alt="Reference" className="w-full object-contain" />
          <img src={analysisUrl} alt="Analysis" className="absolute inset-0 w-full object-contain"
               style={{ opacity }} />
        </div>
      </div>
    );
  }

  // default: "analysis"
  return (
    <div>
      {title && <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>{title}</p>}
      <img src={analysisUrl} alt={title || "Analysis"} className="w-full rounded-xl object-contain max-h-[520px]" />
    </div>
  );
}
