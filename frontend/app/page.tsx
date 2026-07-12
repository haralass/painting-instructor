"use client";
import { useState, useRef, useEffect, DragEvent, ChangeEvent } from "react";
import { useRouter } from "next/navigation";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import SmoothScroll, { scrollToSection } from "./components/SmoothScroll";
import AtelierHero from "./components/AtelierHero";
import KineticTitle from "./components/KineticTitle";
import EvolvingCanvas, { STAGE_VISUAL_COUNT } from "./components/EvolvingCanvas";
import { painterUserId } from "./lib/user";
import { CAPABILITIES, DETAIL_LEVELS, MEDIUM_FALLBACKS } from "./lib/contract.generated";

// The one shared catalogue: studies shown here are exactly the advertised
// capabilities with real sample assets — the same list the gallery renders
// and the workspace unlocks. Deliverables (video/PDF) are presented apart,
// never as studies.
const STUDY_CARDS  = CAPABILITIES.filter(c => c.advertised && c.sample);
const DELIVERABLES = CAPABILITIES.filter(c => c.category === "deliverable");
const TEACHING     = CAPABILITIES.filter(c => c.category === "teaching" && c.advertised);

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const MEDIUMS = [
  { id: "oil",        label: "Oil Paint",   dot: "#b4511f", tip: "Rich blending, slow drying. Best for realism and portraiture." },
  { id: "watercolor", label: "Watercolour", dot: "#3e5c76", tip: "Transparent layers. Work light-to-dark, preserve whites." },
  { id: "acrylic",    label: "Acrylic",     dot: "#c9932e", tip: "Fast-drying, versatile. Can mimic oil or watercolour." },
  { id: "pencil",     label: "Pencil",      dot: "#8a8272", tip: "Graphite hatching. Build value through layered strokes." },
  { id: "charcoal",   label: "Charcoal",    dot: "#41504f", tip: "Broad marks, erasable highlights. Great for tonal studies." },
  { id: "digital",    label: "Digital",     dot: "#6f7d5c", tip: "Layers, undo, and infinite colour — but the same value discipline." },
];

const SKILL_LEVELS = [
  { id: "beginner",     label: "Beginner",     tip: "Adds a value warm-up rehearsal before the real painting." },
  { id: "intermediate", label: "Intermediate", tip: "The standard lesson for your medium." },
  { id: "advanced",     label: "Advanced",     tip: "Adds a measured self-critique pass at the end." },
];

const VALUE_ZONE_OPTIONS = [3, 5, 7] as const;

type Stage = {
  order: number;
  name: string;
  description: string;
  why?: string;
  analysis_layers?: string[];
};

type Brand = {
  id: string;
  name: string;
  medium: string;
  tube_count: number;
};

type MediumCfg = {
  name: string;
  recommended_value_zones?: number;
  recommended_palette_size?: number;
  stages: Stage[];
  instructions?: Record<string, string>;
};

/* Per-medium stage fallback — GENERATED from the real backend configs
   (contract.generated.ts), shown until the live config arrives or if the
   backend is down, so the method section never lies about the lesson. */
function fallbackCfg(mediumId: string): MediumCfg {
  const fb = MEDIUM_FALLBACKS[mediumId] ?? MEDIUM_FALLBACKS.oil;
  return { name: fb.name, stages: fb.stages };
}

