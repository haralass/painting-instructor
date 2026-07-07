import Link from "next/link";
import EvolvingCanvas, { STAGE_VISUAL_COUNT } from "../../../components/EvolvingCanvas";
import { STEP_STAGE, STEP_LABELS, type JobStatus } from "../lib/manifest";

// ── Loading / Error states ─────────────────────────────────────────────────
// A3: shown until analysis_ready manifest arrives (or completion).
export default function LoadingScreen({ jobStatus }: { jobStatus: JobStatus }) {
  const isRunning = jobStatus.status === "queued" || jobStatus.status === "processing";
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4"
          style={{ background: "var(--bg)" }}>
      <div className="text-center max-w-md fade-up">
        {isRunning && (
          <>
            {/* Your canvas, laid in stage by stage as the pipeline advances */}
            <div className="mx-auto mb-8 rounded-sm overflow-hidden"
                 style={{
                   aspectRatio: "4/3", maxWidth: 360,
                   border: "10px solid var(--paper)",
                   outline: "1px solid var(--border-strong)",
                   boxShadow: "0 30px 70px rgba(63,48,28,0.18)",
                   transform: "rotate(-0.6deg)",
                 }}>
              <EvolvingCanvas
                stage={Math.min(STEP_STAGE[jobStatus.step] ?? 0, STAGE_VISUAL_COUNT - 1)}
                seed={7}
              />
            </div>
            <p className="eyebrow mb-3">Painting your reference</p>
            <h2 className="font-display text-3xl mb-4" style={{ color: "var(--ink)" }}>
              Laying in your <em className="text-gradient">lesson</em>
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
