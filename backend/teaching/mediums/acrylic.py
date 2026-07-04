ACRYLIC: dict = {
    "name": "Acrylic",
    "recommended_value_zones": 5,
    "recommended_palette_size": 12,
    "edge_strategy": "hard_soft_mix",
    "texture_strategy": "impasto_or_glaze",
    "stages": [
        {
            "order": 1,
            "name": "Ground preparation",
            "description": "Tone the canvas with a mid-value acrylic wash (e.g., raw umber). Dry in 5 minutes. Unlike oil, acrylics allow immediate overpainting.",
            "analysis_layers": ["level_1_values"],
        },
        {
            "order": 2,
            "name": "Dark mass block-in",
            "description": "Block major shadow shapes with a flat brush and thinned acrylic. Work quickly — acrylics dry fast. Keep it gestural.",
            "analysis_layers": ["level_1_outlines", "level_2_values"],
        },
        {
            "order": 3,
            "name": "Colour blocking",
            "description": "Fill all major colour zones flat before blending. Work largest areas first. Accept the hard edges — they will be softened later.",
            "analysis_layers": ["level_2_colours", "color_by_number"],
        },
        {
            "order": 4,
            "name": "Value refinement",
            "description": "Develop the 5-zone value structure. Use a wet brush to blend transitions before the paint dries. Work area by area.",
            "analysis_layers": ["level_3_values", "level_3_colours"],
        },
        {
            "order": 5,
            "name": "Edge and form",
            "description": "Harden important structural edges with a liner brush. Soften internal transitions with a damp brush or glazing medium.",
            "analysis_layers": ["outlines_primary_secondary", "level_4_outlines"],
        },
        {
            "order": 6,
            "name": "Texture and detail",
            "description": "Add impasto texture to light areas. Glaze transparent darks for luminosity. Final detail marks, highlights in titanium white.",
            "analysis_layers": ["level_5_outlines", "level_5_colours"],
        },
    ],
    "instructions": {
        "palette_note": "Keep a wet palette to extend working time. Add retarder medium if needed.",
        "edge_note": "Acrylics dry darker. Test on a separate surface. Layer transparency with glazing medium.",
        "value_note": "Acrylics are forgiving — you can paint lights over darks with opaque paint.",
    },
}
