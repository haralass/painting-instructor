"use client";
import { useState, useRef, useEffect, DragEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import SmoothScroll, { scrollToSection } from "./components/SmoothScroll";
import HeroCanvas from "./components/HeroCanvas";
import KineticTitle from "./components/KineticTitle";
import ArtTile, { ArtMode } from "./components/ArtTile";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const MEDIUMS = [
  { id: "oil",        label: "Oil Paint",   dot: "#bf5b45", tip: "Rich blending, slow drying. Best for realism and portraiture." },
  { id: "watercolor", label: "Watercolour", dot: "#7d92ab", tip: "Transparent layers. Work light-to-dark, preserve whites." },
  { id: "acrylic",    label: "Acrylic",     dot: "#dca55e", tip: "Fast-drying, versatile. Can mimic oil or watercolour." },
  { id: "pencil",     label: "Pencil",      dot: "#9b9187", tip: "Graphite hatching. Build value through layered strokes." },
  { id: "charcoal",   label: "Charcoal",    dot: "#41504f", tip: "Broad marks, erasable highlights. Great for tonal studies." },
  { id: "digital",    label: "Digital",     dot: "#8a9179", tip: "Layers, undo, and infinite colour — but the same value discipline." },
];

const SKILL_LEVELS = [
  { id: "beginner",     label: "Beginner",     tip: "Adds a value warm-up rehearsal before the real painting." },
  { id: "intermediate", label: "Intermediate", tip: "The standard lesson for your medium." },
  { id: "advanced",     label: "Advanced",     tip: "Adds a measured self-critique pass at the end." },
];

const INITIAL_VIEW_LEVELS = [
  { value: 1, label: "Foundation",     desc: "Basic shapes + primary contours only. Best for beginners.", regions: "4–8 masses" },
  { value: 2, label: "Simplified",     desc: "Major forms + key shadows. Quick study.",                   regions: "8–20 regions" },
  { value: 3, label: "Standard",       desc: "Balanced detail + colour zones. Most paintings.",           regions: "20–60 regions" },
  { value: 4, label: "Detailed",       desc: "Fine regions, decorative elements, texture.",               regions: "60–180 regions" },
  { value: 5, label: "Full Reference", desc: "Every detected layer — complete hierarchical breakdown.",   regions: "150–400 regions" },
];

const LEVEL_BLOB_COUNTS = [4, 9, 18, 38, 80];

const ANALYSIS_TILES: { mode: ArtMode; title: string; desc: string; count: number }[] = [
  { mode: "line",        title: "Line Art",           desc: "Weighted contours — silhouette, interior forms, texture.", count: 20 },
  { mode: "notan",       title: "Value Study",        desc: "Notan — lights and darks resolved before any colour.", count: 30 },
  { mode: "temperature", title: "Colour Temperature", desc: "Warm light, cool shadow — mapped across the image.", count: 34 },
  { mode: "palette",     title: "Limited Palette",    desc: "Dominant colours by area. Mix from these, add nothing.", count: 10 },
  { mode: "light",       title: "Light & Shadow",     desc: "Gurney's five zones, from highlight to cast shadow.", count: 22 },
  { mode: "numbers",     title: "Paint by Numbers",   desc: "Flat colour blocking — how every master starts a canvas.", count: 16 },
  { mode: "dots",        title: "Structural Dots",    desc: "Connect them in order to build your under-drawing.", count: 10 },
  { mode: "colour",      title: "Tutorial Video & PDF", desc: "A progressive video lesson and a printable tutorial book.", count: 60 },
];

const VALUE_ZONE_OPTIONS = [3, 5, 7] as const;

export default function HomePage() {
  const router   = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const mainRef  = useRef<HTMLDivElement>(null);

  const [file,        setFile]        = useState<File | null>(null);
  const [preview,     setPreview]     = useState<string | null>(null);
  const [medium,      setMedium]      = useState("oil");
  const [skillLevel,  setSkillLevel]  = useState("intermediate");
  const [paletteSize, setPaletteSize] = useState(12);
  const [initialViewLevel, setInitialViewLevel] = useState(3);
  const [valueZones,  setValueZones]  = useState<3 | 5 | 7>(5);
  const [regionComplexity, setRegionComplexity] = useState(3);
  const [textureDetail, setTextureDetail] = useState(true);
  const [bgDetail,      setBgDetail]      = useState(false);
  const [dragging,    setDragging]    = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState<string | null>(null);

  useEffect(() => {
    const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${api}/mediums/${medium}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setPaletteSize(data.recommended_palette_size ?? paletteSize);
        setValueZones(data.recommended_value_zones ?? valueZones);
      })
      .catch(() => {});
  }, [medium]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Scroll choreography ─────────────────────────────────────────────────
  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    const mm = gsap.matchMedia();

    const ctx = gsap.context(() => {
      mm.add(
        { desktop: "(min-width: 768px) and (prefers-reduced-motion: no-preference)",
          mobile:  "(max-width: 767px) and (prefers-reduced-motion: no-preference)" },
        (conditions) => {
          const { desktop } = conditions.conditions as { desktop: boolean };

          // Hero canvas dims as the story begins, stays as ambient background
          gsap.to("#hero-canvas", {
            opacity: 0.16,
            scrollTrigger: { trigger: "#levels", start: "top 90%", end: "top 30%", scrub: true },
          });

          // Hero text drifts up and out
          gsap.to(".hero-inner", {
            yPercent: -18, opacity: 0.15,
            scrollTrigger: { trigger: ".hero-section", start: "top top", end: "bottom 25%", scrub: true },
          });

          if (desktop) {
            // 5-level deck: cards fan out from a stacked deck as you scroll
            const cards = gsap.utils.toArray<HTMLElement>(".level-card");
            const tl = gsap.timeline({
              scrollTrigger: {
                trigger: "#levels-pin",
                start: "clamp(top top)",
                end: "+=250%",
                pin: true,
                scrub: 1,
              },
            });
            cards.forEach((card, i) => {
              const off = i - 2;
              tl.fromTo(card,
                { y: i * -12, z: i * -80, rotationZ: off * 2, rotationY: 0, filter: `brightness(${100 - i * 11}%)` },
                { x: () => off * Math.min(window.innerWidth * 0.185, 300),
                  y: Math.abs(off) * 26, z: -Math.abs(off) * 70,
                  rotationZ: 0, rotationY: off * -9, rotationX: 5,
                  filter: `brightness(${100 - Math.abs(off) * 9}%)`,
                  duration: 1, ease: "power2.inOut" },
                i * 0.12
              );
            });
          } else {
            // Mobile: simple staggered entrance, no pinning
            gsap.utils.toArray<HTMLElement>(".level-card").forEach((card) => {
              gsap.fromTo(card,
                { y: 60, opacity: 0, rotationX: 14 },
                { y: 0, opacity: 1, rotationX: 0, duration: 0.9, ease: "power3.out",
                  scrollTrigger: { trigger: card, start: "top 92%" } }
              );
            });
          }

          // Perspective grid — tiles rise out of depth as they enter
          gsap.utils.toArray<HTMLElement>(".an-tile").forEach((tile) => {
            gsap.fromTo(tile,
              { rotationX: 38, z: -260, opacity: 0, transformOrigin: "50% 100%" },
              { rotationX: 0, z: 0, opacity: 1, ease: "none",
                scrollTrigger: { trigger: tile, start: "top 96%", end: "top 55%", scrub: 1 } }
            );
          });

          // Upload studio entrance
          gsap.fromTo("#studio-panel",
            { y: 70, opacity: 0, rotationX: 6, transformOrigin: "50% 100%" },
            { y: 0, opacity: 1, rotationX: 0, duration: 1.1, ease: "power3.out",
              scrollTrigger: { trigger: "#create", start: "top 78%" } }
          );

          // Section headings
          gsap.utils.toArray<HTMLElement>(".sec-head").forEach((h) => {
            gsap.fromTo(h, { y: 40, opacity: 0 },
              { y: 0, opacity: 1, duration: 0.9, ease: "power3.out",
                scrollTrigger: { trigger: h, start: "top 88%" } });
          });
        }
      );
    }, mainRef);

    return () => { ctx.revert(); mm.revert(); };
  }, []);

  function handleFile(f: File) {
    if (!f.type.startsWith("image/")) {
      setError("Please upload an image file (JPG, PNG, HEIC).");
      return;
    }
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setError(null);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }

  function onChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  async function submit() {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file",         file);
      form.append("medium",       medium);
      form.append("palette_size", String(paletteSize));
      form.append("initial_view_level", String(initialViewLevel));
      form.append("value_zones",  String(valueZones));
      form.append("region_complexity",  String(regionComplexity));
      form.append("texture_detail",    String(textureDetail));
      form.append("background_detail", String(bgDetail));
      form.append("skill_level",       skillLevel);

      const res = await fetch(`${API}/jobs/`, { method: "POST", body: form });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Server error: ${res.status}`);
      }
      const data = await res.json();
      router.push(`/results/${data.job_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed. Is the backend running?");
      setLoading(false);
    }
  }

  const selectedMedium = MEDIUMS.find(m => m.id === medium);
  const selectedDetail = INITIAL_VIEW_LEVELS.find(d => d.value === initialViewLevel);

  return (
    <SmoothScroll>
      <div ref={mainRef} style={{ background: "var(--bg)" }}>
        <HeroCanvas />

        {/* ── Nav ─────────────────────────────────────────────────────── */}
        <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 md:px-10 py-4"
                style={{ background: "linear-gradient(to bottom, rgba(11,9,8,0.85), transparent)" }}>
          <span className="font-display text-lg tracking-wide" style={{ color: "var(--text)" }}>
            Painting <em style={{ color: "var(--accent)" }}>Instructor</em>
          </span>
          <nav className="flex items-center gap-2 md:gap-4">
            <button onClick={() => scrollToSection("#levels")}
                    className="hidden md:inline text-sm px-3 py-2 transition-colors hover:text-white"
                    style={{ color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer" }}>
              How it works
            </button>
            <button onClick={() => scrollToSection("#analysis")}
                    className="hidden md:inline text-sm px-3 py-2 transition-colors hover:text-white"
                    style={{ color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer" }}>
              The analysis
            </button>
            <button onClick={() => scrollToSection("#create")} className="btn-primary" style={{ padding: "10px 22px", fontSize: 14 }}>
              Start painting
            </button>
          </nav>
        </header>

        <main className="relative z-10">

          {/* ── Hero ───────────────────────────────────────────────────── */}
          <section className="hero-section min-h-screen flex items-center justify-center px-6">
            <div className="hero-inner text-center max-w-4xl pt-20">
              <p className="eyebrow mb-6 fade-up">AI Atelier — from photograph to painting lesson</p>
              <h1 className="font-display text-5xl md:text-7xl lg:text-8xl leading-[1.04] mb-8" style={{ color: "var(--text)" }}>
                <KineticTitle text="Every photo hides" delay={0.15} />
                <br />
                <em>
                  <KineticTitle text="a painting." delay={0.55} gradient />
                </em>
              </h1>
              <p className="text-lg md:text-xl max-w-xl mx-auto mb-10 fade-up" style={{ color: "var(--text-dim)", animationDelay: "0.9s" }}>
                Upload a reference photo. We deconstruct it the way a master would —
                values, temperature, structure — and teach you to paint it, level by level.
              </p>
              <div className="flex items-center justify-center gap-4 flex-wrap fade-up" style={{ animationDelay: "1.1s" }}>
                <button onClick={() => scrollToSection("#create")} className="btn-primary">
                  Upload a photo →
                </button>
                <button onClick={() => scrollToSection("#levels")} className="btn-ghost">
                  See how it works
                </button>
              </div>
              <div className="scroll-hint mt-16 text-2xl" style={{ color: "var(--accent-dim)" }}>↓</div>
            </div>
          </section>

          {/* ── Five levels: pinned 3D deck ────────────────────────────── */}
          <section id="levels" className="relative">
            <div className="sec-head text-center px-6 pt-28 pb-4 md:pb-0">
              <p className="eyebrow mb-4">The method</p>
              <h2 className="font-display text-4xl md:text-6xl" style={{ color: "var(--text)" }}>
                Five levels of <em className="text-gradient">seeing</em>
              </h2>
              <p className="mt-5 max-w-lg mx-auto" style={{ color: "var(--text-dim)" }}>
                One merge-tree hierarchy, five genuine cuts. The same painting,
                refined from a handful of masses to full reference detail.
              </p>
            </div>

            <div id="levels-pin" className="min-h-screen flex items-center justify-center"
                 style={{ perspective: 1600 }}>
              <div className="relative w-full flex items-center justify-center py-14 md:py-0"
                   style={{ transformStyle: "preserve-3d", minHeight: 480 }}>
                <div className="flex flex-col md:block items-center gap-8 w-full md:w-auto px-6 md:px-0">
                  {INITIAL_VIEW_LEVELS.map((lvl, i) => (
                    <div key={lvl.value}
                         className="level-card md:absolute md:top-1/2 md:left-1/2 md:-translate-x-1/2 md:-translate-y-1/2 w-full max-w-[300px] md:w-[280px] rounded-2xl overflow-hidden"
                         style={{
                           transformStyle: "preserve-3d",
                           background: "var(--surface)",
                           border: "1px solid var(--border)",
                           boxShadow: "0 30px 60px rgba(0,0,0,0.55)",
                           zIndex: 10 - i,
                           willChange: "transform",
                         }}>
                      <div style={{ aspectRatio: "4/3" }}>
                        <ArtTile mode="colour" seed={7} count={LEVEL_BLOB_COUNTS[i]} />
                      </div>
                      <div className="p-5">
                        <div className="flex items-baseline justify-between mb-1.5">
                          <p className="font-display text-xl" style={{ color: "var(--text)" }}>{lvl.label}</p>
                          <span className="text-xs font-mono" style={{ color: "var(--accent)" }}>0{lvl.value}</span>
                        </div>
                        <p className="text-xs leading-relaxed mb-3" style={{ color: "var(--text-dim)" }}>{lvl.desc}</p>
                        <span className="text-[11px] px-2.5 py-1 rounded-full"
                              style={{ background: "rgba(220,165,94,0.12)", color: "var(--accent)", border: "1px solid rgba(220,165,94,0.25)" }}>
                          {lvl.regions}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* ── Analysis: perspective grid ─────────────────────────────── */}
          <section id="analysis" className="px-6 md:px-12 pt-28 pb-24 max-w-7xl mx-auto">
            <div className="sec-head text-center mb-16">
              <p className="eyebrow mb-4">What you receive</p>
              <h2 className="font-display text-4xl md:text-6xl" style={{ color: "var(--text)" }}>
                A complete <em className="text-gradient">atelier analysis</em>
              </h2>
              <p className="mt-5 max-w-lg mx-auto" style={{ color: "var(--text-dim)" }}>
                Eight studies generated from your photo — the same preparation
                a classical painter would make before touching the canvas.
              </p>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-5" style={{ perspective: 1200 }}>
              {ANALYSIS_TILES.map((t, i) => (
                <div key={t.title} className="an-tile rounded-2xl overflow-hidden group"
                     style={{
                       background: "var(--surface)",
                       border: "1px solid var(--border)",
                       transformStyle: "preserve-3d",
                       willChange: "transform",
                     }}>
                  <div className="relative" style={{ aspectRatio: "4/3", overflow: "hidden" }}>
                    <div className="transition-transform duration-700 group-hover:scale-110" style={{ height: "100%" }}>
                      <ArtTile mode={t.mode} seed={7 + i * 13} count={t.count} />
                    </div>
                    {t.mode === "colour" && (
                      <div className="absolute inset-0 flex items-center justify-center"
                           style={{ background: "rgba(11,9,8,0.45)" }}>
                        <div className="w-14 h-14 rounded-full flex items-center justify-center"
                             style={{ background: "rgba(242,192,120,0.92)", color: "#14100b", fontSize: 20, paddingLeft: 4 }}>
                          ▶
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="p-4">
                    <p className="font-display text-base mb-1" style={{ color: "var(--text)" }}>{t.title}</p>
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>{t.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Upload studio ──────────────────────────────────────────── */}
          <section id="create" className="px-6 pt-16 pb-32 flex flex-col items-center">
            <div className="sec-head text-center mb-12">
              <p className="eyebrow mb-4">Your turn</p>
              <h2 className="font-display text-4xl md:text-6xl" style={{ color: "var(--text)" }}>
                The <em className="text-gradient">studio</em>
              </h2>
            </div>

            <div id="studio-panel" className="panel w-full max-w-2xl p-6 md:p-10 space-y-8">

              {/* Drop zone */}
              <div
                onClick={() => inputRef.current?.click()}
                onDrop={onDrop}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                className="relative cursor-pointer rounded-2xl border-2 border-dashed transition-all flex items-center justify-center overflow-hidden"
                style={{
                  borderColor: dragging ? "var(--accent)" : "var(--border)",
                  background:  dragging ? "rgba(220,165,94,0.06)" : "rgba(11,9,8,0.4)",
                  minHeight:   preview  ? "auto" : 220,
                  boxShadow:   dragging ? "0 0 40px rgba(220,165,94,0.15) inset" : "none",
                }}
              >
                {preview ? (
                  <img src={preview} alt="preview" className="w-full object-contain max-h-80" />
                ) : (
                  <div className="text-center py-12 px-6">
                    <div className="w-16 h-16 mx-auto mb-5 rounded-full flex items-center justify-center blob-pulse"
                         style={{ background: "linear-gradient(140deg, rgba(220,165,94,0.2), rgba(191,91,69,0.2))", border: "1px solid rgba(220,165,94,0.35)" }}>
                      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="3" width="18" height="18" rx="3"/>
                        <circle cx="8.5" cy="8.5" r="1.5"/>
                        <path d="M21 15l-5-5L5 21"/>
                      </svg>
                    </div>
                    <p className="font-display text-lg mb-1" style={{ color: "var(--text)" }}>
                      Drop your reference photo here
                    </p>
                    <p className="text-sm" style={{ color: "var(--text-dim)" }}>
                      JPG, PNG, HEIC — any size
                    </p>
                  </div>
                )}
                <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={onChange} />
              </div>

              {preview && (
                <button className="text-sm underline" style={{ color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer" }}
                        onClick={() => { setFile(null); setPreview(null); }}>
                  Choose a different photo
                </button>
              )}

              {/* Medium selector */}
              <div>
                <label className="label-xs block mb-3">Painting medium</label>
                <div className="flex flex-wrap gap-2">
                  {MEDIUMS.map(m => (
                    <button key={m.id} onClick={() => setMedium(m.id)} className="chip" data-active={medium === m.id}>
                      <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: m.dot }} />
                      {m.label}
                    </button>
                  ))}
                </div>
                {selectedMedium && (
                  <p className="text-xs mt-2.5" style={{ color: "var(--text-dim)" }}>{selectedMedium.tip}</p>
                )}
              </div>

              {/* Skill level */}
              <div>
                <label className="label-xs block mb-3">Your level</label>
                <div className="flex flex-wrap gap-2">
                  {SKILL_LEVELS.map(s => (
                    <button key={s.id} onClick={() => setSkillLevel(s.id)} className="chip" data-active={skillLevel === s.id}>
                      {s.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs mt-2.5" style={{ color: "var(--text-dim)" }}>
                  {SKILL_LEVELS.find(s => s.id === skillLevel)?.tip}
                </p>
              </div>

              {/* Palette size */}
              <div>
                <label className="label-xs block mb-3">
                  Palette size — <span style={{ color: "var(--accent)" }}>{paletteSize} colours</span>
                </label>
                <input type="range" min={6} max={32} step={2} value={paletteSize}
                       onChange={e => setPaletteSize(Number(e.target.value))}
                       className="w-full" />
                <div className="flex justify-between text-xs mt-1.5" style={{ color: "var(--text-dim)" }}>
                  <span>6 (minimal)</span><span>32 (detailed)</span>
                </div>
              </div>

              {/* Value zones */}
              <div>
                <label className="label-xs block mb-3">Value zones</label>
                <div className="flex gap-2">
                  {VALUE_ZONE_OPTIONS.map(n => (
                    <button key={n} onClick={() => setValueZones(n)} className="chip" data-active={valueZones === n}>
                      {n} zones
                    </button>
                  ))}
                </div>
                <p className="text-xs mt-2.5" style={{ color: "var(--text-dim)" }}>
                  3 = shadow / midtone / light &nbsp;·&nbsp; 5 = standard &nbsp;·&nbsp; 7 = maximum tonal range
                </p>
              </div>

              {/* Initial view level */}
              <div>
                <label className="label-xs block mb-3">Starting view level</label>
                <div className="flex flex-wrap gap-2">
                  {INITIAL_VIEW_LEVELS.map(d => (
                    <button key={d.value} onClick={() => setInitialViewLevel(d.value)} className="chip" data-active={initialViewLevel === d.value}>
                      {d.label}
                    </button>
                  ))}
                </div>
                {selectedDetail && (
                  <p className="text-xs mt-2.5" style={{ color: "var(--text-dim)" }}>{selectedDetail.desc}</p>
                )}
                <p className="text-xs mt-1" style={{ color: "var(--text-dim)", opacity: 0.7 }}>
                  All 5 levels are always generated — this only picks which one opens first.
                </p>
              </div>

              {/* Region complexity */}
              <div>
                <label className="label-xs block mb-3">
                  Region complexity — <span style={{ color: "var(--accent)" }}>
                    {["", "Minimal", "Simplified", "Balanced", "Detailed", "Maximum"][regionComplexity]}
                  </span>
                </label>
                <input type="range" min={1} max={5} step={1} value={regionComplexity}
                       onChange={e => setRegionComplexity(Number(e.target.value))}
                       className="w-full" />
                <div className="flex justify-between text-xs mt-1.5" style={{ color: "var(--text-dim)" }}>
                  <span>1 (fewer, broader)</span><span>5 (more, finer)</span>
                </div>
                <p className="text-xs mt-1" style={{ color: "var(--text-dim)", opacity: 0.7 }}>
                  Controls how many superpixels seed the hierarchy. Higher = more regions per level.
                </p>
              </div>

              {/* Texture + background detail toggles */}
              <div className="flex gap-6 flex-wrap">
                {[
                  { label: "Texture edges",    checked: textureDetail, set: setTextureDetail,
                    tip: "Include high-frequency texture contours (fabric, bark, fur)." },
                  { label: "Background edges", checked: bgDetail,      set: setBgDetail,
                    tip: "Analyse edges behind the main subject." },
                ].map(({ label, checked, set, tip }) => (
                  <label key={label} className="flex items-center gap-3 cursor-pointer select-none">
                    <button
                      role="switch" aria-checked={checked}
                      onClick={() => set(!checked)}
                      className="relative w-10 h-6 rounded-full transition-colors"
                      style={{
                        background: checked ? "linear-gradient(120deg, var(--accent-bright), var(--accent))" : "var(--surface-2)",
                        border: "1px solid var(--border)",
                        cursor: "pointer",
                      }}>
                      <span className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform"
                            style={{ transform: checked ? "translateX(16px)" : "translateX(0)" }} />
                    </button>
                    <span className="text-sm" style={{ color: checked ? "var(--text)" : "var(--text-dim)" }}>
                      {label}
                    </span>
                    <span className="hidden sm:inline text-xs" style={{ color: "var(--text-dim)", opacity: 0.7 }}>{tip}</span>
                  </label>
                ))}
              </div>

              {/* Error */}
              {error && (
                <p className="text-sm px-4 py-3 rounded-xl" style={{ background: "rgba(191,91,69,0.12)", color: "#e0876f", border: "1px solid rgba(191,91,69,0.3)" }}>
                  {error}
                </p>
              )}

              {/* Submit */}
              <button onClick={submit} disabled={!file || loading} className="btn-primary w-full" style={{ padding: "17px 28px" }}>
                {loading ? "Uploading…" : "Generate Tutorial →"}
              </button>
            </div>
          </section>

          {/* ── Footer ─────────────────────────────────────────────────── */}
          <footer className="px-6 py-10 text-center" style={{ borderTop: "1px solid var(--border)" }}>
            <p className="font-display text-sm mb-1" style={{ color: "var(--text-dim)" }}>
              Painting <em style={{ color: "var(--accent-dim)" }}>Instructor</em>
            </p>
            <p className="text-xs" style={{ color: "var(--text-dim)", opacity: 0.6 }}>
              Line art · Value study · Colour temperature · Paint by numbers · Progressive video lessons
            </p>
          </footer>
        </main>
      </div>
    </SmoothScroll>
  );
}
