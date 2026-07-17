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

export type CompareMode = "analysis" | "reference" | "side_by_side" | "overlay" | "split";

// ── Phase 4: structured lesson (mirrors backend/schemas/lesson.py) ──
export type LessonOverlay = { kind: string; asset?: string | null; region_ids: number[]; opacity?: number };
export type LessonCompletion = { kind: "confirm" | "upload" | "trace"; criteria: string };
export type LessonStepV2 = {
  id: string; capability_id: string; phase: string; order: number;
  title: string; objective: string; explanation: string; action: string;
  overlays: LessonOverlay[]; tool?: string | null; mixture?: string | null;
  completion_check?: LessonCompletion | null; common_mistake?: string | null;
  stop_condition?: string | null; checkpoint_id?: string | null; depends_on: string[];
};
export type LessonCheckpoint = {
  id: string; type: string; title: string; instructions: string;
  required: boolean; accepts: string[];
};
export type LessonV2 = {
  id: string; capability_id: string; medium: string; guidance: string;
  steps: LessonStepV2[]; checkpoints: LessonCheckpoint[];
};

// ── Phase 3: structured drawing construction (mirrors backend/schemas/drawing.py) ──
export type Pt = [number, number];
export type EdgeCause = {
  scores: Record<string, number>;
  primary: string | null;
  confidence: number;
};
export type DrawLandmark = {
  id: string; category: string; x: number; y: number; normalized: Pt;
  importance: number; confidence: number; visibility_level: number; lesson_order: number;
};
export type DrawAxis = {
  id: string; start: Pt; end: Pt; orientation_deg: number; role: string; importance: number;
};
export type DrawPath = {
  id: string; category: string; points: Pt[]; closed: boolean;
  hierarchy_level: number; importance: number; edge_cause?: EdgeCause | null;
  stage: string; lesson_order: number;
};
export type DrawNegativeSpace = {
  id: string; polygon: Pt[]; touches_edges: string[]; area_fraction: number; importance: number;
};
export type DrawEnvelope = { id: string; vertices: Pt[]; segment_count: number; landmark_ids: string[] };
export type DrawProportion = { id: string; kind: string; label: string; value?: number | null; reference_points: Pt[]; landmark_ids: string[] };
export type DrawStage = {
  id: string; order: number; title: string; summary: string;
  landmark_ids: string[]; axis_ids: string[]; path_ids: string[];
  negative_space_ids: string[]; proportion_check_ids: string[]; is_checkpoint: boolean;
};
export type DrawingAnalysis = {
  id: string; image_width: number; image_height: number; canvas_ratio: number;
  subject_bounds: {
    x_min: number; y_min: number; x_max: number; y_max: number;
    margins: Record<string, number>; occupied_fraction: number; source: string; confidence: number;
  };
  occupied_area: Pt[];
  main_axis?: DrawAxis | null;
  dominant_slopes: DrawAxis[];
  landmarks: DrawLandmark[];
  negative_spaces: DrawNegativeSpace[];
  proportion_checks: DrawProportion[];
  envelope?: DrawEnvelope | null;
  silhouette?: DrawPath | null;
  internal_paths: DrawPath[];
  construction_order: DrawStage[];
};

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
  drawing_json?: string;               // Phase 3 structured drawing construction
  lesson?: LessonV2 | null;            // Phase 4 structured composition-first lesson
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

// ── Phase 2 leftover: rectangle region selection + "Analyse this area" ──
// Mirrors backend/analysis/local.py's return dict. Selection geometry is
// ORIGINAL image px (frontend/app/lib/imageCoords.ts convention); `offset`
// + `scale` map any point in the local result back onto the parent image:
//   parent_px = offset + local_px / scale
export type LocalAnalysisBBox = { x: number; y: number; w: number; h: number };
export type LocalAnalysisAssets = {
  outlines: string | null;
  regions: string | null;
  values: string | null;
  colours: string | null;
  label_map: string | null;
  regions_json: string | null;
  drawing_json: string | null;
  detail_level: number | null;
};
export type LocalDrawingSummary = {
  subject_source: string | null;
  occupied_fraction: number | null;
  n_landmarks: number;
  envelope_segments: number | null;
  n_internal_paths: number;
  silhouette_cause: string | null;
};
export type LocalAnalysis = {
  selection_id: string;
  job_id: string;
  bbox: LocalAnalysisBBox;             // the true crop rect, ORIGINAL image px
  offset: { x: number; y: number };
  scale: number;                        // working px per crop px
  working_size: { width: number; height: number };
  assets: LocalAnalysisAssets;          // outputs-relative paths — use outputUrl()
  drawing_summary: LocalDrawingSummary | null;   // focused local construction (brief §9)
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
