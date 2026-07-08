import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Gallery — Painting Instructor",
  description:
    "Every study the atelier generates from a single photo — line art, value studies, colour palettes and more, before you upload your own.",
};

// ── The studies produced from one reference photo ──────────────────────────────
// Each maps to a committed sample under /public/samples/demo1/. One-liners
// adapted from the results-page PAGE_LABELS.
type Study = { file: string; title: string; teaches: string };

const STUDIES: Study[] = [
  {
    file: "line_art",
    title: "Line Art",
    teaches: "Weighted contours that lock in the silhouette before a drop of paint.",
  },
  {
    file: "notan",
    title: "Value Study (Notan)",
    teaches: "Lights and darks resolved first — get these right and the painting reads.",
  },
  {
    file: "color_palette",
    title: "Colour Palette",
    teaches: "Your reference distilled to a limited, harmonious set of mixing colours.",
  },
  {
    file: "color_by_number",
    title: "Paint by Numbers",
    teaches: "Flat colour blocks to fill the whole canvas before you blend.",
  },
  {
    file: "light_direction",
    title: "Light & Shadow",
    teaches: "Gurney's five zones map where light lands and shadow gathers.",
  },
  {
    file: "subject_focus",
    title: "Focal Subject",
    teaches: "The subject lifted from its background — your sharpest, most saturated note.",
  },
  {
    file: "depth_planes",
    title: "Depth Planes",
    teaches: "Foreground, middle and background split so distance reads cooler and softer.",
  },
  {
    file: "local_vs_light",
    title: "Local Colour vs Light",
    teaches: "An object's true colour separated from the light falling on it.",
  },
  {
    file: "value_traps",
    title: "Value Traps",
    teaches: "Where the eye is fooled into painting the wrong value — flagged in advance.",
  },
  {
    file: "edge_coach",
    title: "Edge Control",
    teaches: "Hard and soft edges mapped so the eye lands where you want it.",
  },
  {
    file: "composition",
    title: "Composition & Focus",
    teaches: "Where attention is pulled — and any rival that competes for it.",
  },
];

export default function GalleryPage() {
  return (
    <main className="min-h-screen w-full px-5 sm:px-8 py-16 sm:py-24">
      <div className="mx-auto max-w-6xl">
        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <header className="fade-up max-w-3xl">
          <p className="eyebrow">The gallery</p>
          <h1 className="font-display mt-4 text-4xl sm:text-6xl leading-[1.05] tracking-tight text-[color:var(--ink)]">
            One photo,{" "}
            <span className="text-gradient">a dozen studies</span>.
          </h1>
          <p className="mt-6 text-lg sm:text-xl leading-relaxed text-[color:var(--text-dim)]">
            Every study the atelier generates from a single photo — before you
            upload your own.
          </p>
        </header>

        {/* ── Reference — shown prominently ────────────────────────────── */}
        <section className="mt-14 sm:mt-20">
          <div className="flex items-center gap-3">
            <p className="label-xs">The reference</p>
            <span className="h-px flex-1 bg-[color:var(--border)]" />
          </div>
          <figure className="panel mt-5 overflow-hidden">
            <img
              src="/samples/demo1/reference.jpg"
              alt="The reference photograph every study below is generated from."
              loading="lazy"
              className="block w-full max-w-full h-auto object-cover"
            />
            <figcaption className="px-5 sm:px-7 py-4 text-sm text-[color:var(--text-dim)] border-t border-[color:var(--border)]">
              This is the single photo. Everything that follows is derived from
              it — no other input.
            </figcaption>
          </figure>
        </section>

        {/* ── The studies grid ─────────────────────────────────────────── */}
        <section className="mt-16 sm:mt-24">
          <div className="flex items-center gap-3">
            <p className="label-xs">The studies</p>
            <span className="h-px flex-1 bg-[color:var(--border)]" />
          </div>

          <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {STUDIES.map((s) => (
              <article
                key={s.file}
                className="panel overflow-hidden flex flex-col transition-transform duration-300 hover:-translate-y-1"
              >
                <div className="overflow-hidden bg-[color:var(--surface-2)]">
                  <img
                    src={`/samples/demo1/${s.file}.jpg`}
                    alt={`${s.title} study generated from the reference photo.`}
                    loading="lazy"
                    className="block w-full max-w-full h-auto aspect-[4/3] object-cover"
                  />
                </div>
                <div className="px-5 py-5 flex flex-col gap-2">
                  <h2 className="font-display text-xl leading-tight text-[color:var(--ink)]">
                    {s.title}
                  </h2>
                  <p className="text-sm leading-relaxed text-[color:var(--text-dim)]">
                    {s.teaches}
                  </p>
                </div>
              </article>
            ))}
          </div>
        </section>

        {/* ── CTA ──────────────────────────────────────────────────────── */}
        <section className="mt-20 sm:mt-28">
          <div className="panel px-7 sm:px-12 py-12 sm:py-16 text-center">
            <p className="eyebrow">Your turn</p>
            <h2 className="font-display mt-4 text-3xl sm:text-4xl leading-tight text-[color:var(--ink)]">
              Now do it with{" "}
              <span className="text-gradient">your own photo</span>.
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-base sm:text-lg text-[color:var(--text-dim)]">
              Upload a single image and the atelier builds the same complete set
              of studies around it.
            </p>
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link href="/#create" className="btn-primary">
                Upload your own photo →
              </Link>
              <Link href="/" className="btn-ghost">
                Back to home
              </Link>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