export default function HomePage() {
  const router   = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const mainRef  = useRef<HTMLDivElement>(null);

  const [file,        setFile]        = useState<File | null>(null);
  const [preview,     setPreview]     = useState<string | null>(null);
  const [medium,      setMedium]      = useState("oil");
  const [skillLevel,  setSkillLevel]  = useState("intermediate");
  const [brands,      setBrands]      = useState<Brand[]>([]);
  const [brandId,     setBrandId]     = useState("");   // "" = generic palette
  const [paletteSize, setPaletteSize] = useState(12);
  const [initialViewLevel, setInitialViewLevel] = useState(3);
  const [valueZones,  setValueZones]  = useState<3 | 5 | 7>(5);
  const [regionComplexity, setRegionComplexity] = useState(3);
  const [textureDetail, setTextureDetail] = useState(true);
  const [bgDetail,      setBgDetail]      = useState(false);
  const [dragging,    setDragging]    = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  // Implementation-level knobs (superpixel seeding, raw cluster counts, edge
  // toggles) live behind this disclosure — painters shouldn't need them.
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [mediumCfg,   setMediumCfg]   = useState<MediumCfg>(() => fallbackCfg("oil"));
  const [activeStage, setActiveStage] = useState(0);

  // Save & continue: recent projects from the backend store. Empty (and the
  // strip hidden) when the backend is down or nothing was ever uploaded.
  type RecentProject = {
    id: string; job_id: string | null; title: string; medium: string;
    reference_path: string; updated_at: string;
  };
  const [recent, setRecent] = useState<RecentProject[]>([]);
  useEffect(() => {
    fetch(`${API}/projects?limit=6`)
      .then(r => (r.ok ? r.json() : []))
      .then((data: RecentProject[]) => setRecent(Array.isArray(data) ? data.filter(p => p.job_id) : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    // Show the generated fallback for the new medium immediately; the live
    // config replaces it when (if) the backend answers.
    setMediumCfg(fallbackCfg(medium));
    const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${api}/mediums/${medium}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setMediumCfg(data);
        setPaletteSize(data.recommended_palette_size ?? paletteSize);
        setValueZones(data.recommended_value_zones ?? valueZones);
      })
      .catch(() => {});
  }, [medium]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Real-paint tube sets for the chosen medium — "mix from YOUR set". Refetched
  // whenever the medium changes; the field is optional and resets to the generic
  // palette when the current brand isn't offered for the new medium.
  useEffect(() => {
    const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    fetch(`${api}/brands?medium=${encodeURIComponent(medium)}`)
      .then(r => r.ok ? r.json() : [])
      .then((data: Brand[]) => {
        const list = Array.isArray(data) ? data : [];
        setBrands(list);
        setBrandId(prev => (list.some(b => b.id === prev) ? prev : ""));
      })
      .catch(() => { setBrands([]); setBrandId(""); });
  }, [medium]);

  const stages = mediumCfg.stages ?? [];

  // ── The evolving canvas follows whichever stage block is mid-viewport ──
  useEffect(() => {
    const blocks = document.querySelectorAll<HTMLElement>(".stage-block");
    if (!blocks.length) return;
    const io = new IntersectionObserver(
      entries => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setActiveStage(Number((e.target as HTMLElement).dataset.idx ?? 0));
          }
        }
      },
      { rootMargin: "-42% 0px -42% 0px" }
    );
    blocks.forEach(b => io.observe(b));
    return () => io.disconnect();
  }, [stages.length]);

  // ── Scroll choreography ─────────────────────────────────────────────────
  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
    const mm = gsap.matchMedia();

    const ctx = gsap.context(() => {
      mm.add("(prefers-reduced-motion: no-preference)", () => {
        // The studio scene recedes into the paper as the method begins;
        // the stroke it painted hands over to the page's painted thread.
        gsap.to("#hero-canvas", {
          opacity: 0.09,
          scrollTrigger: { trigger: "#method", start: "top 90%", end: "top 25%", scrub: true },
        });

        gsap.to(".hero-inner", {
          yPercent: -16, opacity: 0.1,
          scrollTrigger: { trigger: ".hero-section", start: "top top", end: "bottom 25%", scrub: true },
        });

        // The painted thread draws itself down the method section
        const thread = document.querySelector<SVGPathElement>("#paint-thread path");
        if (thread) {
          const len = thread.getTotalLength();
          gsap.fromTo(thread,
            { strokeDasharray: len, strokeDashoffset: len },
            { strokeDashoffset: 0, ease: "none",
              scrollTrigger: { trigger: "#method", start: "top 65%", end: "bottom 75%", scrub: 0.6 } }
          );
        }

        gsap.utils.toArray<HTMLElement>(".stage-block").forEach(block => {
          gsap.fromTo(block,
            { x: 44, opacity: 0 },
            { x: 0, opacity: 1, duration: 0.8, ease: "power3.out",
              scrollTrigger: { trigger: block, start: "top 86%" } }
          );
        });

        gsap.utils.toArray<HTMLElement>(".an-tile").forEach(tile => {
          gsap.fromTo(tile,
            { rotationX: 38, z: -260, opacity: 0, transformOrigin: "50% 100%" },
            { rotationX: 0, z: 0, opacity: 1, ease: "none",
              scrollTrigger: { trigger: tile, start: "top 96%", end: "top 55%", scrub: 1 } }
          );
        });

        gsap.fromTo("#studio-panel",
          { y: 70, opacity: 0, rotationX: 6, transformOrigin: "50% 100%" },
          { y: 0, opacity: 1, rotationX: 0, duration: 1.1, ease: "power3.out",
            scrollTrigger: { trigger: "#create", start: "top 78%" } }
        );

        gsap.utils.toArray<HTMLElement>(".sec-head").forEach(h => {
          gsap.fromTo(h, { y: 40, opacity: 0 },
            { y: 0, opacity: 1, duration: 0.9, ease: "power3.out",
              scrollTrigger: { trigger: h, start: "top 88%" } });
        });
      });
    }, mainRef);

    return () => { ctx.revert(); mm.revert(); };
  }, [stages.length]);

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
      if (brandId) form.append("brand_id", brandId);
      const uid = painterUserId();
      if (uid) form.append("user_id", uid);

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
  const selectedDetail = DETAIL_LEVELS.find(d => d.level === initialViewLevel);
  const visualFor = (i: number) =>
    Math.round((i / Math.max(stages.length - 1, 1)) * (STAGE_VISUAL_COUNT - 1));

  return (
    <SmoothScroll>
      <div ref={mainRef} style={{ background: "var(--bg)" }}>
        <AtelierHero />

        {/* ── Nav ─────────────────────────────────────────────────────── */}
        <header className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 md:px-10 py-4"
                style={{ background: "linear-gradient(to bottom, rgba(248,244,234,0.92), transparent)" }}>
          <span className="font-display text-lg tracking-wide" style={{ color: "var(--ink)" }}>
            Painting <em style={{ color: "var(--accent)" }}>Instructor</em>
          </span>
          <nav className="flex items-center gap-2 md:gap-4">
            <button onClick={() => scrollToSection("#method")}
                    className="hidden md:inline text-sm px-3 py-2 transition-colors"
                    style={{ color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer" }}>
              The method
            </button>
            <button onClick={() => scrollToSection("#analysis")}
                    className="hidden md:inline text-sm px-3 py-2 transition-colors"
                    style={{ color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer" }}>
              Your studies
            </button>
            <a href="/gallery"
               className="hidden md:inline text-sm px-3 py-2 transition-colors"
               style={{ color: "var(--text-dim)", textDecoration: "none" }}>
              Gallery
            </a>
            <button onClick={() => scrollToSection("#create")} className="btn-primary" style={{ padding: "10px 22px", fontSize: 14 }}>
              Start painting
            </button>
          </nav>
        </header>

        <main className="relative z-10">

          {/* ── Hero: the master's stroke ──────────────────────────────── */}
          <section className="hero-section min-h-screen flex items-center px-6 md:px-12">
            <div className="hero-inner max-w-7xl mx-auto w-full">
              <div className="max-w-xl pt-24 md:pt-0">
                <p className="eyebrow mb-6 fade-up">The atelier — from photograph to painting lesson</p>
                <h1 className="font-display text-5xl md:text-7xl lg:text-8xl leading-[1.04] mb-8" style={{ color: "var(--ink)" }}>
                  <KineticTitle text="Every photo hides" delay={0.15} />
                  <br />
                  <em>
                    <KineticTitle text="a painting." delay={0.55} gradient />
                  </em>
                </h1>
                <p className="text-lg md:text-xl max-w-lg mb-10 fade-up" style={{ color: "var(--text-dim)", animationDelay: "0.9s" }}>
                  Upload a reference photo. We deconstruct it the way a master would —
                  values, temperature, structure — then teach you to paint it,
                  stage by stage, stroke by stroke.
                </p>
                <div className="flex items-center gap-4 flex-wrap fade-up" style={{ animationDelay: "1.1s" }}>
                  <button onClick={() => scrollToSection("#create")} className="btn-primary">
                    Upload a photo →
                  </button>
                  <button onClick={() => scrollToSection("#method")} className="btn-ghost">
                    Watch the method
                  </button>
                </div>
                <div className="scroll-hint mt-14 text-2xl" style={{ color: "var(--accent)" }}>↓</div>
              </div>
            </div>
          </section>

          {/* ── The method: one painting, painted as you scroll ────────── */}
          <section id="method" className="relative px-6 md:px-12 pt-28 pb-24 max-w-7xl mx-auto">
            {/* The painted thread the hero stroke hands over to */}
            <svg id="paint-thread" aria-hidden
                 className="absolute left-1/2 top-0 h-full hidden md:block"
                 style={{ width: 120, transform: "translateX(-50%)", pointerEvents: "none" }}
                 viewBox="0 0 120 2400" preserveAspectRatio="xMidYMax slice">
              <path d="M60 0 C 30 220, 92 380, 58 620 C 26 850, 96 1010, 62 1260 C 30 1500, 90 1660, 58 1910 C 30 2130, 80 2260, 60 2400"
                    fill="none" stroke="var(--accent)" strokeWidth="7" strokeLinecap="round" opacity="0.28" />
            </svg>

            <div className="sec-head text-center mb-10 relative">
              <p className="eyebrow mb-4">The method</p>
              <h2 className="font-display text-4xl md:text-6xl" style={{ color: "var(--ink)" }}>
                Watch the painting <em className="text-gradient">happen</em>
              </h2>
              <p className="mt-5 max-w-xl mx-auto" style={{ color: "var(--text-dim)" }}>
                These are the real stages of your lesson — pulled live from the
                teaching engine, in the exact order a painter works. Pick a
                medium: the order changes with it.
              </p>
              <div className="flex flex-wrap justify-center gap-2 mt-7">
                {MEDIUMS.map(m => (
                  <button key={m.id} onClick={() => setMedium(m.id)} className="chip" data-active={medium === m.id}>
                    <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: m.dot }} />
                    {m.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="md:grid md:grid-cols-2 md:gap-14 relative">
              {/* The canvas being painted — stays put while the stages scroll,
                  on mobile too (smaller) so the "it evolves as you read" idea
                  survives on a phone. Paper-coloured band hides stages behind. */}
              <div className="sticky top-14 md:top-24 self-start z-10 mb-6 md:mb-0 pt-3 pb-4 md:py-0"
                   style={{ background: "var(--bg)" }}>
                <div className="rounded-sm overflow-hidden mx-auto w-full max-w-[220px] md:max-w-[560px]"
                     style={{
                       aspectRatio: "4/3",
                       border: "10px solid var(--paper)",
                       outline: "1px solid var(--border-strong)",
                       boxShadow: "0 34px 80px rgba(63,48,28,0.18), 0 4px 14px rgba(63,48,28,0.1)",
                       transform: "rotate(-0.6deg)",
                       background: "var(--paper)",
                     }}>
                  <EvolvingCanvas stage={visualFor(activeStage)} seed={7} />
                </div>
                <p className="text-center text-xs md:text-sm mt-3 md:mt-5 font-display italic" style={{ color: "var(--text-dim)" }}>
                  {stages[activeStage]
                    ? <>Stage {String(stages[activeStage].order).padStart(2, "0")} — {stages[activeStage].name}</>
                    : "The blank canvas"}
                </p>
              </div>

              {/* The real stages, in the real order */}
              <div className="space-y-6 relative" style={{ zIndex: 2 }}>
                {stages.map((s, i) => (
                  <div key={`${medium}-${s.order}`} data-idx={i}
                       className="stage-block panel p-6 md:p-7">
                    <div className="flex items-baseline justify-between mb-2">
                      <p className="font-display text-2xl" style={{ color: "var(--ink)" }}>{s.name}</p>
                      <span className="text-sm font-mono" style={{ color: "var(--accent)" }}>
                        {String(s.order).padStart(2, "0")} / {String(stages[stages.length - 1]?.order ?? 0).padStart(2, "0")}
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed mb-3" style={{ color: "var(--text)" }}>{s.description}</p>
                    {s.why && (
                      <p className="text-sm leading-relaxed pl-4 italic"
                         style={{ color: "var(--text-dim)", borderLeft: "2px solid var(--accent)" }}>
                        Why — {s.why}
                      </p>
                    )}
                  </div>
                ))}

                {/* The lesson bends to the student without renumbering stages */}
                <div className="grid sm:grid-cols-2 gap-4">
                  <div className="p-5 rounded-2xl" style={{ background: "var(--surface-2)", border: "1px dashed var(--border-strong)" }}>
                    <span className="text-[11px] px-2.5 py-1 rounded-full font-semibold"
                          style={{ background: "var(--sage)", color: "var(--paper)" }}>Beginner adds</span>
                    <p className="font-display text-lg mt-3 mb-1" style={{ color: "var(--ink)" }}>Value warm-up</p>
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>
                      A rehearsal on the notan before the real painting begins.
                    </p>
                  </div>
                  <div className="p-5 rounded-2xl" style={{ background: "var(--surface-2)", border: "1px dashed var(--border-strong)" }}>
                    <span className="text-[11px] px-2.5 py-1 rounded-full font-semibold"
                          style={{ background: "var(--cool)", color: "var(--paper)" }}>Advanced adds</span>
                    <p className="font-display text-lg mt-3 mb-1" style={{ color: "var(--ink)" }}>Self-critique pass</p>
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>
                      Photograph your painting and upload it — the engine measures it against the plan.
                    </p>
                  </div>
                </div>

                <p className="text-sm leading-relaxed p-5 rounded-2xl"
                   style={{ color: "var(--text-dim)", background: "rgba(180,81,31,0.06)", border: "1px solid rgba(180,81,31,0.18)" }}>
                  And this is only the skeleton: for your photo, every stage unpacks
                  into concrete moves — which mass to block in first, where the light
                  enters, what to mix — read straight from your image.
                </p>
              </div>
            </div>
          </section>

          {/* ── Your studies ───────────────────────────────────────────── */}
          <section id="analysis" className="px-6 md:px-12 pt-28 pb-24 max-w-7xl mx-auto">
            <div className="sec-head text-center mb-16">
              <p className="eyebrow mb-4">What you receive</p>
              <h2 className="font-display text-4xl md:text-6xl" style={{ color: "var(--ink)" }}>
                A complete <em className="text-gradient">atelier analysis</em>
              </h2>
              <p className="mt-5 max-w-lg mx-auto" style={{ color: "var(--text-dim)" }}>
                {STUDY_CARDS.length} studies generated from your photo — every one
                below is a real output from the demo reference, the same list you
                get in the workspace.
              </p>
            </div>

            <div className="grid grid-cols-2 lg:grid-cols-4 gap-5" style={{ perspective: 1200 }}>
              {STUDY_CARDS.map(c => (
                <div key={c.id} className="an-tile rounded-2xl overflow-hidden group"
                     style={{
                       background: "var(--surface)",
                       border: "1px solid var(--border)",
                       boxShadow: "0 14px 40px rgba(63,48,28,0.07)",
                       transformStyle: "preserve-3d",
                       willChange: "transform",
                     }}>
                  <div className="relative" style={{ aspectRatio: "4/3", overflow: "hidden", borderBottom: "1px solid var(--border)" }}>
                    <img src={`/samples/demo1/${c.sample}`} alt={`${c.name} study, generated from the demo reference.`}
                         loading="lazy"
                         className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" />
                  </div>
                  <div className="p-4">
                    <p className="font-display text-base mb-1" style={{ color: "var(--ink)" }}>{c.name}</p>
                    <p className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>{c.description}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Deliverables + teaching surfaces — real capabilities, but not
                image studies, so they are never counted or shown as such. */}
            <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 mt-10">
              {[...TEACHING, ...DELIVERABLES].map(c => (
                <div key={c.id} className="p-5 rounded-2xl"
                     style={{ background: "var(--surface-2)", border: "1px dashed var(--border-strong)" }}>
                  <span className="text-[11px] px-2.5 py-1 rounded-full font-semibold"
                        style={{
                          background: c.category === "deliverable" ? "var(--cool)" : "var(--sage)",
                          color: "var(--paper)",
                        }}>
                    {c.category === "deliverable" ? "Deliverable" : "Interactive"}
                  </span>
                  <p className="font-display text-lg mt-3 mb-1" style={{ color: "var(--ink)" }}>{c.name}</p>
                  <p className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>{c.description}</p>
                </div>
              ))}
            </div>
          </section>

          {/* ── Continue where you left off ────────────────────────────── */}
          {recent.length > 0 && (
            <section className="px-6 md:px-12 pb-4 max-w-7xl mx-auto">
              <div className="flex items-center gap-3 mb-4">
                <p className="label-xs">Continue where you left off</p>
                <span className="h-px flex-1" style={{ background: "var(--border)" }} />
              </div>
              <div className="flex gap-4 overflow-x-auto pb-2">
                {recent.map(p => (
                  <a key={p.id} href={`/results/${p.job_id}`}
                     className="flex-shrink-0 w-52 rounded-2xl overflow-hidden transition-transform duration-300 hover:-translate-y-1"
                     style={{ background: "var(--surface)", border: "1px solid var(--border)", textDecoration: "none" }}>
                    <img src={`${API}/outputs/${p.reference_path}`} alt=""
                         className="w-full object-cover" style={{ aspectRatio: "4/3" }}
                         onError={e => { (e.target as HTMLImageElement).style.display = "none"; }} />
                    <div className="p-3">
                      <p className="text-sm font-medium truncate" style={{ color: "var(--ink)" }}>{p.title}</p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
                        {p.medium} · {new Date(p.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                  </a>
                ))}
              </div>
            </section>
          )}

          {/* ── The studio ─────────────────────────────────────────────── */}
          <section id="create" className="px-6 pt-16 pb-32 flex flex-col items-center">
            <div className="sec-head text-center mb-12">
              <p className="eyebrow mb-4">Your turn</p>
              <h2 className="font-display text-4xl md:text-6xl" style={{ color: "var(--ink)" }}>
                The <em className="text-gradient">studio</em>
              </h2>
              <p className="mt-5 max-w-md mx-auto text-sm" style={{ color: "var(--text-dim)" }}>
                Every control the engine understands, in the order you&rsquo;d set up
                a real easel. The defaults follow your medium — change anything.
              </p>
            </div>

            <div id="studio-panel" className="panel w-full max-w-2xl p-6 md:p-10 space-y-10">

              {/* 1 · Reference */}
              <div>
                <p className="font-display text-xl mb-1" style={{ color: "var(--ink)" }}>
                  <span style={{ color: "var(--accent)" }}>1.</span> Your reference
                </p>
                <p className="text-xs mb-4" style={{ color: "var(--text-dim)" }}>
                  The photo you want to learn to paint.
                </p>
                <div
                  onClick={() => inputRef.current?.click()}
                  onDrop={onDrop}
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  className="relative cursor-pointer rounded-2xl border-2 border-dashed transition-all flex items-center justify-center overflow-hidden"
                  style={{
                    borderColor: dragging ? "var(--accent)" : "var(--border-strong)",
                    background:  dragging ? "rgba(180,81,31,0.05)" : "var(--surface-2)",
                    minHeight:   preview  ? "auto" : 220,
                    boxShadow:   dragging ? "0 0 40px rgba(180,81,31,0.12) inset" : "none",
                  }}
                >
                  {preview ? (
                    <img src={preview} alt="preview" className="w-full object-contain max-h-80" />
                  ) : (
                    <div className="text-center py-12 px-6">
                      <div className="w-16 h-16 mx-auto mb-5 rounded-full flex items-center justify-center blob-pulse"
                           style={{ background: "rgba(180,81,31,0.1)", border: "1px solid rgba(180,81,31,0.3)" }}>
                        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="3" width="18" height="18" rx="3"/>
                          <circle cx="8.5" cy="8.5" r="1.5"/>
                          <path d="M21 15l-5-5L5 21"/>
                        </svg>
                      </div>
                      <p className="font-display text-lg mb-1" style={{ color: "var(--ink)" }}>
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
                  <button className="text-sm underline mt-3" style={{ color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer" }}
                          onClick={() => { setFile(null); setPreview(null); }}>
                    Choose a different photo
                  </button>
                )}
              </div>

              {/* 2 · Medium & level */}
              <div>
                <p className="font-display text-xl mb-1" style={{ color: "var(--ink)" }}>
                  <span style={{ color: "var(--accent)" }}>2.</span> Medium &amp; your level
                </p>
                <p className="text-xs mb-4" style={{ color: "var(--text-dim)" }}>
                  The lesson&rsquo;s stages, order and palette advice all follow this choice.
                </p>
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
                <div className="flex flex-wrap gap-2 mt-4">
                  {SKILL_LEVELS.map(s => (
                    <button key={s.id} onClick={() => setSkillLevel(s.id)} className="chip" data-active={skillLevel === s.id}>
                      {s.label}
                    </button>
                  ))}
                </div>
                <p className="text-xs mt-2.5" style={{ color: "var(--text-dim)" }}>
                  {SKILL_LEVELS.find(s => s.id === skillLevel)?.tip}
                </p>

                {/* Your paint set — mix recipes from a real brand's tubes.
                    Only shown for mediums that ship real-paint sets. */}
                {brands.length > 0 && (
                  <div className="mt-5">
                    <label className="label-xs block mb-2">Your paint set (optional)</label>
                    <div className="flex flex-wrap gap-2">
                      <button onClick={() => setBrandId("")} className="chip" data-active={brandId === ""}>
                        Generic palette
                      </button>
                      {brands.map(b => (
                        <button key={b.id} onClick={() => setBrandId(b.id)} className="chip" data-active={brandId === b.id}>
                          {b.name}
                        </button>
                      ))}
                    </div>
                    <p className="text-xs mt-2.5" style={{ color: "var(--text-dim)" }}>
                      {brandId
                        ? "Mixing recipes are built from this set's real tubes."
                        : "Recipes use a generic 12-tube starter palette. Pick your brand to mix from tubes you own."}
                    </p>
                  </div>
                )}
              </div>

              {/* 3 · Values */}
              <div>
                <p className="font-display text-xl mb-1" style={{ color: "var(--ink)" }}>
                  <span style={{ color: "var(--accent)" }}>3.</span> Value simplification
                </p>
                <p className="text-xs mb-4" style={{ color: "var(--text-dim)" }}>
                  How finely light is divided — the backbone of the painting.
                </p>
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

              {/* 4 · Starting view */}
              <div>
                <p className="font-display text-xl mb-1" style={{ color: "var(--ink)" }}>
                  <span style={{ color: "var(--accent)" }}>4.</span> Starting view
                </p>
                <p className="text-xs mb-4" style={{ color: "var(--text-dim)" }}>
                  All five view levels are always generated — you only choose
                  where the lesson opens. The reference itself is never simplified.
                </p>
                <div className="flex flex-wrap gap-2">
                  {DETAIL_LEVELS.map(d => (
                    <button key={d.level} onClick={() => setInitialViewLevel(d.level)} className="chip" data-active={initialViewLevel === d.level}>
                      {d.label}
                    </button>
                  ))}
                </div>
                {selectedDetail && (
                  <p className="text-xs mt-2.5" style={{ color: "var(--text-dim)" }}>
                    {selectedDetail.description} <span style={{ opacity: 0.75 }}>({selectedDetail.regions_hint})</span>
                  </p>
                )}
              </div>

              {/* Advanced — implementation-level knobs, collapsed by default.
                  Kept functional for debugging/power use; a normal lesson
                  never needs them (brief §4). */}
              <div className="rounded-2xl" style={{ border: "1px dashed var(--border-strong)" }}>
                <button onClick={() => setAdvancedOpen(o => !o)}
                        className="w-full flex items-center justify-between px-5 py-4"
                        style={{ background: "none", border: "none", cursor: "pointer" }}>
                  <span className="text-sm font-medium" style={{ color: "var(--text-dim)" }}>
                    Advanced (technical) settings
                  </span>
                  <span style={{ color: "var(--accent)" }}>{advancedOpen ? "−" : "+"}</span>
                </button>
                {advancedOpen && (
                  <div className="px-5 pb-5 space-y-6">
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
                      <p className="text-xs mt-1" style={{ color: "var(--text-dim)", opacity: 0.8 }}>
                        Defaults to your medium&rsquo;s recommendation.
                      </p>
                    </div>
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
                    </div>
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
                              background: checked ? "var(--accent)" : "var(--border)",
                              border: "1px solid " + (checked ? "var(--accent)" : "var(--border-strong)"),
                              cursor: "pointer",
                            }}>
                            <span className="absolute top-0.5 left-0.5 w-5 h-5 rounded-full transition-transform"
                                  style={{ background: "var(--paper)", transform: checked ? "translateX(16px)" : "translateX(0)" }} />
                          </button>
                          <span className="text-sm" style={{ color: checked ? "var(--ink)" : "var(--text-dim)" }}>
                            {label}
                          </span>
                          <span className="hidden sm:inline text-xs" style={{ color: "var(--text-dim)", opacity: 0.8 }}>{tip}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Error */}
              {error && (
                <p className="text-sm px-4 py-3 rounded-xl" style={{ background: "rgba(157,47,47,0.08)", color: "var(--crimson)", border: "1px solid rgba(157,47,47,0.3)" }}>
                  {error}
                </p>
              )}

              {/* Submit + honest summary of what was chosen */}
              <div>
                <p className="text-xs mb-3 text-center" style={{ color: "var(--text-dim)" }}>
                  {selectedMedium?.label} · {SKILL_LEVELS.find(s => s.id === skillLevel)?.label} ·{" "}
                  {valueZones} value zones · opens at {selectedDetail?.label}
                </p>
                <button onClick={submit} disabled={!file || loading} className="btn-primary w-full" style={{ padding: "17px 28px" }}>
                  {loading ? "Uploading…" : "Generate my lesson →"}
                </button>
              </div>
            </div>
          </section>

          {/* ── Footer ─────────────────────────────────────────────────── */}
          <footer className="px-6 py-10 text-center" style={{ borderTop: "1px solid var(--border)" }}>
            <p className="font-display text-sm mb-1" style={{ color: "var(--text-dim)" }}>
              Painting <em style={{ color: "var(--accent)" }}>Instructor</em>
            </p>
            <p className="text-xs" style={{ color: "var(--text-dim)", opacity: 0.7 }}>
              Line art · Value study · Colour temperature · Paint by numbers · Progressive video lessons
            </p>
            <p className="text-xs mt-2" style={{ color: "var(--text-dim)", opacity: 0.55 }}>
              Marble bust 3D scan — Poly Haven, CC0
            </p>
          </footer>
        </main>
      </div>
    </SmoothScroll>
  );
}
