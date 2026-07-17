"use client";
import { useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { API, absUrl, outputUrl, LEVEL_LABELS, type CompareMode, type LocalAnalysis } from "./lib/manifest";
import { useJobPolling } from "./hooks/useJobPolling";
import LoadingScreen from "./components/LoadingScreen";
import ImageDisplay from "./components/ImageDisplay";
import Viewer from "./components/Viewer";
import LessonPlayer from "./components/LessonPlayer";
import GuidedLessonPlayer from "./components/GuidedLessonPlayer";
import CritiquePanel from "./components/CritiquePanel";
import SquintSimulator from "./components/SquintSimulator";
import ConstructionView from "./components/ConstructionView";
import ProgressiveReveal from "./components/ProgressiveReveal";
import HierarchicalControls from "./components/HierarchicalControls";
import TeachingAside from "./components/TeachingAside";
import type { ViewMode } from "./hooks/useJobPolling";

// ── Main component ────────────────────────────────────────────────────────────
export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const {
    jobStatus, manifest, classicPages,
    selected, setSelected,
    detailLevel, setDetailLevel,
    viewMode, setViewMode,
  } = useJobPolling(jobId);

  // "build_up" is a UI-only view mode layered on top of the polling hook's
  // ViewMode union (which is off-limits to edit). Widen the mode + setter once
  // here at the boundary so the rest of the file can treat it as a real mode.
  type UIViewMode = ViewMode | "build_up";
  const uiViewMode = viewMode as UIViewMode;
  const setUIViewMode = setViewMode as unknown as React.Dispatch<React.SetStateAction<UIViewMode>>;

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

  // Phase 2 leftover: rectangle region selection + "Analyse this area".
  // The Viewer owns the drag-to-select rectangle; this page owns the actual
  // network call and the small result panel that shows what came back.
  const [localAnalysis, setLocalAnalysis]           = useState<LocalAnalysis | null>(null);
  const [localAnalysisError, setLocalAnalysisError] = useState<string | null>(null);
  const [analyzingArea, setAnalyzingArea]            = useState(false);
  // When set, show the focused step-by-step construction of a local crop.
  const [localConstruction, setLocalConstruction]   = useState<LocalAnalysis | null>(null);

  async function handleSelectArea(bbox: { x: number; y: number; w: number; h: number }) {
    setAnalyzingArea(true);
    setLocalAnalysisError(null);
    try {
      const res = await fetch(`${API}/jobs/${jobId}/local-analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bbox),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail ?? `Local analysis failed (${res.status})`);
      }
      setLocalAnalysis(await res.json() as LocalAnalysis);
    } catch (err) {
      setLocalAnalysisError(err instanceof Error ? err.message : "Local analysis failed");
    } finally {
      setAnalyzingArea(false);
    }
  }
  function clearLocalAnalysis() {
    setLocalAnalysis(null);
    setLocalAnalysisError(null);
  }

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

  // Value-study asset for the Squint Simulator's "reveal the true notan" button.
  // Prefer the dedicated notan classic page; fall back to the current level's
  // values layer. Undefined when neither exists (button simply hides).
  const notanUrl = classicPages.find(p => p.key === "notan")?.url
    ?? (currentLevelData?.values ? outputUrl(currentLevelData.values) : undefined);

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
    // h-screen + overflow-hidden: the shell owns the viewport; each panel
    // scrolls independently. No page-level scroll, no giant empty columns.
    <main className="h-screen flex flex-col overflow-hidden" style={{ background: "var(--bg)" }}>

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
              ["lesson",              "Lesson",          Boolean(manifest?.lesson?.steps?.length || manifest?.lesson_plan?.length)],
              ["construction",        "Construction",    Boolean(manifest?.drawing_json)],
              ["hierarchical_lesson", "Explore Layers",  true],
              ["build_up",            "Build up",        Boolean(manifest?.detail_levels && Object.keys(manifest.detail_levels).length > 0)],
              ["squint",              "Squint",          true],
              ["classic_analysis",    "Classic Analysis", true],
              ["critique",            "Get Critique",    true],
            ] as const).map(([mode, label, enabled]) => enabled && (
              <button
                key={mode}
                onClick={() => {
                  setUIViewMode(mode);
                  if (mode === "classic_analysis" && !selected && classicPages[0]) setSelected(classicPages[0]);
                }}
                className="w-full text-left px-2 py-1.5 rounded text-xs font-medium transition-colors"
                style={{
                  background: uiViewMode === mode ? "var(--accent)" : "var(--surface)",
                  color:      uiViewMode === mode ? "var(--paper)" : "var(--text-dim)",
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
              ["construction",        "Construction"],
              ["hierarchical_lesson", "Layers"],
              ["build_up",            "Build up"],
              ["squint",              "Squint"],
              ["classic_analysis",    "Analysis"],
              ["critique",            "Critique"],
            ] as const).map(([mode, label]) => (
              <button key={mode}
                      onClick={() => {
                        setUIViewMode(mode);
                        if (mode === "classic_analysis" && !selected && classicPages[0]) setSelected(classicPages[0]);
                      }}
                      className="flex-shrink-0 px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
                      style={{
                        background: uiViewMode === mode ? "var(--accent)" : "var(--surface)",
                        color:      uiViewMode === mode ? "var(--paper)" : "var(--text-dim)",
                        border:     "1px solid var(--border)",
                      }}>
                {label}
              </button>
            ))}
          </div>

          {uiViewMode === "build_up" ? (
            <ProgressiveReveal
              manifest={manifest}
              referenceUrl={referenceUrl}
            />
          ) : viewMode === "lesson" && manifest?.lesson?.steps?.length ? (
            <div className="flex-1 flex flex-col min-h-0 p-4">
              <GuidedLessonPlayer
                jobId={jobId}
                referenceUrl={referenceUrl}
                manifest={manifest}
                onOpenCritique={() => setUIViewMode("critique")}
              />
            </div>
          ) : viewMode === "lesson" && manifest?.lesson_plan && manifest.lesson_plan.length > 0 ? (
            <LessonPlayer
              manifest={manifest}
              referenceUrl={referenceUrl}
              videoReady={videoReady}
            />
          ) : viewMode === "construction" ? (
            <div className="flex-1 flex flex-col min-h-0 p-4">
              <ConstructionView jobId={jobId} referenceUrl={referenceUrl} manifest={manifest} />
            </div>
          ) : viewMode === "critique" ? (
            <CritiquePanel jobId={jobId} referenceUrl={referenceUrl} />
          ) : viewMode === "squint" ? (
            <SquintSimulator referenceUrl={referenceUrl} notanUrl={notanUrl} />
          ) : (<>

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
          <div className="p-4 flex-1 flex flex-col min-h-0">
            {viewMode === "hierarchical_lesson" ? (
              /* Phase 2: the real workspace — one OpenSeadragon viewer drives
                 every compare mode (Reference / Overlay / Before-After split /
                 synced Side-by-Side) plus region hover/click selection against
                 the merge-tree hierarchy. No duplicated viewer logic. */
              compareMode === "side_by_side" ? (
                <div className="flex gap-3 flex-1 min-h-0">
                  {([["reference", true], ["overlay", false]] as const).map(([m, primary]) => (
                    <div key={m} className="flex-1 min-w-0 flex flex-col">
                      <p className="label-xs mb-1">{primary ? "Reference" : "Analysis"}</p>
                      <Viewer
                        jobId={jobId}
                        referenceUrl={referenceUrl}
                        overlays={activeAssets}
                        opacity={1}
                        mode={m}
                        syncKey={`sbs:${jobId}`}
                        hideControls={!primary}
                        imageWidth={manifest?.image?.width}
                        imageHeight={manifest?.image?.height}
                        labelMapUrl={manifest?.label_maps?.[String(detailLevel)]
                          ? outputUrl(manifest.label_maps[String(detailLevel)]) : undefined}
                        regionsUrl={outputUrl(manifest?.regions_json ?? `${jobId}/regions.json`)}
                        manifest={manifest}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <Viewer
                  jobId={jobId}
                  referenceUrl={referenceUrl}
                  overlays={activeAssets}
                  opacity={compareMode === "overlay" ? opacity : 1}
                  mode={compareMode === "reference" ? "reference"
                      : compareMode === "split" ? "split" : "overlay"}
                  imageWidth={manifest?.image?.width}
                  imageHeight={manifest?.image?.height}
                  labelMapUrl={manifest?.label_maps?.[String(detailLevel)]
                    ? outputUrl(manifest.label_maps[String(detailLevel)]) : undefined}
                  regionsUrl={outputUrl(manifest?.regions_json ?? `${jobId}/regions.json`)}
                  manifest={manifest}
                  onSelectArea={handleSelectArea}
                  onClearArea={clearLocalAnalysis}
                  analyzingArea={analyzingArea}
                />
              )
            ) : (
            <ImageDisplay
              compareMode={compareMode}
              analysisUrl={analysisUrl}
              activeAssets={[]}
              referenceUrl={referenceUrl}
              opacity={opacity}
              imageWidth={manifest?.image?.width}
              imageHeight={manifest?.image?.height}
              title={viewMode === "classic_analysis" && selected ? selected.title : (LEVEL_LABELS[detailLevel] ?? currentLevelData?.label ?? "")}
              palette={manifest?.palette}
            />
            )}

            {/* "Analyse this area" result — a closer, real local re-analysis of
                the rectangle the student dragged on the viewer, cropped from
                the full-resolution reference (never the preview). */}
            {viewMode === "hierarchical_lesson" && (localAnalysis || localAnalysisError) && (
              <div className="mt-3 p-3 rounded-xl flex gap-3 items-start"
                   style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
                {localAnalysisError ? (
                  <p className="text-sm flex-1" style={{ color: "var(--text-dim)" }}>
                    Local analysis failed: {localAnalysisError}
                  </p>
                ) : localAnalysis && (
                  <>
                    <img
                      src={outputUrl(localAnalysis.assets.outlines ?? localAnalysis.assets.colours ?? undefined)}
                      alt="Close-up analysis of the selected area"
                      className="rounded-lg flex-shrink-0"
                      style={{ width: 160, height: "auto", border: "1px solid var(--border)", background: "var(--paper)" }}
                    />
                    <div className="flex-1 text-xs">
                      <p className="font-medium mb-1" style={{ color: "var(--ink)" }}>
                        Analysed area — {Math.round(localAnalysis.bbox.w)}×{Math.round(localAnalysis.bbox.h)}px
                      </p>
                      <p style={{ color: "var(--text-dim)" }}>
                        A closer look at just this region, worked out the same way as the
                        full lesson — outlines, values and colour masses, scaled up for detail.
                      </p>
                      {localAnalysis.drawing_summary && (
                        <p className="mt-1" style={{ color: "var(--text)" }}>
                          Construction here: {localAnalysis.drawing_summary.n_landmarks} landmarks,
                          a {localAnalysis.drawing_summary.envelope_segments}-sided envelope
                          {typeof localAnalysis.drawing_summary.occupied_fraction === "number"
                            && `, subject fills ~${Math.round(localAnalysis.drawing_summary.occupied_fraction * 100)}% of the crop`}.
                          {localAnalysis.drawing_summary.silhouette_cause
                            && ` The outer edge reads as ${localAnalysis.drawing_summary.silhouette_cause}.`}
                        </p>
                      )}
                      {localAnalysis.assets.drawing_json && localAnalysis.assets.crop && (
                        <button onClick={() => setLocalConstruction(localAnalysis)}
                                className="btn-ghost mt-2" style={{ padding: "4px 12px", fontSize: 12 }}>
                          Learn to build this area step by step →
                        </button>
                      )}
                    </div>
                  </>
                )}
                <button onClick={clearLocalAnalysis} title="Clear"
                        style={{ background: "none", border: "none", cursor: "pointer",
                                 color: "var(--text-dim)", flexShrink: 0 }}>✕</button>
              </div>
            )}

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

            {/* Secondary material lives BELOW the image, collapsed — the
                workspace opens on the image, not on a video (brief §19/O). */}
            {manifest?.personal_observations && (
              <details className="mt-4 rounded-xl overflow-hidden"
                       style={{ border: "1px solid var(--border)" }}>
                <summary className="px-4 py-3 text-xs font-semibold uppercase tracking-widest cursor-pointer select-none"
                         style={{ color: "var(--text-dim)" }}>
                  About your image
                </summary>
                <p className="px-4 pb-4 text-sm leading-relaxed" style={{ color: "var(--text)" }}>
                  {manifest.personal_observations}
                </p>
              </details>
            )}

            <details className="mt-3 rounded-xl overflow-hidden"
                     style={{ border: "1px solid var(--border)" }}>
              <summary className="px-4 py-3 text-xs font-semibold uppercase tracking-widest cursor-pointer select-none"
                       style={{ color: "var(--text-dim)" }}>
                Tutorial video {videoReady ? "" : "· rendering…"}
              </summary>
              <div className="px-4 pb-4">
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
                       style={{ background: "var(--surface)", height: 120 }}>
                    <p className="text-sm" style={{ color: "var(--text-dim)" }}>
                      Video is still rendering — it will appear here.
                    </p>
                  </div>
                )}
              </div>
            </details>
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

      {/* Focused local construction — the §9 "local lesson": the child crop's
          own step-by-step drawing construction, over a modal covering the
          workspace. Reuses ConstructionView with the crop's drawing + image. */}
      {localConstruction?.assets.drawing_json && localConstruction.assets.crop && (
        <div className="fixed inset-0 z-50 flex flex-col p-4"
             style={{ background: "rgba(36,31,22,0.55)" }}>
          <div className="flex-1 min-h-0 flex flex-col rounded-2xl overflow-hidden p-4"
               style={{ background: "var(--bg)", border: "1px solid var(--border-strong)" }}>
            <div className="flex items-center justify-between mb-3 flex-shrink-0">
              <p className="font-display text-lg" style={{ color: "var(--ink)" }}>
                Building this area — {Math.round(localConstruction.bbox.w)}×{Math.round(localConstruction.bbox.h)}px
                <span className="text-sm ml-2" style={{ color: "var(--text-dim)" }}>
                  a focused construction of just your selection
                </span>
              </p>
              <button onClick={() => setLocalConstruction(null)} className="btn-ghost"
                      style={{ padding: "6px 16px", fontSize: 13 }}>Close ✕</button>
            </div>
            <div className="flex-1 min-h-0">
              <ConstructionView
                jobId={jobId}
                referenceUrl={outputUrl(localConstruction.assets.crop)}
                drawingUrl={outputUrl(localConstruction.assets.drawing_json)}
                manifest={null}
              />
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
