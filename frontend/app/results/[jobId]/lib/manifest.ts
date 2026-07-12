// ── Shared constants, label maps, types and URL helpers for the results view ──
//
// All catalogues (page labels, classic page keys, step labels/stages, level
// labels) come from the GENERATED contract — backend/capabilities.py is the
// single source of truth. Never define a catalogue by hand here again.

import {
  PAGE_LABELS, CLASSIC_PAGE_KEYS, STEP_LABELS, STEP_STAGE, LEVEL_LABELS,
} from "../../../lib/contract.generated";

export { PAGE_LABELS, CLASSIC_PAGE_KEYS, STEP_LABELS, STEP_STAGE, LEVEL_LABELS };

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const LAYER_KEYS = ["outlines", "regions", "values", "colours"] as const;
export type LayerKey = typeof LAYER_KEYS[number];

export const LAYER_LABELS: Record<string, string> = {
  outlines: "Outlines",
  values:   "Values",
  colours:  "Colours",
  regions:  "Regions",
};

// A4: Individual outline sublayer labels
export const OUTLINE_SUBLAYER_LABELS: Record<string, string> = {
  primary:    "Primary",
  secondary:  "Secondary",
  decorative: "Decorative",
  texture:    "Texture",
};

export type CompareMode = "analysis" | "reference" | "side_by_side" | "overlay";

// ── Types ─────────────────────────────────────────────────────────────────────
export type JobStatus = {
  status: "queued" | "processing" | "completed" | "completed_with_warnings" | "failed";
  progress: number;
  step: string;
  message: string;
  analysis_ready?: boolean;  // A3: true when preliminary manifest is available
  result?: {
    manifest: string;
    pages: string[];
    video?: string;
    pdf?:   string;
  };
  error?: string;
};

// Per-step ordered micro-steps — a granular painting checklist for one lesson
// step. Optional on each lesson_plan entry.
export type MicroStep = {
  order: number;
  region_id: number;
  location: string;
  value_label: string;
  colour_name: string;
  area_frac: number;
  action: string;
  mix_hint: string | null;
};

export type Manifest = {
  job_id: string;
  input: {
    medium: string;
    palette_size: number;
    initial_view_level: number;
    value_zones: number;
    region_complexity?: number;
    background_detail?: boolean;
    texture_detail?: boolean;
    skill_level?: string;
  };
  image: { width: number; height: number };
  reference?: string;
  pages: string[];
  detail_levels: Record<string, {
    level: number; label: string;
    outlines: string; regions: string; values: string; colours: string;
    edge_maps?: Record<string, string>;  // level-aware sublayers — NOT the same as the top-level edge_maps below
  }>;
  edge_maps?: Record<string, string>;  // global, non-level-filtered — "primary"|"secondary"|"decorative"|"texture" → rel path
  label_maps?: Record<string, string>; // per-level RGB-encoded region-id maps (viewer click-select)
  regions_json?: string;               // region hierarchy metadata for this job
  outline_composites?: Record<string, string>;  // global (non-level-filtered) outline composites
  palette: {
    id: number; name: string; base_rgb: [number,number,number]; area_fraction: number;
    mixing?: { text: string; delta_e: number; mixed_rgb: [number,number,number] };
  }[];
  colour_families: unknown[];
  value_zones: { id: number; label: string; grey_value: number }[];
  teaching_stages?: {
    order: number;
    name: string;
    description: string;
    analysis_layers: string[];
  }[];
  teaching_instructions?: Record<string, string>;
  lesson_plan?: {
    order: number;
    name: string;
    description: string;
    why?: string;
    medium: string;
    level: number;
    assets: Record<string, string>;
    image_notes?: string[];
    image_micro_steps?: MicroStep[];
    emphasis?: boolean;        // adaptive-profile lever: this stage targets your habit
    profile_notes?: string[];  // adaptive-profile lever: watch-outs from your critiques
    lesson_goal?: string;      // adaptive-profile lever: the session goal (first step)
  }[];
  image_brief?: {
    overview?: string;
    light?: { angle: number | null; from: string | null };
    masses?: { location: string; colour_name: string; value_label: string; area_frac: number }[];
    focal?: { location: string } | null;
    busy_areas?: { location: string; region_count: number }[];
    warmest_colour?: string | null;
    coolest_colour?: string | null;
  };
  video?: string;
  video_chapters?: { order: number; name: string; start_sec: number }[];
  pdf?: string;
  personal_observations?: string | null;
  status?: string;  // A3: "analysis_ready" when progressive delivery is active
};

export type AnalysisPage = {
  key: string;
  url: string;
  title: string;
  why: string;
  tip: string;
};

// ── Helpers ───────────────────────────────────────────────────────────────────
export function absUrl(relPath: string | undefined | null): string {
  if (!relPath) return "";
  if (relPath.startsWith("http")) return relPath;
  return `${API}/${relPath.replace(/^\//, "")}`;
}

/** Convert an outputs-relative path (e.g. "abc/level_1.png") to a full URL. */
export function outputUrl(relPath: string | undefined | null): string {
  if (!relPath) return "";
  if (relPath.startsWith("http")) return relPath;
  return `${API}/outputs/${relPath.replace(/^\//, "")}`;
}
