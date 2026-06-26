PENCIL: dict = {
    "name": "Pencil",
    "recommended_value_zones": 7,
    "recommended_palette_size": 6,
    "edge_strategy": "hatching",
    "texture_strategy": "crosshatch",
    "stages": [
        {
            "order": 1,
            "name": "Construction lines",
            "description": "Lightly sketch the major proportions with a 2H pencil. Use construction lines (centre line, bounding box, negative shapes). Don't draw what you think you see — measure.",
            "analysis_layers": ["level_1_outlines"],
        },
        {
            "order": 2,
            "name": "Contour refinement",
            "description": "Refine the outline with an HB pencil. Vary line weight: heavier on shadow-side contours, lighter on light-side edges. No outlines in finished drawings — vary the weight.",
            "analysis_layers": ["outlines_primary", "outlines_primary_secondary"],
        },
        {
            "order": 3,
            "name": "Value mass lay-in",
            "description": "With a 2B or 4B, block the shadow masses with consistent hatching direction. Identify the 3 major zones: dark, mid, light. Go darker than you think.",
            "analysis_layers": ["level_2_values", "level_3_values"],
        },
        {
            "order": 4,
            "name": "Hatching development",
            "description": "Build value through layered hatching at 45° or following the form. Crosshatch for darker tones. Keep strokes even in pressure, vary in density.",
            "analysis_layers": ["level_4_values"],
        },
        {
            "order": 5,
            "name": "Edge refinement",
            "description": "Use a kneaded eraser to lift highlights. Harden primary contours with a sharp 4B. Blend mid-tones with a tortillon in one direction only.",
            "analysis_layers": ["outlines_detailed", "level_5_values"],
        },
        {
            "order": 6,
            "name": "Accents and texture",
            "description": "Add the darkest dark (pure 8B or 9B). Re-establish lost edges. Add micro-texture in decorative areas. Final: pull highlights with an eraser.",
            "analysis_layers": ["level_5_outlines"],
        },
    ],
    "instructions": {
        "palette_note": "Use H grades for light, B grades for dark. Never press hard — layer instead.",
        "edge_note": "Pencil edges: sharp where light meets form, lost where shadow meets shadow.",
        "value_note": "Your darkest dark is your most expressive tool. Reserve 6B/8B for the deepest shadows only.",
    },
}
