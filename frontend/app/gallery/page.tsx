import type { Metadata } from "next";
import Link from "next/link";
import { CAPABILITIES } from "../lib/contract.generated";

export const metadata: Metadata = {
  title: "Gallery — Painting Instructor",
  description:
    "Every study the atelier generates from a single photo — line art, value studies, colour palettes and more, before you upload your own.",
};

// The gallery shows EXACTLY the advertised capabilities with real sample
// assets — the same shared contract the landing page and workspace read.
const STUDIES = CAPABILITIES.filter(c => c.advertised && c.sample);

export default function GalleryPage() {
  return (
    <main className="min-h-screen w-full px-5 sm:px-8 py-16 sm:py-24">
      <div className="mx-auto max-w-6xl">
        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <header className="fade-up max-w-3xl">
          <p className="eyebrow">The gallery</p>
          <h1 className="font-display mt-4 text-4xl sm:text-6xl leading-[1.05] tracking-tight text-[color:var(--ink)]">
            One photo,{" "}
            <span className="text-gradient">{STUDIES.length} studies</span>.
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
                key={s.id}
                className="panel overflow-hidden flex flex-col transition-transform duration-300 hover:-translate-y-1"
              >
                <div className="overflow-hidden bg-[color:var(--surface-2)]">
                  <img
                    src={`/samples/demo1/${s.sample}`}
                    alt={`${s.name} study generated from the reference photo.`}
                    loading="lazy"
                    className="block w-full max-w-full h-auto aspect-[4/3] object-cover"
                  />
                </div>
                <div className="px-5 py-5 flex flex-col gap-2">
                  <h2 className="font-display text-xl leading-tight text-[color:var(--ink)]">
                    {s.name}
                  </h2>
                  <p className="text-sm leading-relaxed text-[color:var(--text-dim)]">
                    {s.description}
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
