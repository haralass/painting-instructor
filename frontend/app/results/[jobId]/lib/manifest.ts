// ── Shared constants, label maps, types and URL helpers for the results view ──

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Which evolving-canvas stage each pipeline step should show, so the loading
// screen paints the picture forward as the real work advances.
export const STEP_STAGE: Record<string, number> = {
  loading: 0, line_art: 1, notan: 2, color_temperature: 3, color_palette: 3,
  light_direction: 3, color_by_number: 4, dot_to_dot: 1, hierarchical: 4,
  video: 5, pdf: 5, manifest: 5, completed: 5,
};

// ── Step labels for the progress display ─────────────────────────────────────
export const STEP_LABELS: Record<string, string> = {
  loading:          "Loading image…",
  line_art:         "Drawing outlines…",
  notan:            "Mapping values…",
  color_temperature:"Analysing colour temperature…",
  color_palette:    "Extracting colour palette…",
  light_direction:  "Finding light source…",
  color_by_number:  "Building paint-by-numbers…",
  dot_to_dot:       "Placing structural dots…",
  hierarchical:     "Building hierarchical regions…",
  video:            "Rendering tutorial video…",
  pdf:              "Assembling PDF…",
  manifest:         "Writing manifest…",
  completed:        "Tutorial ready",
};

// ── Page labels for classic analysis outputs ──────────────────────────────────
export const PAGE_LABELS: Record<string, { title: string; why: string; tip: string }> = {
  line_art: {
    title: "Line Art",
    why:   "Every painting starts with clear structure. These lines define the silhouette (thickest, most important), interior forms (medium weight), and background texture (lightest).",
    tip:   "Transfer these outlines to your canvas with light charcoal. Don't press hard — you'll erase them as you paint.",
  },
  subject_focus: {
    title: "Focal Subject",
    why:   "A local segmentation model isolates your subject from its background. The eye should land here first — keep this area the sharpest, most saturated, and highest in contrast.",
    tip:   "Paint the muted areas first and loosely; save your cleanest colour, hardest edges, and thickest paint for the subject.",
  },
  depth_planes: {
    title: "Depth Planes",
    why:   "A local depth model splits the scene into foreground, middle-ground and background. Atmospheric perspective means distance reads as cooler, lighter and lower in contrast — warm/sharp up front, cool/soft far away.",
    tip:   "Push the background cooler, lighter and softer than it looks; reserve your warmest, darkest, hardest-edged notes for the foreground.",
  },
  local_vs_light: {
    title: "Local Colour vs Light",
    why:   "Left is the local colour with the light divided out; right is the light alone. A shadow isn't a different colour — it's the same local colour under less light. Mix the local colour first, then adjust it for the light.",
    tip:   "Judge an object's true colour from the lit-and-shadowed average, then push it warmer/lighter in the light and cooler/darker in shadow — don't reach for a whole new colour.",
  },
  notan: {
    title: "Value Study (Notan)",
    why:   "Notan is a Japanese design concept — before you touch colour, you must get your lights and darks right. A painting with correct values reads in black and white.",
    tip:   "Mix 3 values: darkest dark, mid grey, white. Fill the entire canvas with these before adding colour.",
  },
  color_temperature: {
    title: "Colour Temperature",
    why:   "Lit areas are warm (yellow/orange), shadows are cool (blue/purple). This is James Gurney's core principle. This map shows an approximation based on LAB b* + chroma.",
    tip:   "Premix a warm and a cool version of every colour. Lean lights warm, shadows cool.",
  },
  color_palette: {
    title: "Colour Palette",
    why:   "The dominant colours of your reference, sorted by area coverage. A limited palette forces harmony — mix from these rather than adding new tubes.",
    tip:   "Lay out this palette before you start. Only these colours — no extras.",
  },
  light_direction: {
    title: "Light & Shadow Zones",
    why:   "Gurney's 5 zones: Highlight → Halftone → Core Shadow → Reflected Light → Cast Shadow. The core shadow is your darkest paint.",
    tip:   "Position your actual light source to match this angle, or mentally commit to it and never change it.",
  },
  color_by_number: {
    title: "Paint by Numbers",
    why:   "Flat colour blocking is how every master painter starts a canvas. Fill the entire canvas before blending — if any white shows through, you cannot judge colour relationships.",
    tip:   "Block in flat colour before blending. Use a large flat brush, cover every zone completely.",
  },
  dot_to_dot: {
    title: "Structural Dots",
    why:   "These dots trace the most structurally significant edges. Connecting them in order builds your under-drawing.",
    tip:   "Connect these dots lightly with a pencil before painting. This is your structural under-drawing.",
  },
  study_overlay: {
    title: "Detail Study",
    why:   "Every colour-region boundary traced directly on the reference — the digital version of outlining shapes by hand on a print. Use it to see exactly where one colour ends and the next begins.",
    tip:   "Pick one small area, follow its traced shapes, and mix each one separately before you commit it to the canvas.",
  },
};

// ── Level labels for hierarchical detail ─────────────────────────────────────
export const LEVEL_LABELS: Record<number, string> = {
  1: "Foundation",
  2: "Simplified",
  3: "Standard",
  4: "Detailed",
  5: "Full Reference",
};

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

export const CLASSIC_PAGE_KEYS = [
  "line_art", "notan", "color_temperature", "color_palette",
  "light_direction", "color_by_number", "dot_to_dot", "study_overlay",
];

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
