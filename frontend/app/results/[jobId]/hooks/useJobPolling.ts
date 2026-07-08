"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  API, absUrl, outputUrl, PAGE_LABELS, CLASSIC_PAGE_KEYS,
  type JobStatus, type Manifest, type AnalysisPage,
} from "../lib/manifest";

export type JobPolling = {
  jobStatus: JobStatus;
  manifest: Manifest | null;
  classicPages: AnalysisPage[];
  selected: AnalysisPage | null;
  setSelected: React.Dispatch<React.SetStateAction<AnalysisPage | null>>;
  detailLevel: number;
  setDetailLevel: React.Dispatch<React.SetStateAction<number>>;
  viewMode: ViewMode;
  setViewMode: React.Dispatch<React.SetStateAction<ViewMode>>;
};

export type ViewMode = "lesson" | "classic_analysis" | "hierarchical_lesson" | "critique" | "squint";

// Polls the job status endpoint, fetches the manifest when ready, and derives
// the classic-analysis page list. Also owns the shared selection/view state
// that both the poll callback and the page need to mutate.
export function useJobPolling(jobId: string): JobPolling {
  const [jobStatus,    setJobStatus]    = useState<JobStatus>({ status: "queued", progress: 0, step: "", message: "Waiting to start" });
  const [manifest,     setManifest]     = useState<Manifest | null>(null);
  const [classicPages, setClassicPages] = useState<AnalysisPage[]>([]);
  const [selected,     setSelected]     = useState<AnalysisPage | null>(null);

  // View mode — "lesson" is the guided step-by-step teacher (default);
  // "hierarchical_lesson" is the free layer explorer; "classic_analysis"
  // shows the seven classic study pages; "critique" compares an uploaded
  // attempt against the reference.
  const [viewMode, setViewMode] = useState<ViewMode>("lesson");

  const [detailLevel, setDetailLevel] = useState(3);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
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

  return {
    jobStatus, manifest, classicPages,
    selected, setSelected,
    detailLevel, setDetailLevel,
    viewMode, setViewMode,
  };
}
