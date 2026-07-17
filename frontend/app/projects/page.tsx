"use client";
// Projects dashboard (Phase 7 — save & continue).
//
// Lists every saved painting project from the backend store with its
// reference thumbnail, medium, how far the lesson has got, and the current
// prioritized correction, each linking back into the workspace to resume
// exactly where it was left. Reads the same project store the workspace
// writes to — no separate state.
import { useEffect, useState } from "react";
import Link from "next/link";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Project = {
  id: string; job_id: string | null; title: string; medium: string;
  reference_path: string; updated_at: string;
  completed_steps?: number; latest_priority?: string | null;
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(`${API}/projects?limit=60`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then((data: Project[]) => setProjects(Array.isArray(data) ? data.filter(p => p.job_id) : []))
      .catch(() => setFailed(true));
  }, []);

  return (
    <main className="min-h-screen w-full px-5 sm:px-8 py-16 sm:py-24">
      <div className="mx-auto max-w-6xl">
        <header className="fade-up max-w-3xl">
          <p className="eyebrow">Your studio</p>
          <h1 className="font-display mt-4 text-4xl sm:text-6xl leading-[1.05] tracking-tight text-[color:var(--ink)]">
            Continue a <span className="text-gradient">painting</span>.
          </h1>
          <p className="mt-6 text-lg sm:text-xl leading-relaxed text-[color:var(--text-dim)]">
            Every project you start is saved — its lesson progress, checkpoints,
            deeper looks and the last correction — so you can pick up exactly
            where you left off.
          </p>
        </header>

        <section className="mt-14 sm:mt-20">
          {failed && (
            <p className="text-sm text-[color:var(--text-dim)]">
              Couldn&rsquo;t reach the studio backend. Is it running?
            </p>
          )}
          {projects && projects.length === 0 && !failed && (
            <div className="panel px-7 py-12 text-center">
              <p className="text-[color:var(--text-dim)]">
                No saved projects yet.{" "}
                <Link href="/#create" className="text-[color:var(--accent)]">Upload a photo</Link>{" "}
                to start your first.
              </p>
            </div>
          )}
          {!projects && !failed && (
            <p className="text-sm text-[color:var(--text-dim)]">Loading your projects…</p>
          )}

          {projects && projects.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {projects.map(p => (
                <Link key={p.id} href={`/results/${p.job_id}`}
                      className="panel overflow-hidden flex flex-col transition-transform duration-300 hover:-translate-y-1"
                      style={{ textDecoration: "none" }}>
                  <div className="overflow-hidden bg-[color:var(--surface-2)]">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={`${API}/outputs/${p.reference_path}`} alt=""
                         loading="lazy"
                         className="block w-full h-auto aspect-[4/3] object-cover"
                         onError={e => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }} />
                  </div>
                  <div className="px-5 py-4 flex flex-col gap-2 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <h2 className="font-display text-lg leading-tight text-[color:var(--ink)] truncate">
                        {p.title}
                      </h2>
                      <span className="text-[11px] px-2 py-0.5 rounded-full flex-shrink-0"
                            style={{ background: "var(--surface)", color: "var(--text-dim)" }}>
                        {p.medium}
                      </span>
                    </div>
                    {typeof p.completed_steps === "number" && p.completed_steps > 0 ? (
                      <p className="text-xs text-[color:var(--text-dim)]">
                        {p.completed_steps} lesson step{p.completed_steps === 1 ? "" : "s"} done
                      </p>
                    ) : (
                      <p className="text-xs text-[color:var(--text-dim)]">Not started yet</p>
                    )}
                    {p.latest_priority && (
                      <p className="text-xs leading-relaxed mt-auto p-2 rounded"
                         style={{ background: "rgba(180,81,31,0.08)", color: "var(--text)" }}>
                        <span style={{ color: "var(--accent)", fontWeight: 600 }}>Fix next: </span>
                        {p.latest_priority}
                      </p>
                    )}
                    <p className="text-[11px] text-[color:var(--text-dim)]"
                       style={{ opacity: 0.7 }}>
                      Updated {new Date(p.updated_at).toLocaleDateString()} · Resume →
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>

        <div className="mt-16">
          <Link href="/" className="btn-ghost">← Home</Link>
        </div>
      </div>
    </main>
  );
}
