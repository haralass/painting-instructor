CHARCOAL: dict = {
    "name": "Charcoal",
    "recommended_value_zones": 5,
    "recommended_palette_size": 6,
    "edge_strategy": "smudge_blend",
    "texture_strategy": "grain",
    "stages": [
        {
            "order": 1,
            "name": "Lay-in with vine charcoal",
            "description": "Use soft vine charcoal to sketch major proportions. Charcoal is erasable — be loose. Block the main shapes only. Tap off excess with a cloth.",
            "analysis_layers": ["level_1_outlines", "level_1_values"],
        },
        {
            "order": 2,
            "name": "Shadow mass",
            "description": "Smudge the shadow mass into a unified dark tone. Use the side of the charcoal stick for large areas. Avoid individual marks at this stage.",
            "analysis_layers": ["level_2_values"],
        },
        {
            "order": 3,
            "name": "Value development",
            "description": "Layer darker charcoal (compressed charcoal) into the deepest shadows. Build up 4–5 value steps. Light areas remain the paper tone — do not fill them.",
            "analysis_layers": ["level_3_values"],
        },
        {
            "order": 4,
            "name": "Lift highlights",
            "description": "Use a kneaded eraser to pull out the lightest highlights. Pull, don't rub. An eraser in charcoal is as important as the charcoal stick itself.",
            "analysis_layers": ["level_4_values", "outlines_primary_secondary"],
        },
        {
            "order": 5,
            "name": "Edge control",
            "description": "Define crisp edges on the light side of forms. Blend and lose edges in the shadow masses. Use a tortillon or finger for blending only in mid-tone areas.",
            "analysis_layers": ["outlines_detailed", "level_5_values"],
        },
        {
            "order": 6,
            "name": "Final details",
            "description": "With a sharpened compressed charcoal stick, add the darkest accents and finest structural lines. Fix the drawing before adding any final marks.",
            "analysis_layers": ["level_5_outlines"],
        },
    ],
    "instructions": {
        "palette_note": "Vine charcoal for initial lay-in (erasable), compressed charcoal for darks (permanent).",
        "edge_note": "Charcoal lives and dies by the eraser. Practice removing as much as applying.",
        "value_note": "Charcoal dries lighter. Always fix each layer before building the next.",
    },
}
