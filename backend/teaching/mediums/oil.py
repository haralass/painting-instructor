OIL: dict = {
    "name": "Oil Paint",
    "recommended_value_zones": 5,
    "recommended_palette_size": 12,
    "edge_strategy": "soft_blend",
    "texture_strategy": "impasto",
    "stages": [
        {
            "order": 1,
            "name": "Toned ground",
            "description": "Apply a mid-value imprimatura (burnt sienna or raw umber) thinned with turpentine. Wipe off lights with a rag. This kills the white and sets a mid-value starting point.",
            "analysis_layers": ["values", "outlines_primary"],
        },
        {
            "order": 2,
            "name": "Lay-in / block-in",
            "description": "With a large flat brush, block the major dark masses using thinned colour. Do not render — only map the shadow shapes. Think in 2 tones: shadow and light.",
            "analysis_layers": ["level_1_values", "level_1_outlines"],
        },
        {
            "order": 3,
            "name": "Value masses",
            "description": "Add the mid-tones and begin to differentiate the 5 Gurney zones. Work from dark to light. Paint thinner in darks, thicker in lights.",
            "analysis_layers": ["level_2_values", "level_2_colours"],
        },
        {
            "order": 4,
            "name": "Colour modelling",
            "description": "Introduce colour temperature: warm lights, cool shadows. Start mixing directly on the canvas. Do not overblend — keep the masses readable.",
            "analysis_layers": ["color_temperature", "level_3_colours"],
        },
        {
            "order": 5,
            "name": "Edge refinement",
            "description": "Harden primary structural edges. Soften transitions within shadow masses. Lost edges in darks; found edges in lights.",
            "analysis_layers": ["outlines_primary_secondary", "level_4_outlines"],
        },
        {
            "order": 6,
            "name": "Detail & texture",
            "description": "Add decorative details, texture, and final highlights. Use a small round brush. Keep the number of details to 10% of the surface.",
            "analysis_layers": ["level_5_outlines", "level_5_colours"],
        },
    ],
    "instructions": {
        "palette_note": "Limit your palette to 6-12 colours. Pre-mix all values before touching the canvas.",
        "edge_note": "Every edge is either lost, found, or soft. Never outline shapes — merge edges instead.",
        "value_note": "Squint until you see 3 values. If that doesn't read, nothing will.",
    },
}
