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

const LAYER_LABELS: Record<string, string> = {
  outlines: "Outlines",
  values:   "Values",
  colours:  "Colours",
  regions:  "Regions",
};

// A4: Individual outline sublayer labels
const OUTLINE_SUBLAYER_LABELS: Record<string, string> = {
  primary:    "Primary",
  secondary:  "Secondary",
  decorative: "Decorative",
  texture:    "Texture",
};

const CLASSIC_PAGE_KEYS = [
  "line_art", "notan", "color_temperature", "color_palette",
  "light_direction", "color_by_number", "dot_to_dot",
];

type CompareMode = "analysis" | "reference" | "side_by_side" | "overlay";

// ── Types ─────────────────────────────────────────────────────────────────────
type JobStatus = {
  status: "queued" | "processing" | "completed" | "completed_with_warnings" | "failed";
  progress: number;
  step: string;
  message: string;
  analysis_ready?: boolean;  // A3: true when preliminary manifest is available
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
  input: {
    medium: string;
    palette_size: number;
    initial_view_level: number;
    value_zones: number;
    region_complexity?: number;
    background_detail?: boolean;
    texture_detail?: boolean;
  };
  image: { width: number; height: number };
  reference?: string;
  pages: string[];
  detail_levels: Record<string, {
    level: number; label: string;
    outlines: string; regions: string; values: string; colours: string;
    edge_maps?: Record<string, string>;  // level-aware sublayers — NOT the same as the top-level edge_maps below
  }>;
  edge_maps?: Record<string, string>;  // global, non-level-filtered — "primary"|"secondary"|"decorative"|"texture" → rel path
  outline_composites?: Record<string, string>;  // global (non-level-filtered) outline composites
  palette: { id: number; name: string; base_rgb: [number,number,number]; area_fraction: number }[];
  colour_families: unknown[];
  value_zones: { id: number; label: string; grey_value: number }[];
  teaching_stages?: {
    order: number;
    name: string;
    description: string;
    analysis_layers: string[];
  }[];
  teaching_instructions?: Record<string, string>;
  lesson_plan?: {
    order: number;
    name: string;
    description: string;
    medium: string;
    level: number;
    assets: Record<string, string>;
  }[];
  video?: string;
  video_chapters?: { order: number; name: string; start_sec: number }[];
  pdf?: string;
  personal_observations?: string | null;
  status?: string;  // A3: "analysis_ready" when progressive delivery is active
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

/** Convert an outputs-relative path (e.g. "abc/level_1.png") to a full URL. */
function outputUrl(relPath: string | undefined | null): string {
  if (!relPath) return "";
  if (relPath.startsWith("http")) return relPath;
  return `${API}/outputs/${relPath.replace(/^\//, "")}`;
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [jobStatus,    setJobStatus]    = useState<JobStatus>({ status: "queued", progress: 0, step: "", message: "Waiting to start" });
  const [manifest,     setManifest]     = useState<Manifest | null>(null);
  const [classicPages, setClassicPages] = useState<AnalysisPage[]>([]);
  const [selected,     setSelected]     = useState<AnalysisPage | null>(null);
  const [whyOpen,      setWhyOpen]      = useState(false);

  // A2: Explicit view mode — classic_analysis vs hierarchical_lesson
  const [viewMode, setViewMode] = useState<"classic_analysis" | "hierarchical_lesson">("hierarchical_lesson");

  // Hierarchical controls
  const [detailLevel,  setDetailLevel]  = useState(3);
  const [compareMode,  setCompareMode]  = useState<CompareMode>("analysis");
  const [opacity,      setOpacity]      = useState(0.5);

  // Independent layer toggles — each can be on/off simultaneously
  const [layers, setLayers] = useState<Record<string, boolean>>({
    colours:  true,
    values:   false,
    outlines: true,
    regions:  false,
  });
  function toggleLayer(key: string) {
    setLayers(prev => ({ ...prev, [key]: !prev[key] }));
  }

  // A4: Individual outline sublayer toggles (only visible when edge_maps available)
  const [outlineSublayers, setOutlineSublayers] = useState<Record<string, boolean>>({
    primary:    true,
    secondary:  false,
    decorative: false,
    texture:    false,
  });
  function toggleSublayer(key: string) {
    setOutlineSublayers(prev => ({ ...prev, [key]: !prev[key] }));
  }

  const pollRef  = useRef<ReturnType<typeof setInterval> | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  // Tracks whether the manifest has been fetched, without making `poll`'s
  // identity depend on manifest state — otherwise every fetch creates a new
  // `poll` reference, which re-fires the polling effect below and refetches
  // immediately, in an unthrottled loop instead of the intended 2.5s cadence.
  const manifestLoadedRef = useRef(false);

  const fetchManifest = useCallback(async (manifestUrl: string) => {
    try {
      const res = await fetch(absUrl(manifestUrl));
      if (res.ok) {
        const data: Manifest = await res.json();
        manifestLoadedRef.current = true;
        setManifest(data);

        const ps: AnalysisPage[] = (data.pages ?? []).map(p => {
          const key  = p.split("/").pop()?.replace(".png", "") ?? "";
          const meta = PAGE_LABELS[key] ?? { title: key, why: "", tip: "" };
          return { key, url: outputUrl(p), ...meta };
        }).filter(p => CLASSIC_PAGE_KEYS.includes(p.key));
        setClassicPages(ps);
        if (ps.length > 0) setSelected(prev => prev ?? ps[0]);

        // Set default viewing level from the initial_view_level the user picked at upload
        if (data.input?.initial_view_level) setDetailLevel(data.input.initial_view_level);
      }
    } catch { /* non-critical */ }
  }, []);

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`${API}/jobs/${jobId}`);
      const data: JobStatus = await res.json();
      setJobStatus(data);

      if ((data.status === "completed" || data.status === "completed_with_warnings") && data.result?.manifest) {
        if (pollRef.current) clearInterval(pollRef.current);
        if (!manifestLoadedRef.current) await fetchManifest(data.result.manifest);
      } else if (data.analysis_ready && !manifestLoadedRef.current) {
        // A3: Progressive delivery — fetch manifest while video/PDF still rendering
        await fetchManifest(`/outputs/${jobId}/manifest.json`);
      }
    } catch { /* backend unreachable */ }
  }, [jobId, fetchManifest]);

  useEffect(() => {
    poll();
    pollRef.current = setInterval(() => {
      setJobStatus(prev => {
        if (prev.status === "completed" || prev.status === "completed_with_warnings" || prev.status === "failed") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
        return prev;
      });
      poll();
    }, 2500);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [poll]);

  // ── Loading / Error states ─────────────────────────────────────────────────
  // A3: show results layout if analysis_ready even while video/PDF still processing
  const showResults = jobStatus.status === "completed"
    || jobStatus.status === "completed_with_warnings"
    || (jobStatus.analysis_ready && manifest !== null);

  if (!showResults) {
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

  // Reference image URL: use manifest.reference if available, fall back to line_art
  const referenceUrl = manifest?.reference
    ? outputUrl(manifest.reference)
    : absUrl(`/outputs/${jobId}/line_art.png`);

  const currentLevelData = manifest?.detail_levels?.[String(detailLevel)];

  // Whether video/PDF are still being generated (A3 progressive delivery)
  const isAnalysisReady = manifest?.status === "analysis_ready";
  const videoReady = Boolean(manifest?.video);
  const pdfReady   = Boolean(manifest?.pdf);

  // A2: derive analysisUrl and activeAssets from viewMode
  const analysisUrl = (viewMode === "classic_analysis" && selected)
    ? selected.url
    : undefined;

  // Compute the ordered list of asset URLs for hierarchical layers
  const LAYER_ASSET_KEY: Record<string, keyof NonNullable<typeof currentLevelData>> = {
    outlines: "outlines",
    values:   "values",
    colours:  "colours",
    regions:  "regions",
  };

  // Sublayer edge map URLs — sourced from the CURRENT level's own edge_maps,
  // not the global (non-level-filtered) manifest.edge_maps. Using the global
  // maps here would mean changing the detail level slider never changes the
  // outline sublayers shown, defeating the point of level-aware outlines.
  const hasEdgeMaps = Boolean(currentLevelData?.edge_maps && Object.keys(currentLevelData.edge_maps).length > 0);
  const activeSublayerUrls: string[] = hasEdgeMaps
    ? Object.entries(outlineSublayers)
        .filter(([, vis]) => vis)
        .map(([key]) => {
          const p = currentLevelData?.edge_maps?.[key];
          return p ? outputUrl(p) : null;
        })
        .filter((u): u is string => Boolean(u))
    : [];

  const activeAssets: string[] = viewMode === "classic_analysis"
    ? []
    : [
        ...Object.entries(layers)
          .filter(([key, vis]) => vis && !(key === "outlines" && hasEdgeMaps))
          .map(([key]) => {
            const assetPath = currentLevelData?.[LAYER_ASSET_KEY[key]];
            return typeof assetPath === "string" ? outputUrl(assetPath) : null;
          })
          .filter((u): u is string => Boolean(u)),
        ...activeSublayerUrls,
      ];

  return (
    <main className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>

      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-6 py-4 border-b flex-shrink-0"
              style={{ borderColor: "var(--border)" }}>
        <a href="/" className="font-bold text-lg" style={{ color: "var(--accent)" }}>← New Tutorial</a>

        {/* A3: Progressive delivery banner */}
        {isAnalysisReady && (
          <span className="text-xs px-3 py-1 rounded-full border"
                style={{ borderColor: "var(--accent)", color: "var(--accent)", background: "transparent" }}>
            Analysis ready — video &amp; PDF still rendering…
          </span>
        )}

        <div className="flex gap-2 text-sm">
          {manifest?.input && (
            <span className="px-3 py-1 rounded" style={{ background: "var(--surface)", color: "var(--text-dim)" }}>
              {manifest.input.medium} · {manifest.input.palette_size} colours · {manifest.input.value_zones} zones
            </span>
          )}
          {pdfReady ? (
            <a href={absUrl(manifest!.pdf!)} target="_blank" rel="noreferrer"
               className="px-4 py-2 rounded-lg border transition-colors"
               style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
              Download PDF
            </a>
          ) : (
            <span className="px-4 py-2 rounded-lg border"
                  style={{ borderColor: "var(--border)", color: "var(--text-dim)", opacity: 0.4 }}>
              PDF rendering…
            </span>
          )}
          {videoReady ? (
            <a href={absUrl(manifest!.video!)} download
               className="px-4 py-2 rounded-lg font-semibold"
               style={{ background: "var(--accent)", color: "#0f0e0d" }}>
              Download Video
            </a>
          ) : (
            <span className="px-4 py-2 rounded-lg font-semibold"
                  style={{ background: "var(--surface)", color: "var(--text-dim)", opacity: 0.4 }}>
              Video rendering…
            </span>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">

        {/* ── Left: classic analysis thumbnails ───────────────────────────── */}
        <nav className="w-44 flex-shrink-0 overflow-y-auto border-r p-2 space-y-1 hidden md:block"
             style={{ borderColor: "var(--border)" }}>

          {/* A2: View mode switcher */}
          <div className="flex flex-col gap-1 mb-3">
            <button
              onClick={() => setViewMode("hierarchical_lesson")}
              className="w-full text-left px-2 py-1.5 rounded text-xs font-medium transition-colors"
              style={{
                background: viewMode === "hierarchical_lesson" ? "var(--accent)" : "var(--surface)",
                color:      viewMode === "hierarchical_lesson" ? "#0f0e0d" : "var(--text-dim)",
              }}>
              Hierarchical Lesson
            </button>
            <button
              onClick={() => { setViewMode("classic_analysis"); if (!selected && classicPages[0]) setSelected(classicPages[0]); }}
              className="w-full text-left px-2 py-1.5 rounded text-xs font-medium transition-colors"
              style={{
                background: viewMode === "classic_analysis" ? "var(--accent)" : "var(--surface)",
                color:      viewMode === "classic_analysis" ? "#0f0e0d" : "var(--text-dim)",
              }}>
              Classic Analysis
            </button>
          </div>

          {viewMode === "classic_analysis" && (
            <>
              <p className="text-xs font-semibold uppercase tracking-widest px-1 mb-2"
                 style={{ color: "var(--text-dim)" }}>Analysis</p>
              {classicPages.map(p => (
                <button key={p.key}
                        onClick={() => { setSelected(p); setCompareMode("analysis"); setWhyOpen(false); }}
                        className="w-full text-left rounded-lg overflow-hidden border transition-colors"
                        style={{ borderColor: selected?.key === p.key ? "var(--accent)" : "transparent" }}>
                  <img src={p.url} alt={p.title} className="w-full object-cover" style={{ aspectRatio: "4/3" }} />
                  <p className="text-xs px-2 py-1 truncate" style={{ color: "var(--text-dim)" }}>{p.title}</p>
                </button>
              ))}
            </>
          )}

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

          {/* About Your Image — grounded in this job's own analysis (Claude
              vision call), not a per-medium template. Absent entirely when
              ANTHROPIC_API_KEY isn't configured on the backend. */}
          {manifest?.personal_observations && (
            <div className="p-4 border-b flex-shrink-0" style={{ borderColor: "var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-2"
                 style={{ color: "var(--text-dim)" }}>About Your Image</p>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>
                {manifest.personal_observations}
              </p>
            </div>
          )}

          {/* Video — A3: show pending state during progressive delivery */}
          <div className="p-4 border-b flex-shrink-0" style={{ borderColor: "var(--border)" }}>
            <p className="text-xs font-semibold uppercase tracking-widest mb-2"
               style={{ color: "var(--text-dim)" }}>Tutorial Video</p>
            {videoReady ? (
              <>
                <video ref={videoRef} src={absUrl(manifest!.video!)} controls className="w-full rounded-xl"
                       style={{ background: "#000", maxHeight: 380 }} />
                {manifest?.video_chapters && manifest.video_chapters.length > 0 && (
                  <div className="flex gap-1.5 flex-wrap mt-2">
                    {manifest.video_chapters.map(ch => (
                      <button
                        key={ch.order}
                        onClick={() => {
                          if (videoRef.current) {
                            videoRef.current.currentTime = ch.start_sec;
                            videoRef.current.play();
                          }
                        }}
                        className="px-2.5 py-1 rounded text-xs border transition-colors"
                        style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
                        {ch.name}
                      </button>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="w-full rounded-xl flex items-center justify-center"
                   style={{ background: "var(--surface)", height: 180 }}>
                <p className="text-sm" style={{ color: "var(--text-dim)" }}>
                  Video is still rendering…
                </p>
              </div>
            )}
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
                     onChange={e => { setDetailLevel(Number(e.target.value)); setViewMode("hierarchical_lesson"); }}
                     className="w-full accent-yellow-600" />
              <div className="flex justify-between text-xs mt-1" style={{ color: "var(--text-dim)" }}>
                <span>Foundation</span><span>Full Reference</span>
              </div>

              {/* Independent layer toggles */}
              <div className="flex gap-2 mt-3 flex-wrap">
                {Object.entries(layers).map(([key, vis]) => (
                  <button
                    key={key}
                    onClick={() => { toggleLayer(key); setViewMode("hierarchical_lesson"); }}
                    style={{
                      background:   vis ? "var(--accent)" : "var(--surface)",
                      color:        vis ? "#0f0e0d"       : "var(--text)",
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
                          color:        vis ? "#0f0e0d"       : "var(--text-dim)",
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
              analysisUrl={analysisUrl}
              activeAssets={viewMode === "classic_analysis" ? [] : activeAssets}
              referenceUrl={referenceUrl}
              opacity={opacity}
              imageWidth={manifest?.image?.width}
              imageHeight={manifest?.image?.height}
              title={viewMode === "classic_analysis" && selected ? selected.title : (currentLevelData?.label ?? "")}
            />

            {/* A2: Classic page WHY explanation — only in classic_analysis mode */}
            {viewMode === "classic_analysis" && selected && compareMode === "analysis" && (
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

            {/* Mobile thumbnail strip — only in classic mode */}
            {viewMode === "classic_analysis" && (
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
            )}
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
                             style={{ background: "var(--accent)", color: "#0f0e0d" }}>
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

// ── Layered image composition ─────────────────────────────────────────────────
function LayerStack({
  assets,
  imageWidth,
  imageHeight,
  maxHeight = 520,
}: {
  assets:      string[];
  imageWidth?:  number;
  imageHeight?: number;
  maxHeight?:   number;
}) {
  if (assets.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "var(--text-dim)", background: "var(--surface)", borderRadius: 12 }}>
        No layers selected — enable at least one above
      </div>
    );
  }

  const aspectStyle = imageWidth && imageHeight
    ? { aspectRatio: `${imageWidth}/${imageHeight}` }
    : {};

  return (
    <div style={{ position: "relative", width: "100%", maxHeight, overflow: "hidden", borderRadius: 12, ...aspectStyle }}>
      {assets.map((url, i) => (
        <img
          key={url}
          src={url}
          alt=""
          style={{
            position:     i === 0 ? "relative" : "absolute",
            top:          0,
            left:         0,
            width:        "100%",
            height:       "100%",
            objectFit:    "contain",
            mixBlendMode: i === 0 ? "normal" : "multiply",
            opacity:      0.85,
          }}
        />
      ))}
    </div>
  );
}

// ── Image display with comparison modes ───────────────────────────────────────
function ImageDisplay({
  compareMode,
  analysisUrl,
  activeAssets,
  referenceUrl,
  opacity,
  imageWidth,
  imageHeight,
  title,
}: {
  compareMode:   CompareMode;
  analysisUrl?:  string;
  activeAssets:  string[];
  referenceUrl:  string;
  opacity:       number;
  imageWidth?:   number;
  imageHeight?:  number;
  title:         string;
}) {
  // Determine what to show in the "analysis" slot
  // If a classic page is selected, show it as a single image; otherwise show the layer stack
  const hasClassic = Boolean(analysisUrl);

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
          <div className="flex-1">
            {hasClassic
              ? <img src={analysisUrl} alt="Analysis" className="w-full rounded-xl object-contain max-h-[480px]" />
              : <LayerStack assets={activeAssets} imageWidth={imageWidth} imageHeight={imageHeight} maxHeight={480} />
            }
          </div>
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
          <div className="absolute inset-0 w-full h-full" style={{ opacity }}>
            {hasClassic
              ? <img src={analysisUrl} alt="Analysis" className="w-full h-full object-contain" />
              : <LayerStack assets={activeAssets} imageWidth={imageWidth} imageHeight={imageHeight} maxHeight={520} />
            }
          </div>
        </div>
      </div>
    );
  }

  // default: "analysis"
  if (!hasClassic && activeAssets.length === 0) {
    return (
      <div className="rounded-xl flex items-center justify-center" style={{ minHeight: 300, background: "var(--surface)" }}>
        <p style={{ color: "var(--text-dim)" }}>No layers selected — enable at least one above</p>
      </div>
    );
  }

  return (
    <div>
      {title && <p className="text-xs mb-2" style={{ color: "var(--text-dim)" }}>{title}</p>}
      {hasClassic
        ? <img src={analysisUrl} alt={title || "Analysis"} className="w-full rounded-xl object-contain max-h-[520px]" />
        : <LayerStack assets={activeAssets} imageWidth={imageWidth} imageHeight={imageHeight} maxHeight={520} />
      }
    </div>
  );
}
