// GENERATED FILE — DO NOT EDIT.
// Source of truth: backend/capabilities.py (+ backend/teaching/mediums/*).
// Regenerate with: .venv/bin/python scripts/generate_frontend_contract.py
// tests/test_contract_drift.py fails when this file is stale.

export type CapabilityModes = { study: boolean; lesson: boolean; check: boolean };
export type CapabilitySupports = {
  local_region: boolean; manual_correction: boolean; checkpoint: boolean;
};
export type CapabilityCard = {
  id: string; name: string; category: string;
  description: string; why: string; tip: string;
  advertised: boolean; workspace: boolean;
  modes: CapabilityModes; supports: CapabilitySupports;
  sample: string | null;
};
export type DetailLevelInfo = {
  level: number; label: string; description: string; regions_hint: string;
};
export type MediumStageInfo = {
  order: number; name: string; description: string; why: string;
};

export const CAPABILITIES: CapabilityCard[] = [
  {
    "id": "line_art",
    "name": "Line Art",
    "category": "analysis",
    "description": "Weighted ink contours — silhouette, interior forms, texture.",
    "why": "Every painting starts with clear structure. These lines define the silhouette (thickest, most important), interior forms (medium weight), and background texture (lightest).",
    "tip": "Transfer these outlines to your canvas with light charcoal. Don't press hard — you'll erase them as you paint.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "line_art.jpg"
  },
  {
    "id": "notan",
    "name": "Value Study (Notan)",
    "category": "analysis",
    "description": "Lights and darks resolved first — get these right and the painting reads.",
    "why": "Notan is a Japanese design concept — before you touch colour, you must get your lights and darks right. A painting with correct values reads in black and white.",
    "tip": "Mix 3 values: darkest dark, mid grey, white. Fill the entire canvas with these before adding colour.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": true
    },
    "sample": "notan.jpg"
  },
  {
    "id": "color_temperature",
    "name": "Colour Temperature",
    "category": "analysis",
    "description": "Warm and cool tendencies mapped across this image.",
    "why": "In many lighting setups lit areas trend warm and shadows cool — but it depends on the light source. This map shows what THIS image actually does, approximated from LAB b* + chroma.",
    "tip": "Premix a warm and a cool version of your key colours. Follow the map, not a rule of thumb — check what the reference really does.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "color_temperature.jpg"
  },
  {
    "id": "color_palette",
    "name": "Colour Palette",
    "category": "analysis",
    "description": "Dominant colours by area, with real tube-mixing recipes.",
    "why": "The dominant colours of your reference, sorted by area coverage. A limited palette forces harmony — mix from these rather than adding new tubes.",
    "tip": "Lay out this palette before you start. Only these colours — no extras.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "color_palette.jpg"
  },
  {
    "id": "light_direction",
    "name": "Light & Shadow Zones",
    "category": "analysis",
    "description": "Gurney's five zones, from highlight to cast shadow.",
    "why": "Gurney's 5 zones: Highlight → Halftone → Core Shadow → Reflected Light → Cast Shadow. The core shadow is your darkest paint.",
    "tip": "Position your actual light source to match this angle, or mentally commit to it and never change it.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "light_direction.jpg"
  },
  {
    "id": "color_by_number",
    "name": "Paint by Numbers",
    "category": "exercise",
    "description": "Flat colour blocking from the same region hierarchy the lesson teaches.",
    "why": "Flat colour blocking is how most painters start a canvas. Fill the entire canvas before blending — if any white shows through, you cannot judge colour relationships.",
    "tip": "Block in flat colour before blending. Use a large flat brush, cover every zone completely.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": true
    },
    "sample": "color_by_number.jpg"
  },
  {
    "id": "dot_to_dot",
    "name": "Dot to Dot",
    "category": "exercise",
    "description": "Numbered dots along the real region boundaries — connect them to build the drawing.",
    "why": "These dots follow the actual boundaries of the image's major shapes. Connecting them in order builds your under-drawing.",
    "tip": "Connect these dots lightly with a pencil before painting. This is your structural under-drawing.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "dot_to_dot.jpg"
  },
  {
    "id": "subject_focus",
    "name": "Focal Subject",
    "category": "coaching",
    "description": "Your subject isolated — where the eye must land first.",
    "why": "A local segmentation model isolates your subject from its background. The eye should land here first — keep this area the sharpest, most saturated, and highest in contrast.",
    "tip": "Paint the muted areas first and loosely; save your cleanest colour, hardest edges, and thickest paint for the subject.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "subject_focus.jpg"
  },
  {
    "id": "depth_planes",
    "name": "Depth Planes",
    "category": "coaching",
    "description": "Foreground, middle and background split so distance reads cooler and softer.",
    "why": "A local depth model splits the scene into foreground, middle-ground and background. Atmospheric perspective means distance reads as cooler, lighter and lower in contrast.",
    "tip": "Push the background cooler, lighter and softer than it looks; reserve your warmest, darkest, hardest-edged notes for the foreground.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "depth_planes.jpg"
  },
  {
    "id": "local_vs_light",
    "name": "Local Colour vs Light",
    "category": "coaching",
    "description": "An estimate of the object's colour separated from the light falling on it.",
    "why": "Left is an ESTIMATE of the local colour with the light divided out; right is the estimated light alone. A shadow isn't a different colour — it's the same local colour under less light. The split is approximate, not a physical measurement.",
    "tip": "Judge an object's true colour from the lit-and-shadowed average, then adjust it for the light — don't reach for a whole new colour.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "local_vs_light.jpg"
  },
  {
    "id": "value_traps",
    "name": "Value Traps",
    "category": "coaching",
    "description": "Where simultaneous contrast will fool your eye — flagged before you paint.",
    "why": "Simultaneous contrast fools the eye: a shape looks darker against a light surround and lighter against a dark one, so you paint the apparent value, not the true one. The tinted zones are where the trap is strongest.",
    "tip": "In these zones, don't trust the local comparison. Judge the value against the whole picture — hold your darkest dark and lightest light in mind.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "value_traps.jpg"
  },
  {
    "id": "edge_coach",
    "name": "Edge Control",
    "category": "coaching",
    "description": "Hard, soft and lost edges mapped, so sharpness leads the eye.",
    "why": "The eye locks onto the hardest edge in the picture. Warm marks are your hard/found edges, cool are soft/lost. They should cluster on the focal subject — equal sharpness everywhere means nothing leads the eye.",
    "tip": "Keep your crispest edges on the focal point; soften edges where similar values meet and everywhere you want the eye to pass over.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": true
    },
    "sample": "edge_coach.jpg"
  },
  {
    "id": "composition",
    "name": "Composition & Focus",
    "category": "coaching",
    "description": "Where attention is pulled — and any rival that competes for it.",
    "why": "The warm ring is where the eye is pulled hardest (contrast × detail × colour); a cool ring marks a rival that competes for attention. A strong picture has one focal point.",
    "tip": "If two centres compete, subdue one — lower its contrast, detail or saturation.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": true
    },
    "sample": "composition.jpg"
  },
  {
    "id": "study_overlay",
    "name": "Detail Study",
    "category": "analysis",
    "description": "Every region boundary traced directly on the reference photograph.",
    "why": "Every colour-region boundary traced directly on the reference — the digital version of outlining shapes by hand on a print. Use it to see exactly where one colour ends and the next begins.",
    "tip": "Pick one small area, follow its traced shapes, and mix each one separately before you commit it to the canvas.",
    "advertised": true,
    "workspace": true,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": "study_overlay.jpg"
  },
  {
    "id": "lesson_plan",
    "name": "Guided Lesson",
    "category": "teaching",
    "description": "A staged painting plan for your medium, grounded in this image's own masses.",
    "why": "",
    "tip": "",
    "advertised": true,
    "workspace": false,
    "modes": {
      "study": true,
      "lesson": true,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": null
  },
  {
    "id": "critique",
    "name": "Progress Critique",
    "category": "teaching",
    "description": "Photograph your attempt and get measured, localised feedback against the reference.",
    "why": "",
    "tip": "",
    "advertised": true,
    "workspace": false,
    "modes": {
      "study": false,
      "lesson": false,
      "check": true
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": true
    },
    "sample": null
  },
  {
    "id": "detail_levels",
    "name": "Detail Explorer",
    "category": "teaching",
    "description": "One stable hierarchy of the image, from 5 masses to full detail — never re-segmented.",
    "why": "",
    "tip": "",
    "advertised": true,
    "workspace": false,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": null
  },
  {
    "id": "video",
    "name": "Tutorial Video",
    "category": "deliverable",
    "description": "A progressive video lesson: outline → values → colour → stroke by stroke.",
    "why": "",
    "tip": "",
    "advertised": true,
    "workspace": false,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": null
  },
  {
    "id": "pdf",
    "name": "Tutorial Book (PDF)",
    "category": "deliverable",
    "description": "The whole lesson assembled as a printable A4 book.",
    "why": "",
    "tip": "",
    "advertised": true,
    "workspace": false,
    "modes": {
      "study": true,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": null
  },
  {
    "id": "value_zones",
    "name": "Value Zone Map",
    "category": "internal",
    "description": "Internal value-simplification map used by the lesson plan and PDF.",
    "why": "",
    "tip": "",
    "advertised": false,
    "workspace": false,
    "modes": {
      "study": false,
      "lesson": false,
      "check": false
    },
    "supports": {
      "local_region": false,
      "manual_correction": false,
      "checkpoint": false
    },
    "sample": null
  }
];

/** Workspace-visible image studies, in display order. ACTIVE FILTER for manifest pages. */
export const CLASSIC_PAGE_KEYS: string[] = [
  "line_art",
  "notan",
  "color_temperature",
  "color_palette",
  "light_direction",
  "color_by_number",
  "dot_to_dot",
  "subject_focus",
  "depth_planes",
  "local_vs_light",
  "value_traps",
  "edge_coach",
  "composition",
  "study_overlay"
];

export const PAGE_LABELS: Record<string, { title: string; why: string; tip: string }> = {
  "line_art": {
    "title": "Line Art",
    "why": "Every painting starts with clear structure. These lines define the silhouette (thickest, most important), interior forms (medium weight), and background texture (lightest).",
    "tip": "Transfer these outlines to your canvas with light charcoal. Don't press hard — you'll erase them as you paint."
  },
  "notan": {
    "title": "Value Study (Notan)",
    "why": "Notan is a Japanese design concept — before you touch colour, you must get your lights and darks right. A painting with correct values reads in black and white.",
    "tip": "Mix 3 values: darkest dark, mid grey, white. Fill the entire canvas with these before adding colour."
  },
  "color_temperature": {
    "title": "Colour Temperature",
    "why": "In many lighting setups lit areas trend warm and shadows cool — but it depends on the light source. This map shows what THIS image actually does, approximated from LAB b* + chroma.",
    "tip": "Premix a warm and a cool version of your key colours. Follow the map, not a rule of thumb — check what the reference really does."
  },
  "color_palette": {
    "title": "Colour Palette",
    "why": "The dominant colours of your reference, sorted by area coverage. A limited palette forces harmony — mix from these rather than adding new tubes.",
    "tip": "Lay out this palette before you start. Only these colours — no extras."
  },
  "light_direction": {
    "title": "Light & Shadow Zones",
    "why": "Gurney's 5 zones: Highlight → Halftone → Core Shadow → Reflected Light → Cast Shadow. The core shadow is your darkest paint.",
    "tip": "Position your actual light source to match this angle, or mentally commit to it and never change it."
  },
  "color_by_number": {
    "title": "Paint by Numbers",
    "why": "Flat colour blocking is how most painters start a canvas. Fill the entire canvas before blending — if any white shows through, you cannot judge colour relationships.",
    "tip": "Block in flat colour before blending. Use a large flat brush, cover every zone completely."
  },
  "dot_to_dot": {
    "title": "Dot to Dot",
    "why": "These dots follow the actual boundaries of the image's major shapes. Connecting them in order builds your under-drawing.",
    "tip": "Connect these dots lightly with a pencil before painting. This is your structural under-drawing."
  },
  "subject_focus": {
    "title": "Focal Subject",
    "why": "A local segmentation model isolates your subject from its background. The eye should land here first — keep this area the sharpest, most saturated, and highest in contrast.",
    "tip": "Paint the muted areas first and loosely; save your cleanest colour, hardest edges, and thickest paint for the subject."
  },
  "depth_planes": {
    "title": "Depth Planes",
    "why": "A local depth model splits the scene into foreground, middle-ground and background. Atmospheric perspective means distance reads as cooler, lighter and lower in contrast.",
    "tip": "Push the background cooler, lighter and softer than it looks; reserve your warmest, darkest, hardest-edged notes for the foreground."
  },
  "local_vs_light": {
    "title": "Local Colour vs Light",
    "why": "Left is an ESTIMATE of the local colour with the light divided out; right is the estimated light alone. A shadow isn't a different colour — it's the same local colour under less light. The split is approximate, not a physical measurement.",
    "tip": "Judge an object's true colour from the lit-and-shadowed average, then adjust it for the light — don't reach for a whole new colour."
  },
  "value_traps": {
    "title": "Value Traps",
    "why": "Simultaneous contrast fools the eye: a shape looks darker against a light surround and lighter against a dark one, so you paint the apparent value, not the true one. The tinted zones are where the trap is strongest.",
    "tip": "In these zones, don't trust the local comparison. Judge the value against the whole picture — hold your darkest dark and lightest light in mind."
  },
  "edge_coach": {
    "title": "Edge Control",
    "why": "The eye locks onto the hardest edge in the picture. Warm marks are your hard/found edges, cool are soft/lost. They should cluster on the focal subject — equal sharpness everywhere means nothing leads the eye.",
    "tip": "Keep your crispest edges on the focal point; soften edges where similar values meet and everywhere you want the eye to pass over."
  },
  "composition": {
    "title": "Composition & Focus",
    "why": "The warm ring is where the eye is pulled hardest (contrast × detail × colour); a cool ring marks a rival that competes for attention. A strong picture has one focal point.",
    "tip": "If two centres compete, subdue one — lower its contrast, detail or saturation."
  },
  "study_overlay": {
    "title": "Detail Study",
    "why": "Every colour-region boundary traced directly on the reference — the digital version of outlining shapes by hand on a print. Use it to see exactly where one colour ends and the next begins.",
    "tip": "Pick one small area, follow its traced shapes, and mix each one separately before you commit it to the canvas."
  }
};

export const STEP_LABELS: Record<string, string> = {
  "loading": "Loading image",
  "subject_mask": "Isolating the subject",
  "depth": "Estimating depth",
  "line_art": "Drawing outlines",
  "notan": "Mapping values",
  "value_analysis": "Analysing values",
  "color_temperature": "Analysing warm/cool tones",
  "color_palette": "Extracting colour palette",
  "light_direction": "Finding light source",
  "color_by_number": "Building paint-by-numbers",
  "subject_focus": "Rendering the focal subject",
  "depth_planes": "Mapping depth planes",
  "local_vs_light": "Separating colour from light",
  "value_traps": "Detecting perceptual traps",
  "edge_coach": "Mapping edge hardness",
  "composition": "Checking the composition",
  "dot_to_dot": "Building the dot-to-dot exercise",
  "hierarchical": "Building hierarchical regions",
  "analysis_ready": "Analysis complete — generating extras",
  "observations": "Looking at your image",
  "rendering_extras": "Rendering video and PDF",
  "stroke_paint": "Painting the brushstrokes",
  "video": "Rendering tutorial video",
  "pdf": "Assembling PDF book",
  "manifest": "Writing manifest",
  "completed": "Tutorial ready"
};

export const STEP_STAGE: Record<string, number> = {
  "loading": 0,
  "subject_mask": 0,
  "depth": 0,
  "line_art": 1,
  "notan": 2,
  "value_analysis": 2,
  "color_temperature": 3,
  "color_palette": 3,
  "light_direction": 3,
  "color_by_number": 4,
  "subject_focus": 3,
  "depth_planes": 3,
  "local_vs_light": 3,
  "value_traps": 2,
  "edge_coach": 4,
  "composition": 4,
  "dot_to_dot": 1,
  "hierarchical": 4,
  "analysis_ready": 4,
  "observations": 4,
  "rendering_extras": 5,
  "stroke_paint": 5,
  "video": 5,
  "pdf": 5,
  "manifest": 5,
  "completed": 5
};

export const DETAIL_LEVELS: DetailLevelInfo[] = [
  {
    "level": 1,
    "label": "Foundation",
    "description": "The largest masses and primary contours — placement and structure only.",
    "regions_hint": "4–8 masses"
  },
  {
    "level": 2,
    "label": "Simplified",
    "description": "Major forms and the key light/shadow divisions.",
    "regions_hint": "8–25 regions"
  },
  {
    "level": 3,
    "label": "Standard",
    "description": "Important internal structure and colour zones — most paintings work here.",
    "regions_hint": "25–70 regions"
  },
  {
    "level": 4,
    "label": "Detailed",
    "description": "Smaller transitions, secondary edges and selected texture.",
    "regions_hint": "70–180 regions"
  },
  {
    "level": 5,
    "label": "Full Detail",
    "description": "Every detected region — the finest simplification the analysis makes. For the actual photograph, use the Reference view.",
    "regions_hint": "150–400 regions"
  }
];

export const LEVEL_LABELS: Record<number, string> = {
  "1": "Foundation",
  "2": "Simplified",
  "3": "Standard",
  "4": "Detailed",
  "5": "Full Detail"
};

export const MEDIUM_FALLBACKS: Record<string, { name: string; stages: MediumStageInfo[] }> = {
  "oil": {
    "name": "Oil Paint",
    "stages": [
      {
        "order": 1,
        "name": "Toned ground",
        "description": "Apply a mid-value imprimatura (burnt sienna or raw umber) thinned with turpentine. Wipe off lights with a rag. This kills the white and sets a mid-value starting point.",
        "why": "A white canvas lies to you: every colour you place on it looks darker than it is, so you overlighten everything. Starting from a mid-value means your first value judgements are already relative to something true."
      },
      {
        "order": 2,
        "name": "Lay-in / block-in",
        "description": "With a large flat brush, block the major dark masses using thinned colour. Do not render — only map the shadow shapes. Think in 2 tones: shadow and light.",
        "why": "The shadow shapes carry the whole structure of the image — if they are placed right, the painting reads correctly even with no detail at all. Detail added on top of wrong shapes only makes the wrongness permanent."
      },
      {
        "order": 3,
        "name": "Value masses",
        "description": "Add the mid-tones and begin to differentiate the 5 Gurney zones. Work from dark to light. Paint thinner in darks, thicker in lights.",
        "why": "Dark-to-light matters in oil because light paint is opaque and dark paint is transparent: lights placed last sit on top and stay clean. Thin darks also dry faster, which keeps the fat-over-lean rule intact so the surface never cracks."
      },
      {
        "order": 4,
        "name": "Colour modelling",
        "description": "Introduce colour temperature: warm lights, cool shadows. Start mixing directly on the canvas. Do not overblend — keep the masses readable.",
        "why": "Form is communicated by temperature as much as by value — a warm light against a cool shadow reads as sunlight even at equal values. Overblending destroys this: every stroke you blend averages a warm and a cool into a dead grey."
      },
      {
        "order": 5,
        "name": "Edge refinement",
        "description": "Harden primary structural edges. Soften transitions within shadow masses. Lost edges in darks; found edges in lights.",
        "why": "Edges steer the viewer's eye: the eye locks onto the hardest edge in the picture. If every edge is equally sharp, nothing is important; losing edges in the shadows lets the focal point win by contrast."
      },
      {
        "order": 6,
        "name": "Detail & texture",
        "description": "Add decorative details, texture, and final highlights. Use a small round brush. Keep the number of details to 10% of the surface.",
        "why": "Detail is expensive: every added detail competes for attention with the focal point. Ten percent of the surface, placed where you want the eye to go, reads as more finished than detail everywhere — the viewer's brain completes the rest."
      }
    ]
  },
  "watercolor": {
    "name": "Watercolour",
    "stages": [
      {
        "order": 1,
        "name": "Compositional sketch",
        "description": "Light pencil sketch (2H). Mark white areas explicitly — you cannot recover whites in watercolour. Mark reserved whites with masking fluid if needed.",
        "why": "Watercolour is the only medium where a mistake in planning is unrecoverable: there is no white paint coming to save you later. The sketch is not about drawing — it is a map of every area you must never touch."
      },
      {
        "order": 2,
        "name": "Preserve whites",
        "description": "Study the highlight map. These areas receive NO paint. Identify the 3–5 most important white areas. Everything else will be painted.",
        "why": "The paper itself is your brightest light — brighter than any pigment. A watercolour glows exactly as much as its preserved whites allow; lose them and the painting goes flat no matter what you do afterwards."
      },
      {
        "order": 3,
        "name": "First light washes",
        "description": "Wet-on-wet: dampen paper, drop in light transparent washes of the lightest colour families. Let bleed. Do not touch wet areas.",
        "why": "Every layer of watercolour darkens the one below and can never lighten it, so the sequence is forced: lightest first. Touching a drying wash is the classic beginner error — it lifts pigment into blooms that read as stains."
      },
      {
        "order": 4,
        "name": "Mid-tone washes",
        "description": "When the first wash is dry, add mid-tone glazes. Each layer darkens. Work from the lightest to the darkest areas.",
        "why": "Glazing over a dry wash multiplies transparency — two clean layers make a colour no single mixture can. Rushing this while the paper is damp muddies both layers instead, which is why patience here is a technique, not a virtue."
      },
      {
        "order": 5,
        "name": "Shadow accents",
        "description": "Add the darkest shadows wet-on-dry for crisp edges. These marks are final — do not rework them.",
        "why": "Dark accents define the value range of the whole painting — everything else is judged against them. Wet-on-dry gives them the crisp edges that pull them forward; reworking them lifts underlayers and turns your darkest note grey."
      },
      {
        "order": 6,
        "name": "Final accents",
        "description": "Add the smallest details: calligraphic marks, dark accents, texture strokes. Remove masking fluid. Add white gouache sparingly for recovered highlights.",
        "why": "Watercolour reads best when most of it is suggestion — a few confident final marks convince the eye that detail exists everywhere. Overworking this stage is how fresh paintings become tired ones."
      }
    ]
  },
  "acrylic": {
    "name": "Acrylic",
    "stages": [
      {
        "order": 1,
        "name": "Ground preparation",
        "description": "Tone the canvas with a mid-value acrylic wash (e.g., raw umber). Dry in 5 minutes. Unlike oil, acrylics allow immediate overpainting.",
        "why": "Against white canvas every value judgement you make will be too light. A five-minute toned ground gives you a true mid-point to judge against, and acrylic's fast drying means there is no excuse to skip it."
      },
      {
        "order": 2,
        "name": "Dark mass block-in",
        "description": "Block major shadow shapes with a flat brush and thinned acrylic. Work quickly — acrylics dry fast. Keep it gestural.",
        "why": "The shadow pattern is the skeleton of the picture: get it placed while the paint is workable and everything later has a home. Speed here is not sloppiness — a gestural block-in keeps you thinking in shapes instead of things."
      },
      {
        "order": 3,
        "name": "Colour blocking",
        "description": "Fill all major colour zones flat before blending. Work largest areas first. Accept the hard edges — they will be softened later.",
        "why": "You cannot judge any colour until its neighbours exist — colour is relative, and a 'correct' mixture against white canvas turns wrong the moment the area next to it is filled. Cover everything first; refine relationships second."
      },
      {
        "order": 4,
        "name": "Value refinement",
        "description": "Develop the 5-zone value structure. Use a wet brush to blend transitions before the paint dries. Work area by area.",
        "why": "Five distinct zones are what make form read as three-dimensional; fewer looks flat, more looks noisy. Acrylic forces area-by-area work because open time is minutes — treat that as a feature that keeps each passage decisive."
      },
      {
        "order": 5,
        "name": "Edge and form",
        "description": "Harden important structural edges with a liner brush. Soften internal transitions with a damp brush or glazing medium.",
        "why": "The eye goes wherever the hardest edge is — edge control is how you decide what the painting is about. Interior transitions softened, structural contours sharpened: that hierarchy is what separates a painting from a colouring-in."
      },
      {
        "order": 6,
        "name": "Texture and detail",
        "description": "Add impasto texture to light areas. Glaze transparent darks for luminosity. Final detail marks, highlights in titanium white.",
        "why": "Thick paint catches real light, so impasto belongs in the lights where the picture's light lives; glazes let darks stay deep without going dead. Saving pure titanium white for the very last marks keeps your highlights the single brightest thing on the canvas."
      }
    ]
  },
  "pencil": {
    "name": "Pencil",
    "stages": [
      {
        "order": 1,
        "name": "Construction lines",
        "description": "Lightly sketch the major proportions with a 2H pencil. Use construction lines (centre line, bounding box, negative shapes). Don't draw what you think you see — measure.",
        "why": "Your brain stores symbols — 'an eye', 'a tree' — and will draw the symbol instead of what is in front of you unless you force it to measure. Construction lines and negative shapes are tricks to bypass the symbol and see actual proportions."
      },
      {
        "order": 2,
        "name": "Contour refinement",
        "description": "Refine the outline with an HB pencil. Vary line weight: heavier on shadow-side contours, lighter on light-side edges. No outlines in finished drawings — vary the weight.",
        "why": "In the real world there are no outlines — only places where one value meets another. A line that is heavier on the shadow side already encodes the lighting, so your 'outline' starts doing the work of tone before you shade anything."
      },
      {
        "order": 3,
        "name": "Value mass lay-in",
        "description": "With a 2B or 4B, block the shadow masses with consistent hatching direction. Identify the 3 major zones: dark, mid, light. Go darker than you think.",
        "why": "Beginners' drawings look washed-out for one reason: fear of darks. Graphite reads roughly one value lighter than it feels while you apply it, so 'darker than you think' is not bravado — it is calibration."
      },
      {
        "order": 4,
        "name": "Hatching development",
        "description": "Build value through layered hatching at 45° or following the form. Crosshatch for darker tones. Keep strokes even in pressure, vary in density.",
        "why": "Layered hatching builds value the way glazes do in painting — each pass darkens predictably, which pressing harder never does. Strokes that follow the form also describe its surface direction for free, like contour lines on a map."
      },
      {
        "order": 5,
        "name": "Edge refinement",
        "description": "Use a kneaded eraser to lift highlights. Harden primary contours with a sharp 4B. Blend mid-tones with a tortillon in one direction only.",
        "why": "The eraser is a drawing tool, not a correction tool — lifting a highlight out of tone reads more naturally than leaving paper around it. One-direction blending matters because scrubbing back and forth destroys the hatching structure you spent stage 4 building."
      },
      {
        "order": 6,
        "name": "Accents and texture",
        "description": "Add the darkest dark (pure 8B or 9B). Re-establish lost edges. Add micro-texture in decorative areas. Final: pull highlights with an eraser.",
        "why": "A drawing's punch comes from its extremes: the single darkest accent and the cleanest lifted highlight, placed last so nothing dulls them. Everything between those two notes now reads richer by comparison."
      }
    ]
  },
  "charcoal": {
    "name": "Charcoal",
    "stages": [
      {
        "order": 1,
        "name": "Lay-in with vine charcoal",
        "description": "Use soft vine charcoal to sketch major proportions. Charcoal is erasable — be loose. Block the main shapes only. Tap off excess with a cloth.",
        "why": "Vine charcoal barely commits — a cloth takes it straight off — which frees you to search for the right shapes instead of protecting wrong ones. Tight careful lines at this stage are wasted effort on a drawing that will change."
      },
      {
        "order": 2,
        "name": "Shadow mass",
        "description": "Smudge the shadow mass into a unified dark tone. Use the side of the charcoal stick for large areas. Avoid individual marks at this stage.",
        "why": "One connected shadow mass is what gives a charcoal drawing its power — the moment you break it into separate patches, the light stops reading as one light. Individual marks fragment the mass; the stick's side keeps you thinking big."
      },
      {
        "order": 3,
        "name": "Value development",
        "description": "Layer darker charcoal (compressed charcoal) into the deepest shadows. Build up 4–5 value steps. Light areas remain the paper tone — do not fill them.",
        "why": "Compressed charcoal goes darker than vine ever can, so the deepest accents need it — but it is nearly permanent, which is why it waits until the shapes are proven. The untouched paper is your light: fill it and you have nothing brighter left."
      },
      {
        "order": 4,
        "name": "Lift highlights",
        "description": "Use a kneaded eraser to pull out the lightest highlights. Pull, don't rub. An eraser in charcoal is as important as the charcoal stick itself.",
        "why": "Charcoal is the one medium where you literally draw the light: lifting tone off reads cleaner than leaving paper around it. Pulling keeps the halo of tone intact; rubbing grinds the pigment in and greys the highlight forever."
      },
      {
        "order": 5,
        "name": "Edge control",
        "description": "Define crisp edges on the light side of forms. Blend and lose edges in the shadow masses. Use a tortillon or finger for blending only in mid-tone areas.",
        "why": "Edges are the drawing's hierarchy: crisp where light meets form (that is where the eye should go), lost inside shadow (that is where the eye should rest). Blending in the darks flattens them into velvet mush — it belongs only in the mid-tones."
      },
      {
        "order": 6,
        "name": "Final details",
        "description": "With a sharpened compressed charcoal stick, add the darkest accents and finest structural lines. Fix the drawing before adding any final marks.",
        "why": "Fixing first locks every layer below so the final accents sit on top at full strength instead of mixing into dust. Those last few darkest marks set the value range of the entire drawing — place them where you want the viewer to look."
      }
    ]
  },
  "digital": {
    "name": "Digital Painting",
    "stages": [
      {
        "order": 1,
        "name": "Canvas & value thumbnail",
        "description": "Set up the canvas at final aspect ratio. On one layer, paint a small 3-value thumbnail (dark / mid / light) with a hard round brush at low zoom. No line work yet.",
        "why": "Digital's infinite undo tempts you to skip planning, but a painting that was never designed cannot be fixed by editing. A 3-value thumbnail settles the composition in minutes, while it is still cheap to change everything."
      },
      {
        "order": 2,
        "name": "Big shape block-in",
        "description": "On a new layer, block the major masses with a hard round or lasso-fill at 100% opacity. Stay zoomed out. Use only the values from your thumbnail.",
        "why": "Working zoomed out at full opacity forces commitment — soft brushes at low opacity produce fog, not form. The lasso-fill trick keeps shapes crisp and stops you rendering before the design is proven."
      },
      {
        "order": 3,
        "name": "Local colour pass",
        "description": "Gamut-pick your palette from the extracted swatches. Fill each mass with its local colour on a colour layer (or repaint over the value block-in). Keep values locked to the thumbnail.",
        "why": "Picking colour straight from the reference teaches you nothing and often imports the camera's lies; mixing toward a deliberate, limited gamut is what builds colour judgement. Locking values while colouring protects the structure you already earned."
      },
      {
        "order": 4,
        "name": "Temperature & light",
        "description": "Shift lights warm and shadows cool (or the reverse, if the light source is cool). Use colour-adjust or glazing layers sparingly. One light source rules everything.",
        "why": "Light temperature is the fastest way to make a digital painting stop looking 'digital' — uniform hue across light and shadow is the tell. One consistent temperature logic sells the light more than any amount of rendering."
      },
      {
        "order": 5,
        "name": "Edges & focal rendering",
        "description": "Merge working layers. Sharpen edges at the focal point; soften or lose edges everywhere else with a soft brush or smudge at low strength. Render form only where the eye should land.",
        "why": "Digital tools make every edge razor-sharp by default, which spreads the viewer's attention evenly — the opposite of a painting. Deciding where NOT to render is the actual skill; the focal point only works because the rest stays quiet."
      },
      {
        "order": 6,
        "name": "Texture, effects & final pass",
        "description": "Add surface texture with textured brushes, subtle noise, or an overlay texture at low opacity. Final colour-balance pass. Flip the canvas one last time to check for drift.",
        "why": "Uniform digital smoothness reads as plastic; a little texture gives the eye a surface to believe. Flipping the canvas resets your adaptation — errors your eye has learned to ignore become obvious in the mirror image."
      }
    ]
  }
};
