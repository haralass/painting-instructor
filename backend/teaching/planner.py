"""
Image-specific lesson planning — the part that makes the instructor personal.

Everything here is deterministic and derived from the analysis pipeline's own
data (regions.json, palette, value zones, light angle). No external services.

The medium configs in mediums/*.py stay what they are: the *craft* curriculum
(how oil paint behaves, why watercolour goes light-to-dark). This module adds
what they can never contain: WHERE things are in *this* photo — which mass to
block in first, where the light comes from, which corner will tempt the
student into overworking.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# 3x3 location grid, row-major. Centroids are normalised to [0,1].
_LOC_WORDS = [
    ["upper left",  "top",     "upper right"],
    ["centre-left", "centre",  "centre-right"],
    ["lower left",  "bottom",  "lower right"],
]

# Light angle (deg, 0=right / 90=top / 180=left / 270=bottom) → compass words.
_LIGHT_SECTORS = [
    (22.5,  "the right"),
    (67.5,  "the upper right"),
    (112.5, "above"),
    (157.5, "the upper left"),
    (202.5, "the left"),
    (247.5, "the lower left"),
    (292.5, "below"),
    (337.5, "the lower right"),
    (360.1, "the right"),
]


def _loc_word(cx: float, cy: float) -> str:
    col = min(int(cx * 3), 2)
    row = min(int(cy * 3), 2)
    return _LOC_WORDS[row][col]


def _light_words(angle_deg: float) -> str:
    a = angle_deg % 360
    for limit, words in _LIGHT_SECTORS:
        if a < limit:
            return words
    return "the right"


def _nearest_palette_name(rgb: tuple, palette: list[dict]) -> str:
    if not palette:
        return "a mid tone"
    best, best_d = palette[0], float("inf")
    for p in palette:
        pr = p.get("base_rgb", (128, 128, 128))
        d = sum((int(a) - int(b)) ** 2 for a, b in zip(rgb, pr))
        if d < best_d:
            best, best_d = p, d
    return best.get("name", "a mid tone")


def _zone_grey(zone_id: int, value_zone_list: list[dict]) -> int:
    for z in value_zone_list:
        if z.get("id") == zone_id:
            return int(z.get("grey_value", 128))
    return 128


def _zone_label(zone_id: int, value_zone_list: list[dict]) -> str:
    for z in value_zone_list:
        if z.get("id") == zone_id:
            return str(z.get("label", "mid"))
    return "mid"


def load_regions(regions_json_path: str | Path) -> list[dict]:
    try:
        return json.loads(Path(regions_json_path).read_text())
    except Exception:
        log.warning("planner: could not read regions from %r", regions_json_path)
        return []


def build_image_brief(
    regions: list[dict],
    palette: list[dict],
    value_zone_list: list[dict],
    light_angle: float | None,
    img_w: int,
    img_h: int,
    medium: str = "oil",
    perspective: dict | None = None,
) -> dict:
    """
    Turn raw analysis data into the painting facts a teacher would point at:
    the big masses (where, how big, what colour, what value), the order to
    block them in for this medium, the light direction, the focal area, and
    the areas that will tempt overworking.
    """
    total_px = max(img_w * img_h, 1)

    def _norm_centroid(r: dict) -> tuple[float, float]:
        cx, cy = r.get("centroid", (img_w / 2, img_h / 2))
        return (min(max(cx / img_w, 0.0), 1.0), min(max(cy / img_h, 0.0), 1.0))

    # ── The big masses: level-1 regions, largest first ───────────────────────
    l1 = sorted(
        (r for r in regions if r.get("scale") == "l1"),
        key=lambda r: -r.get("area", 0),
    )
    masses = []
    for r in l1[:8]:
        cx, cy = _norm_centroid(r)
        area_frac = r.get("area", 0) / total_px
        if area_frac < 0.02:
            continue  # sub-2% slivers are noise, not paintable masses
        mean_rgb = tuple(int(c) for c in r.get("mean_rgb", (128, 128, 128)))
        masses.append({
            "region_id":   r.get("id"),
            "location":    _loc_word(cx, cy),
            "cx": round(cx, 3), "cy": round(cy, 3),
            "area_frac":   round(area_frac, 3),
            "mean_rgb":    list(mean_rgb),  # kept for deterministic mix-hint lookup
            "colour_name": _nearest_palette_name(mean_rgb, palette),
            "value_zone":  r.get("value_zone", 0),
            "value_label": _zone_label(r.get("value_zone", 0), value_zone_list),
            "grey":        _zone_grey(r.get("value_zone", 0), value_zone_list),
        })

    # ── Block-in order: watercolour must go light→dark, everything else
    #    establishes the darks first ────────────────────────────────────────
    light_first = medium == "watercolor"
    block_in = sorted(masses, key=lambda m: m["grey"], reverse=light_first)

    # ── Focal area: the most important mid-level region ─────────────────────
    l3 = [r for r in regions if r.get("scale") == "l3"]
    focal = None
    if l3:
        f = max(l3, key=lambda r: r.get("importance", 0))
        cx, cy = _norm_centroid(f)
        focal = {
            "location":    _loc_word(cx, cy),
            "cx": round(cx, 3), "cy": round(cy, 3),
            "colour_name": _nearest_palette_name(tuple(f.get("mean_rgb", (128, 128, 128))), palette),
            "importance":  round(f.get("importance", 0), 3),
        }

    # ── Busy areas: where the finest level piles up regions — these are the
    #    places a student will drown in detail ──────────────────────────────
    l5 = [r for r in regions if r.get("scale") == "l5"]
    cell_counts: dict[str, int] = {}
    for r in l5:
        cx, cy = _norm_centroid(r)
        cell_counts[_loc_word(cx, cy)] = cell_counts.get(_loc_word(cx, cy), 0) + 1
    busy_areas = []
    if cell_counts and len(l5) >= 9:
        mean_count = len(l5) / 9
        busy_areas = [
            {"location": loc, "region_count": n}
            for loc, n in sorted(cell_counts.items(), key=lambda kv: -kv[1])
            if n > mean_count * 1.6
        ][:2]

    # ── Value coverage: how much of the picture is dark vs light ────────────
    zone_area: dict[int, int] = {}
    for r in l1:
        zone_area[r.get("value_zone", 0)] = zone_area.get(r.get("value_zone", 0), 0) + r.get("area", 0)
    l1_total = max(sum(zone_area.values()), 1)
    coverage = sorted(
        ({"zone": z, "label": _zone_label(z, value_zone_list),
          "grey": _zone_grey(z, value_zone_list),
          "fraction": round(a / l1_total, 3)}
         for z, a in zone_area.items()),
        key=lambda c: c["grey"],
    )
    dark_frac = sum(c["fraction"] for c in coverage if c["grey"] < 100)

    # ── Warm / cool anchors from the palette ─────────────────────────────────
    warmest = coolest = None
    if palette:
        def _warmth(p: dict) -> float:
            r, g, b = p.get("base_rgb", (128, 128, 128))
            return float(r) - float(b)
        by_warmth = sorted(palette, key=_warmth)
        coolest, warmest = by_warmth[0].get("name"), by_warmth[-1].get("name")

    brief = {
        "light": {
            "angle": round(light_angle, 1) if light_angle is not None else None,
            "from":  _light_words(light_angle) if light_angle is not None else None,
        },
        "masses":       masses,
        "block_in_order": [m["region_id"] for m in block_in],
        "block_in_light_first": light_first,
        "focal":        focal,
        "busy_areas":   busy_areas,
        "value_coverage": coverage,
        "dark_fraction": round(dark_frac, 3),
        "warmest_colour": warmest,
        "coolest_colour": coolest,
        "perspective": perspective,
    }
    brief["overview"] = _overview_text(brief, medium)
    return brief


def _overview_text(brief: dict, medium: str) -> str:
    """3-4 plain sentences a teacher would say before the first brushstroke."""
    parts: list[str] = []

    light_from = brief["light"]["from"]
    if light_from:
        parts.append(f"The light in this photo comes from {light_from}.")
    else:
        parts.append(
            "The light here is soft and diffuse — no single direction. Model form with close values and gentle "
            "edges rather than strong cast shadows."
        )

    masses = brief["masses"]
    if masses:
        m0 = masses[0]
        parts.append(
            f"The biggest mass is the {m0['value_label']} {m0['colour_name']} shape in the "
            f"{m0['location']}, about {round(m0['area_frac'] * 100)}% of the picture — "
            f"when that sits correctly, everything else has an anchor."
        )

    dark = brief["dark_fraction"]
    if dark >= 0.55:
        parts.append(
            f"This is a dark-dominant image ({round(dark * 100)}% shadow): protect your few lights — they carry the picture."
        )
    elif dark <= 0.25:
        parts.append(
            f"This is a light-dominant image (only {round(dark * 100)}% shadow): the darks are rare, so place them precisely."
        )

    if brief["busy_areas"]:
        b = brief["busy_areas"][0]
        parts.append(
            f"The busiest area is the {b['location']} — it will tempt you into detail long before the painting is ready for it."
        )

    vp = brief.get("perspective")
    if vp:
        parts.append(
            f"This image has true perspective: {vp['n_lines']} structural lines converge toward the "
            f"{_loc_word(vp['nx'], vp['ny'])}. Establish those lines straight and early — if they drift, "
            "nothing built on them will sit right."
        )

    return " ".join(parts)


# ── Attaching notes to lesson steps ──────────────────────────────────────────

def _mix_hint_for(mean_rgb, medium: str) -> str | None:
    """
    Short paint-mixing recipe hint for a mass's mean colour, from the local
    Kubelka-Munk mixer. Only for physical-paint mediums; None otherwise or if
    the mixer is unavailable / the colour can't be resolved.
    """
    try:
        from .mixing import MIXING_MEDIUMS, recipe_for
    except Exception:
        return None
    if medium not in MIXING_MEDIUMS or not mean_rgb:
        return None
    try:
        return recipe_for(tuple(int(c) for c in mean_rgb)).get("text")
    except Exception:
        return None


def _build_micro_steps(order: list[dict], brief: dict, medium: str) -> list[dict]:
    """
    One structured, ordered painting instruction per mass, in the medium's
    block-in direction. Uses ALL masses in `block_in_order` (not a truncated
    slice). `order` is 1-based within the step. Empty list when no masses.
    """
    light_first = brief.get("block_in_light_first", False)
    verb = "Wash in" if light_first else "Block in"
    micro: list[dict] = []
    for i, m in enumerate(order, start=1):
        pct = round(m["area_frac"] * 100)
        action = (
            f"{verb} the {m['value_label']} {m['colour_name']} mass "
            f"in the {m['location']} (~{pct}%)."
        )
        micro.append({
            "order":       i,
            "region_id":   m.get("region_id"),
            "location":    m.get("location"),
            "value_label": m.get("value_label"),
            "colour_name": m.get("colour_name"),
            "area_frac":   m.get("area_frac"),
            "action":      action,
            "mix_hint":    _mix_hint_for(m.get("mean_rgb"), medium),
        })
    return micro


def attach_image_notes(steps: list[dict], brief: dict, medium: str) -> list[dict]:
    """
    Give each lesson step 1-3 sentences about THIS image. Placement is driven
    by what the step actually shows (its resolved asset keys and level), not
    by stage names, so it works for every medium config uniformly.
    """
    masses = brief.get("masses", [])
    by_id = {m["region_id"]: m for m in masses}
    order = [by_id[i] for i in brief.get("block_in_order", []) if i in by_id]
    focal = brief.get("focal")
    busy = brief.get("busy_areas", [])
    light_from = brief.get("light", {}).get("from")

    real_orders = [s.get("order", 0) for s in steps if 1 <= s.get("order", 0) < 90]
    max_order = max((s.get("order", 0) for s in steps), default=0)
    # A real step, identified by its own order rather than object identity —
    # the previous `step is next(...)` check broke whenever the list was copied.
    min_real_order = min(real_orders) if real_orders else None

    # The full ordered micro-step list attaches to exactly ONE step — the early
    # block-in/value stage — so each mass appears once overall. Target the
    # earliest real value-carrying step that is neither the ground/first
    # planning step (min_real_order) nor an edge/detail step (level >= 4);
    # fall back to any real value step, then to the first real step.
    micro_target_order: int | None = None
    value_steps = [
        s for s in steps
        if 1 <= s.get("order", 0) < 90 and "values" in " ".join(s.get("assets", {}).keys())
    ]
    early_block_in = [
        s for s in value_steps
        if s.get("order") != min_real_order and s.get("level", 1) < 4
    ]
    if early_block_in:
        micro_target_order = min(s["order"] for s in early_block_in)
    elif value_steps:
        micro_target_order = min(s["order"] for s in value_steps)
    elif min_real_order is not None:
        micro_target_order = min_real_order

    for step in steps:
        notes: list[str] = []
        keys = " ".join(step.get("assets", {}).keys())
        lvl = step.get("level", 1)
        first_real = step.get("order") == min_real_order

        # Structured, ordered micro-steps: default empty; the full list lands on
        # the single chosen block-in/value step.
        step["image_micro_steps"] = (
            _build_micro_steps(order, brief, medium)
            if order and step.get("order") == micro_target_order
            else []
        )

        # Early structural steps: where to start, and the light
        if first_real or lvl <= 1:
            if light_from:
                notes.append(f"Keep in mind from the start: the light comes from {light_from} — every shadow you place must agree with it.")
            else:
                notes.append("The light in this photo is diffuse — don't invent hard cast shadows; the form reads through close, soft value shifts.")
            vp = brief.get("perspective")
            if vp:
                notes.append(
                    f"Draw the perspective lines first: {vp['n_lines']} of them converge toward the "
                    f"{_loc_word(vp['nx'], vp['ny'])} — lay them in with a straightedge before any mass."
                )
            if order:
                seq = order[:3]
                direction = "lightest first" if brief.get("block_in_light_first") else "darkest first"
                notes.append(
                    "Block-in order for this image (" + direction + "): "
                    + "; then ".join(
                        f"the {m['value_label']} {m['colour_name']} mass in the {m['location']} (~{round(m['area_frac'] * 100)}%)"
                        for m in seq
                    ) + "."
                )

        # Value-carrying steps
        if "values" in keys and not first_real:
            dark = brief.get("dark_fraction", 0)
            cov = brief.get("value_coverage", [])
            if cov:
                darkest = cov[0]
                notes.append(
                    f"In this image the darkest zone ('{darkest['label']}') covers about "
                    f"{round(darkest['fraction'] * 100)}% of the surface — mix enough of that value to cover it in one session."
                )
            if dark >= 0.55 and lvl >= 3:
                notes.append("Dark-dominant image: resist lightening the shadows to 'rescue' them — their mass is the design.")

        # Colour / temperature steps
        if ("colours" in keys or "color" in keys) and brief.get("warmest_colour"):
            notes.append(
                f"Your temperature anchors here are {brief['warmest_colour']} (warmest) and "
                f"{brief['coolest_colour']} (coolest) — every other mixture sits between them."
            )
            if focal:
                notes.append(
                    f"Save your cleanest colour for the {focal['location']} — the analysis puts the focal interest there."
                )

        # Edge / detail steps
        if lvl >= 4 or step.get("order", 0) == max_order:
            if focal and not any("focal" in n or focal["location"] in n for n in notes):
                notes.append(f"Sharpest edges and final details belong around the {focal['location']} — nowhere else.")
            for b in busy:
                notes.append(
                    f"The {b['location']} is the busiest area of this photo "
                    f"({b['region_count']} distinct regions at full detail) — simplify it to a handful of shapes and stop."
                )

        step["image_notes"] = notes[:3]

    return steps
