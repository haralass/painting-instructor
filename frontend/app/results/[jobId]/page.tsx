"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";

const API = "http://localhost:8000";

const STEP_LABELS: Record<string, string> = {
  loading:          "Loading image…",
  line_art:         "Drawing outlines…",
  notan:            "Mapping values (Notan)…",
  color_temperature:"Analysing warm/cool…",
  color_palette:    "Extracting colour palette…",
  light_direction:  "Finding light source…",
  color_by_number:  "Building paint-by-numbers…",
  dot_to_dot:       "Placing dots…",
  video:            "Rendering tutorial video…",
  pdf:              "Assembling PDF book…",
};

const PAGE_LABELS: Record<string, { title: string; why: string }> = {
  line_art: {
    title: "Line Art",
    why: "Every painting starts with clear structure. These lines define the silhouette (thickest, most important), interior forms (medium weight), and background texture (lightest). Silhouette edges tell the viewer what object they're looking at before they read any detail.",
  },
  notan: {
    title: "Value Study (Notan)",
    why: "Notan is a Japanese design concept — before you touch colour, you must get your lights and darks right. A painting with correct values reads in black and white. Squint at your reference: if the shapes still read, your values are working.",
  },
  color_temperature: {
    title: "Warm / Cool Map",
    why: "Light and shadow have opposite temperatures. In natural light, lit areas are warm (orange/yellow), shadows are cool (blue/purple). This is James Gurney's core principle from Colour & Light. Violating this makes paintings look flat or artificial.",
  },
  color_palette: {
    title: "Colour Palette",
    why: "These are the dominant colours of your reference, sorted by area coverage. A limited palette (12–16 colours max) forces harmony. Mix from these rather than adding new tubes — every extra colour risks mud.",
  },
  light_direction: {
    title: "Light & Shadow Zones",
    why: "Gurney's 5 zones of light: Highlight → Halftone → Core Shadow → Reflected Light → Cast Shadow. The core shadow is your darkest paint. Reflected light (lighter than core shadow but darker than halftone) is the hardest for beginners — they always paint it too light.",
  },
  color_by_number: {
    title: "Paint by Numbers",
    why: "Flat colour blocking is how every master painter starts a canvas. Fill the entire canvas before adding detail — if any white shows through, you cannot judge colour relationships. The numbered zones give you a map for your blocking-in session.",
  },
  dot_to_dot: {
    title: "Structural Dots",
    why: "These dots trace the most structurally significant edges — the ones that define form, not texture. Connecting them in order builds your under-drawing. A strong under-drawing means your colour layers can be loose and expressive without losing structure.",
  },
};

type JobStatus = {
  status: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE";
  step?: string;
  result?: {
    pages: string[];
    video: string;
    pdf: string;
  };
  error?: string;
};

type AnalysisPage = {
  key: string;
  url: string;
  title: string;
  why: string;
};

