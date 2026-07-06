"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import EvolvingCanvas, { STAGE_VISUAL_COUNT } from "../../components/EvolvingCanvas";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Which evolving-canvas stage each pipeline step should show, so the loading
// screen paints the picture forward as the real work advances.
const STEP_STAGE: Record<string, number> = {
  loading: 0, line_art: 1, notan: 2, color_temperature: 3, color_palette: 3,
  light_direction: 3, color_by_number: 4, dot_to_dot: 1, hierarchical: 4,
  video: 5, pdf: 5, manifest: 5, completed: 5,
};

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
  study_overlay: {
    title: "Detail Study",
    why:   "Every colour-region boundary traced directly on the reference — the digital version of outlining shapes by hand on a print. Use it to see exactly where one colour ends and the next begins.",
    tip:   "Pick one small area, follow its traced shapes, and mix each one separately before you commit it to the canvas.",
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
  "light_direction", "color_by_number", "dot_to_dot", "study_overlay",
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
    skill_level?: string;
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
  palette: {
    id: number; name: string; base_rgb: [number,number,number]; area_fraction: number;
    mixing?: { text: string; delta_e: number; mixed_rgb: [number,number,number] };
  }[];
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
    why?: string;
    medium: string;
    level: number;
    assets: Record<string, string>;
    image_notes?: string[];
  }[];
  image_brief?: {
    overview?: string;
    light?: { angle: number | null; from: string | null };
    masses?: { location: string; colour_name: string; value_label: string; area_frac: number }[];
    focal?: { location: string } | null;
    busy_areas?: { location: string; region_count: number }[];
    warmest_colour?: string | null;
    coolest_colour?: string | null;
  };
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

  // View mode — "lesson" is the guided step-by-step teacher (default);
  // "hierarchical_lesson" is the free layer explorer; "classic_analysis"
  // shows the seven classic study pages; "critique" compares an uploaded
  // attempt against the reference.
  const [viewMode, setViewMode] = useState<"lesson" | "classic_analysis" | "hierarchical_lesson" | "critique">("lesson");

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

        // No lesson plan (old job / failed resolution) — fall back to the explorer
        if (!data.lesson_plan || data.lesson_plan.length === 0) {
          setViewMode(prev => (prev === "lesson" ? "hierarchical_lesson" : prev));
        }
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
        <div className="text-center max-w-md fade-up">
          {isRunning && (
            <>
              {/* Paint blobs mixing — staggered pulse */}
              <div className="flex items-center justify-center gap-3 mb-8">
                {["#dca55e", "#bf5b45", "#7d92ab"].map((c, i) => (
                  <span key={c} className="blob-pulse inline-block rounded-full"
                        style={{
                          width: 22 + (i === 1 ? 10 : 0), height: 22 + (i === 1 ? 10 : 0),
                          background: `radial-gradient(circle at 35% 30%, ${c}, ${c}88)`,
                          boxShadow: `0 0 24px ${c}55`,
                          animationDelay: `${i * 0.35}s`,
                        }} />
                ))}
              </div>
              <p className="eyebrow mb-3">Analysing your reference</p>
              <h2 className="font-display text-3xl mb-4" style={{ color: "var(--text)" }}>
                Preparing your <em className="text-gradient">tutorial</em>
              </h2>
              <p className="text-base mb-2" style={{ color: "var(--text)" }}>
                {STEP_LABELS[jobStatus.step] ?? jobStatus.message ?? "Processing…"}
              </p>
              <p className="text-sm mb-6" style={{ color: "var(--text-dim)" }}>
                {jobStatus.progress > 0 ? `${jobStatus.progress}% complete` : "Starting…"}
              </p>
              <div className="h-2 w-full rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
                <div className="h-full rounded-full progress-shimmer transition-all duration-700"
                     style={{ width: `${Math.max(jobStatus.progress, 4)}%` }} />
              </div>
            </>
          )}
          {jobStatus.status === "failed" && (
            <>
              <div className="w-14 h-14 mx-auto mb-6 rounded-full flex items-center justify-center"
                   style={{ background: "rgba(157,47,47,0.1)", border: "1px solid rgba(157,47,47,0.35)", color: "var(--crimson)", fontSize: 22 }}>
                ✕
              </div>
              <h2 className="font-display text-3xl mb-2" style={{ color: "var(--text)" }}>Processing failed</h2>
              <p style={{ color: "var(--text-dim)" }}>{jobStatus.error ?? "Unknown error"}</p>
              <Link href="/" className="btn-primary mt-8 inline-flex" style={{ padding: "12px 24px", fontSize: 14, textDecoration: "none" }}>
                ← Try again
              </Link>
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
              style={{ borderColor: "var(--border)", background: "linear-gradient(to bottom, rgba(248,244,234,0.9), transparent)" }}>
        <Link href="/" className="font-display text-lg" style={{ color: "var(--text)", textDecoration: "none" }}>
          <span style={{ color: "var(--accent)" }}>←</span> Painting <em style={{ color: "var(--accent)" }}>Instructor</em>
        </Link>

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
               className="btn-ghost" style={{ padding: "9px 18px", fontSize: 13, textDecoration: "none" }}>
              Download PDF
            </a>
          ) : (
            <span className="btn-ghost" style={{ padding: "9px 18px", fontSize: 13, opacity: 0.4, cursor: "default" }}>
              PDF rendering…
            </span>
          )}
          {videoReady ? (
            <a href={absUrl(manifest!.video!)} download
               className="btn-primary" style={{ padding: "9px 18px", fontSize: 13, textDecoration: "none" }}>
              Download Video
            </a>
          ) : (
            <span className="btn-primary" style={{ padding: "9px 18px", fontSize: 13, opacity: 0.4, cursor: "default", filter: "saturate(0.4)" }}>
              Video rendering…
            </span>
          )}
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">

        {/* ── Left: classic analysis thumbnails ───────────────────────────── */}
        <nav className="w-44 flex-shrink-0 overflow-y-auto border-r p-2 space-y-1 hidden md:block"
             style={{ borderColor: "var(--border)" }}>

          {/* View mode switcher */}
          <div className="flex flex-col gap-1 mb-3">
            {([
              ["lesson",              "Lesson",          Boolean(manifest?.lesson_plan?.length)],
              ["hierarchical_lesson", "Explore Layers",  true],
              ["classic_analysis",    "Classic Analysis", true],
              ["critique",            "Get Critique",    true],
            ] as const).map(([mode, label, enabled]) => enabled && (
              <button
                key={mode}
                onClick={() => {
                  setViewMode(mode);
                  if (mode === "classic_analysis" && !selected && classicPages[0]) setSelected(classicPages[0]);
                }}
                className="w-full text-left px-2 py-1.5 rounded text-xs font-medium transition-colors"
                style={{
                  background: viewMode === mode ? "var(--accent)" : "var(--surface)",
                  color:      viewMode === mode ? "var(--paper)" : "var(--text-dim)",
                }}>
                {label}
              </button>
            ))}
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
                         border: "1px solid var(--border)",
                       }} />
                ))}
              </div>
            </div>
          )}
        </nav>

        {/* ── Centre: video + main image + controls ───────────────────────── */}
        <section className="flex-1 flex flex-col overflow-y-auto min-w-0">

          {/* Mobile mode switcher — the left nav is hidden below md */}
          <div className="flex gap-1.5 p-3 overflow-x-auto md:hidden flex-shrink-0 border-b"
               style={{ borderColor: "var(--border)" }}>
            {([
              ["lesson",              "Lesson"],
              ["hierarchical_lesson", "Layers"],
              ["classic_analysis",    "Analysis"],
              ["critique",            "Critique"],
            ] as const).map(([mode, label]) => (
              <button key={mode}
                      onClick={() => {
                        setViewMode(mode);
                        if (mode === "classic_analysis" && !selected && classicPages[0]) setSelected(classicPages[0]);
                      }}
                      className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
                      style={{
                        background: viewMode === mode ? "var(--accent)" : "var(--surface)",
                        color:      viewMode === mode ? "var(--paper)" : "var(--text-dim)",
                        border:     "1px solid var(--border)",
                      }}>
                {label}
              </button>
            ))}
          </div>

          {viewMode === "lesson" && manifest?.lesson_plan && manifest.lesson_plan.length > 0 ? (
            <LessonPlayer
              manifest={manifest}
              referenceUrl={referenceUrl}
              videoReady={videoReady}
            />
          ) : viewMode === "critique" ? (
            <CritiquePanel jobId={jobId} referenceUrl={referenceUrl} />
          ) : (<>

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
                     className="w-full accent-orange-700" />
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
                {(["analysis", "reference", "side_by_side", "overlay"] as CompareMode[]).map(m => (
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
          </>)}
        </section>

        {/* ── Right: teaching instructions panel — the lesson player and the
              critique view carry their own teaching column, so this aside
              only accompanies the explorer/classic modes ─────────────────── */}
        {manifest?.input && (viewMode === "hierarchical_lesson" || viewMode === "classic_analysis") && (
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
    <div key={assets.join("|")}
         className="layer-transition"
         style={{ position: "relative", width: "100%", maxHeight, overflow: "hidden", borderRadius: 12, ...aspectStyle }}>
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

// ── Lesson player — the guided, step-by-step teacher ─────────────────────────
function LessonPlayer({
  manifest,
  referenceUrl,
  videoReady,
}: {
  manifest: Manifest;
  referenceUrl: string;
  videoReady: boolean;
}) {
  const steps = [...(manifest.lesson_plan ?? [])].sort((a, b) => a.order - b.order);
  const [idx, setIdx] = useState(0);
  const [showRef, setShowRef] = useState(false);
  const step = steps[idx];
  const brief = manifest.image_brief;

  if (!step) return null;

  const assets = Object.values(step.assets ?? {}).map(outputUrl).filter(Boolean);
  const stepLabel = step.order === 0 ? "Warm-up" : step.order === 99 ? "Final check" : `Step ${step.order}`;

  return (
    <div className="p-4 md:p-6 space-y-5">

      {/* The teacher's brief — image-specific, computed from THIS photo */}
      {(brief?.overview || manifest.personal_observations) && idx === 0 && (
        <div className="rounded-xl p-4"
             style={{ background: "rgba(180,81,31,0.06)", border: "1px solid rgba(180,81,31,0.22)" }}>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
            Before you start — about your photo
          </p>
          {brief?.overview && (
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{brief.overview}</p>
          )}
          {manifest.personal_observations && (
            <p className="text-sm leading-relaxed mt-2" style={{ color: "var(--text-dim)" }}>
              {manifest.personal_observations}
            </p>
          )}
        </div>
      )}

      <div className="flex flex-col lg:flex-row gap-5">

        {/* Visual for this step */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>
              {showRef ? "Reference photo" : "What to look at for this step"}
            </p>
            <button onClick={() => setShowRef(!showRef)}
                    className="px-3 py-1 rounded border text-xs transition-colors"
                    style={{
                      background:  showRef ? "var(--accent)" : "var(--surface)",
                      color:       showRef ? "var(--paper)" : "var(--text-dim)",
                      borderColor: "var(--border)",
                    }}>
              {showRef ? "Show analysis" : "Show reference"}
            </button>
          </div>
          {showRef || assets.length === 0 ? (
            <img src={referenceUrl} alt="Reference"
                 className="w-full rounded-xl object-contain layer-transition" style={{ maxHeight: 500 }} />
          ) : (
            <LayerStack assets={assets}
                        imageWidth={manifest.image?.width} imageHeight={manifest.image?.height}
                        maxHeight={500} />
          )}
        </div>

        {/* Teaching column */}
        <div className="w-full lg:w-80 flex-shrink-0 space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest mb-1" style={{ color: "var(--accent)" }}>
              {stepLabel} of {steps.filter(s => 1 <= s.order && s.order < 90).length}
              {manifest.input?.skill_level ? ` · ${manifest.input.skill_level}` : ""}
            </p>
            <h2 className="text-xl font-bold mb-2" style={{ color: "var(--text)" }}>{step.name}</h2>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{step.description}</p>
          </div>

          {/* For YOUR photo — the personal part */}
          {step.image_notes && step.image_notes.length > 0 && (
            <div className="rounded-xl p-3"
                 style={{ background: "rgba(180,81,31,0.07)", border: "1px solid rgba(180,81,31,0.28)" }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
                For your photo
              </p>
              <ul className="space-y-2">
                {step.image_notes.map((n, i) => (
                  <li key={i} className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{n}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Why */}
          {step.why && (
            <div className="rounded-xl p-3" style={{ background: "var(--surface)", border: "1px solid var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>
                Why this step
              </p>
              <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>{step.why}</p>
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center gap-2">
            <button onClick={() => setIdx(Math.max(0, idx - 1))} disabled={idx === 0}
                    className="px-4 py-2 rounded-lg border text-sm transition-colors"
                    style={{
                      borderColor: "var(--border)", color: "var(--text)",
                      opacity: idx === 0 ? 0.35 : 1, cursor: idx === 0 ? "default" : "pointer",
                      background: "var(--surface)",
                    }}>
              ← Back
            </button>
            <button onClick={() => setIdx(Math.min(steps.length - 1, idx + 1))}
                    disabled={idx === steps.length - 1}
                    className="flex-1 px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
                    style={{
                      background: idx === steps.length - 1 ? "var(--surface)" : "var(--accent)",
                      color:      idx === steps.length - 1 ? "var(--text-dim)" : "var(--paper)",
                      cursor:     idx === steps.length - 1 ? "default" : "pointer",
                    }}>
              {idx === steps.length - 1 ? "Lesson complete" : "Next step →"}
            </button>
          </div>

          {/* Step dots */}
          <div className="flex gap-1.5 justify-center flex-wrap">
            {steps.map((s, i) => (
              <button key={s.order} onClick={() => setIdx(i)} title={s.name}
                      className="rounded-full transition-all"
                      style={{
                        width: i === idx ? 22 : 8, height: 8,
                        background: i === idx ? "var(--accent)" : i < idx ? "var(--accent-dim)" : "var(--border)",
                        border: "none", cursor: "pointer",
                      }} />
            ))}
          </div>
        </div>
      </div>

      {/* Tutorial video at the end of the lesson */}
      {videoReady && manifest.video && idx === steps.length - 1 && (
        <div className="pt-2">
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
            Watch the full progression
          </p>
          <video src={absUrl(manifest.video)} controls className="w-full rounded-xl"
                 style={{ background: "#000", maxHeight: 380 }} />
        </div>
      )}
    </div>
  );
}

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

function CritiquePanel({ jobId, referenceUrl }: { jobId: string; referenceUrl: string }) {
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
