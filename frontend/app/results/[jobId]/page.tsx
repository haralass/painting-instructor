"use client";
import { useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { absUrl, outputUrl, type CompareMode } from "./lib/manifest";
import { useJobPolling } from "./hooks/useJobPolling";
import LoadingScreen from "./components/LoadingScreen";
import ImageDisplay from "./components/ImageDisplay";
import LessonPlayer from "./components/LessonPlayer";
import CritiquePanel from "./components/CritiquePanel";
import HierarchicalControls from "./components/HierarchicalControls";
import TeachingAside from "./components/TeachingAside";

// ── Main component ────────────────────────────────────────────────────────────
export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const {
    jobStatus, manifest, classicPages,
    selected, setSelected,
    detailLevel, setDetailLevel,
    viewMode, setViewMode,
  } = useJobPolling(jobId);

  const [whyOpen, setWhyOpen] = useState(false);

  // Hierarchical controls display state — owned here because it drives the
  // image composition below as well as the controls surface.
  const [compareMode, setCompareMode] = useState<CompareMode>("analysis");
  const [opacity,     setOpacity]     = useState(0.5);

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

  const videoRef = useRef<HTMLVideoElement>(null);

  // ── Loading / Error states ─────────────────────────────────────────────────
  // A3: show results layout if analysis_ready even while video/PDF still processing
  const showResults = jobStatus.status === "completed"
    || jobStatus.status === "completed_with_warnings"
    || (jobStatus.analysis_ready && manifest !== null);

  if (!showResults) {
    return <LoadingScreen jobStatus={jobStatus} />;
  }

  // ── Results layout ─────────────────────────────────────────────────────────
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
            <HierarchicalControls
              manifest={manifest}
              detailLevel={detailLevel}
              setDetailLevel={setDetailLevel}
              setViewMode={setViewMode}
              layers={layers}
              toggleLayer={toggleLayer}
              hasEdgeMaps={hasEdgeMaps}
              outlineSublayers={outlineSublayers}
              toggleSublayer={toggleSublayer}
              compareMode={compareMode}
              setCompareMode={setCompareMode}
              opacity={opacity}
              setOpacity={setOpacity}
            />
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
          <TeachingAside
            manifest={manifest}
            setViewMode={setViewMode}
            setDetailLevel={setDetailLevel}
            setCompareMode={setCompareMode}
          />
        )}
      </div>
    </main>
  );
}
