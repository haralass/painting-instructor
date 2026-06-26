WATERCOLOR: dict = {
    "name": "Watercolour",
    "recommended_value_zones": 5,
    "recommended_palette_size": 8,
    "edge_strategy": "wet_on_wet",
    "texture_strategy": "granulation",
    "stages": [
        {
            "order": 1,
            "name": "Compositional sketch",
            "description": "Light pencil sketch (2H). Mark white areas explicitly — you cannot recover whites in watercolour. Mark reserved whites with masking fluid if needed.",
            "analysis_layers": ["outlines_primary", "level_1_outlines"],
        },
        {
            "order": 2,
            "name": "Preserve whites",
            "description": "Study the highlight map. These areas receive NO paint. Identify the 3–5 most important white areas. Everything else will be painted.",
            "analysis_layers": ["level_1_values"],
        },
        {
            "order": 3,
            "name": "First light washes",
            "description": "Wet-on-wet: dampen paper, drop in light transparent washes of the lightest colour families. Let bleed. Do not touch wet areas.",
            "analysis_layers": ["level_2_colours"],
        },
        {
            "order": 4,
            "name": "Mid-tone washes",
            "description": "When the first wash is dry, add mid-tone glazes. Each layer darkens. Work from the lightest to the darkest areas.",
            "analysis_layers": ["level_3_values", "level_3_colours"],
        },
        {
            "order": 5,
            "name": "Shadow accents",
            "description": "Add the darkest shadows wet-on-dry for crisp edges. These marks are final — do not rework them.",
            "analysis_layers": ["level_4_values", "outlines_primary_secondary"],
        },
        {
            "order": 6,
            "name": "Final accents",
            "description": "Add the smallest details: calligraphic marks, dark accents, texture strokes. Remove masking fluid. Add white gouache sparingly for recovered highlights.",
            "analysis_layers": ["level_5_outlines"],
        },
    ],
    "instructions": {
        "palette_note": "Use transparent pigments. Avoid earth tones that granulate heavily in washes.",
        "edge_note": "Wet edges blend; dry edges are hard. Control moisture to control edges.",
        "value_note": "Plan your darks before the first brushstroke. You can only go darker, never lighter.",
    },
}