export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [status, setStatus] = useState<JobStatus>({ status: "PENDING" });
  const [pages, setPages]   = useState<AnalysisPage[]>([]);
  const [selected, setSelected] = useState<AnalysisPage | null>(null);
  const [whyOpen, setWhyOpen]   = useState(false);

  const poll = useCallback(async () => {
    try {
      const res = await fetch(`${API}/jobs/${jobId}`);
      const data: JobStatus = await res.json();
      setStatus(data);

      if (data.status === "SUCCESS" && data.result) {
        const ps: AnalysisPage[] = data.result.pages.map((p) => {
          const key = p.split("/").pop()?.replace(".png", "") ?? "";
          const meta = PAGE_LABELS[key] ?? { title: key, why: "" };
          return { key, url: `${API}/outputs/${jobId}/${key}.png`, ...meta };
        });
        setPages(ps);
        if (ps.length > 0) setSelected(ps[0]);
      }
    } catch {
      // backend unreachable, keep polling
    }
  }, [jobId]);

  useEffect(() => {
    poll();
    const id = setInterval(() => {
      if (status.status !== "SUCCESS" && status.status !== "FAILURE") poll();
    }, 2500);
    return () => clearInterval(id);
  }, [poll, status.status]);

  const isRunning = status.status === "PENDING" || status.status === "STARTED";
  const isDone    = status.status === "SUCCESS";
  const isFailed  = status.status === "FAILURE";

  // ── Loading / Error states ────────────────────────────────────────────────
  if (!isDone) {
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
              <p className="text-base mb-6" style={{ color: "var(--text-dim)" }}>
                {STEP_LABELS[status.step ?? ""] ?? "Processing…"}
              </p>
              <div className="h-1 w-full rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{ background: "var(--accent)", width: status.step ? "60%" : "15%" }}
                />
              </div>
            </>
          )}
          {isFailed && (
            <>
              <div className="text-5xl mb-6">❌</div>
              <h2 className="text-2xl font-bold mb-2">Processing failed</h2>
              <p style={{ color: "var(--text-dim)" }}>{status.error ?? "Unknown error"}</p>
            </>
          )}
        </div>
      </main>
    );
  }

  const videoUrl = `${API}/outputs/${jobId}/tutorial.mp4`;
  const pdfUrl   = `${API}/outputs/${jobId}/tutorial_book.pdf`;

  // ── Results layout ────────────────────────────────────────────────────────
  return (
    <main className="min-h-screen flex flex-col" style={{ background: "var(--bg)" }}>

      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-4 border-b"
              style={{ borderColor: "var(--border)" }}>
        <a href="/" className="font-bold text-lg" style={{ color: "var(--accent)" }}>
          ← New Tutorial
        </a>
        <div className="flex gap-3">
          <a href={pdfUrl} target="_blank" rel="noreferrer"
             className="px-4 py-2 rounded-lg border text-sm font-medium transition-colors hover:border-yellow-600 hover:text-yellow-400"
             style={{ borderColor: "var(--border)", color: "var(--text-dim)" }}>
            Download PDF
          </a>
          <a href={videoUrl} download
             className="px-4 py-2 rounded-lg text-sm font-semibold"
             style={{ background: "var(--accent)", color: "#0f0e0d" }}>
            Download Video
          </a>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">

        {/* Left — thumbnail strip */}
        <nav className="w-48 flex-shrink-0 overflow-y-auto border-r p-3 space-y-2 hidden md:block"
             style={{ borderColor: "var(--border)" }}>
          {pages.map(p => (
            <button key={p.key}
                    onClick={() => { setSelected(p); setWhyOpen(false); }}
                    className="w-full text-left rounded-lg overflow-hidden border transition-colors"
                    style={{
                      borderColor: selected?.key === p.key ? "var(--accent)" : "transparent",
                    }}>
              <img src={p.url} alt={p.title} className="w-full object-cover" style={{ aspectRatio: "4/3" }} />
              <p className="text-xs px-2 py-1 truncate" style={{ color: "var(--text-dim)" }}>{p.title}</p>
            </button>
          ))}
        </nav>

        {/* Centre — video + selected analysis */}
        <section className="flex-1 flex flex-col overflow-y-auto">

          {/* Video */}
          <div className="p-4">
            <h2 className="text-sm font-semibold mb-2 uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
              Tutorial Video
            </h2>
            <video
              src={videoUrl}
              controls
              className="w-full rounded-xl"
              style={{ background: "#000", maxHeight: 480 }}
            />
          </div>

          {/* Selected analysis image */}
          {selected && (
            <div className="p-4 border-t" style={{ borderColor: "var(--border)" }}>
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold text-lg">{selected.title}</h2>
                <button
                  onClick={() => setWhyOpen(!whyOpen)}
                  className="px-3 py-1 rounded-lg border text-sm transition-colors"
                  style={{
                    borderColor: whyOpen ? "var(--accent)" : "var(--border)",
                    color:       whyOpen ? "var(--accent)" : "var(--text-dim)",
                  }}
                >
                  WHY? →
                </button>
              </div>
              <img src={selected.url} alt={selected.title} className="w-full rounded-xl object-contain max-h-96" />

              {/* Mobile thumbnail strip */}
              <div className="flex gap-2 mt-4 overflow-x-auto pb-2 md:hidden">
                {pages.map(p => (
                  <button key={p.key}
                          onClick={() => { setSelected(p); setWhyOpen(false); }}
                          className="flex-shrink-0 rounded overflow-hidden border"
                          style={{ borderColor: selected.key === p.key ? "var(--accent)" : "var(--border)" }}>
                    <img src={p.url} alt={p.title} className="h-16 w-20 object-cover" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* Right — WHY sidebar */}
        {whyOpen && selected && (
          <aside className="w-80 flex-shrink-0 border-l p-5 overflow-y-auto"
                 style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-base" style={{ color: "var(--accent)" }}>
                Why this step matters
              </h3>
              <button onClick={() => setWhyOpen(false)} style={{ color: "var(--text-dim)" }}>✕</button>
            </div>
            <h4 className="font-semibold mb-3">{selected.title}</h4>
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-dim)" }}>
              {selected.why || "Art principle explanation coming soon."}
            </p>

            <div className="mt-6 p-4 rounded-lg" style={{ background: "var(--bg)" }}>
              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--accent)" }}>
                Action for this step
              </p>
              <ActionTip pageKey={selected.key} />
            </div>
          </aside>
        )}
      </div>
    </main>
  );
}

function ActionTip({ pageKey }: { pageKey: string }) {
  const tips: Record<string, string> = {
    line_art:         "Transfer these outlines to your canvas with light charcoal or a 2H pencil. Don't press hard — you'll erase them as you paint.",
    notan:            "Mix only 3 values: darkest dark, mid grey, and white. Fill the entire canvas with these before adding colour.",
    color_temperature:"Premix a warm and a cool version of every colour. Always lean the lights warm and the shadows cool.",
    color_palette:    "Lay out this palette on your palette board before you start. Only these colours — no extras.",
    light_direction:  "Position your actual light source to match this angle, or mentally commit to it and never change it.",
    color_by_number:  "Block in flat colour before blending. Use a large flat brush and cover every numbered zone completely first.",
    dot_to_dot:       "Connect these dots lightly with your pencil before painting. This is your structural under-drawing.",
  };
  return (
    <p className="text-xs leading-relaxed" style={{ color: "var(--text-dim)" }}>
      {tips[pageKey] ?? "Follow the steps shown in the video for this analysis layer."}
    </p>
  );
}
