from __future__ import annotations
import logging
import re

log = logging.getLogger(__name__)

_LEVEL_ASSET_RE = re.compile(r"^level_(\d)_(values|colours|outlines|regions)$")

# ── Adaptive-teaching levers ──────────────────────────────────────────────────
# A returning student's Adaptive Painter Profile (backend/critique/profile.py)
# reshapes their NEXT lesson. Everything here is a pure, deterministic function
# of the profile dict — no LLM. A missing/empty profile is a no-op, so output is
# byte-identical to today's when no profile is supplied.

# Which teaching category a recurring weakness (profile metric) belongs to.
_WEAKNESS_CATEGORY = {
    "value_compression":  "value",
    "edge_hardness":      "edge",
    "temp_bias":          "colour",
    "temp_light_shadow":  "colour",
    "chroma_bias":        "colour",
    "hue_error":          "colour",
}

# Keywords that identify the stage each category maps to, scored against every
# stage's name (+2 per hit) and its analysis_layers (+1 per hit). The highest
# scoring stage wins; ties break to the lowest order. Works uniformly across
# every medium config because it reads the config, not hard-coded stage numbers.
_CATEGORY_KEYWORDS = {
    "value":  {"name": ("value", "notan"),                    "layer": ("values", "notan")},
    "colour": {"name": ("colour", "color", "temperature", "temp"), "layer": ("colours", "color")},
    "edge":   {"name": ("edge",),                              "layer": ("outline", "edge")},
}

# Per-user watch-out note, templated from the weakness {metric, direction}. Two
# variants per metric keyed on the signed error's sign; {n} = critiques seen.
_NOTE_TEMPLATES = {
    "value_compression": (
        "You've compressed the value range in your last {n} paintings — push your darkest dark and lightest light further apart than feels comfortable before you commit here.",
        "You've over-extended contrast in your last {n} paintings — keep the midtones connected instead of forcing everything to black and white.",
    ),
    "chroma_bias": (
        "You've oversaturated your last {n} paintings — mix a neutral of the same value before committing colour here.",
        "Your last {n} paintings came out too grey — let the focal colour stay saturated instead of neutralising it.",
    ),
    "temp_bias": (
        "Your last {n} paintings ran too warm — cool your shadows before they take over the picture.",
        "Your last {n} paintings ran too cool — warm your lights so the picture doesn't go cold.",
    ),
    "temp_light_shadow": (
        "You've under-separated light and shadow temperature across your last {n} paintings — make the lights warmer and the shadows cooler than you think.",
        "You've over-separated light and shadow temperature across your last {n} paintings — pull the temperature contrast back toward the reference.",
    ),
    "edge_hardness": (
        "Your focal edges have been too hard in your last {n} paintings — lose the edges inside the shadow masses and save the crisp edge for the focal point.",
        "Your focal edges have been too soft in your last {n} paintings — commit at least one genuinely crisp edge at the focal point.",
    ),
    "hue_error": (
        "Your hues have drifted off the reference in your last {n} paintings — check each mixture's hue against the reference swatch before committing.",
        "Your hues have drifted off the reference in your last {n} paintings — check each mixture's hue against the reference swatch before committing.",
    ),
}

# The single weakness to beat this session, surfaced as a top-level lesson goal.
_LESSON_GOALS = {
    "value_compression": "Beat your habit this session: get your value range within 15% of the reference — a true darkest dark and a true lightest light.",
    "chroma_bias":       "Beat your habit this session: match the reference's saturation — no colour more intense (or more grey) than what's actually there.",
    "temp_bias":         "Beat your habit this session: keep your overall temperature neutral against the reference — no global warm or cool cast.",
    "temp_light_shadow": "Beat your habit this session: separate light and shadow temperature exactly as much as the reference does — no more, no less.",
    "edge_hardness":     "Beat your habit this session: reserve your single hardest edge for the focal point and lose the rest.",
    "hue_error":         "Beat your habit this session: match each mixture's hue to the reference before you commit it.",
}


def _stage_order_for_category(medium_cfg: dict, category: str) -> int | None:
    """Deterministically pick the stage order that best represents `category`."""
    kw = _CATEGORY_KEYWORDS.get(category)
    if not kw:
        return None
    best_order: int | None = None
    best_score = 0
    for stage in medium_cfg.get("stages", []):
        name = str(stage.get("name", "")).lower()
        score = 0
        for k in kw["name"]:
            if k in name:
                score += 2
        for layer in stage.get("analysis_layers", []):
            low = str(layer).lower()
            if any(k in low for k in kw["layer"]):
                score += 1
        if score > best_score:  # strict > => ties keep the lowest order
            best_score, best_order = score, stage.get("order")
    return best_order


def _profile_levers(profile: dict | None, medium_cfg: dict) -> dict | None:
    """
    Translate the top-ranked weakness in `profile` into the concrete levers a
    lesson should pull. Returns None (a no-op) when there is no profile, no
    weakness, or the top weakness maps to no teaching category.
    """
    if not profile:
        return None
    weaknesses = profile.get("weaknesses") or []
    if not weaknesses:
        return None
    top = weaknesses[0] or {}
    metric = top.get("metric")
    category = _WEAKNESS_CATEGORY.get(metric)
    if not category:
        return None

    n = int(profile.get("n_critiques") or 0)
    n_txt = str(n) if n > 0 else "recent"
    templ = _NOTE_TEMPLATES.get(metric)
    if templ:
        pos, neg = templ
        note = (pos if float(top.get("signed_mean", 0.0) or 0.0) >= 0 else neg).format(n=n_txt)
    else:
        note = f"Across your last {n_txt} paintings this painter {top.get('direction', 'has a recurring habit')} — correct for it in this stage."

    return {
        "category":           category,
        "metric":             metric,
        "stage_order":        _stage_order_for_category(medium_cfg, category),
        "note":               note,
        "lesson_goal":        _LESSON_GOALS.get(metric),
        "force_value_warmup": metric == "value_compression",
    }

_GLOBAL_OUTLINE_KEYS = {
    "outlines_primary", "outlines_primary_secondary", "outlines_detailed", "outlines_full",
}

# Classic-pipeline pages that mediums reference directly as an analysis layer
# (e.g. oil/digital stage 4 -> "color_temperature", digital/acrylic stage 3 ->
# "color_by_number"). These are single, well-known per-job pages saved as
# "<stem>.png" next to every other classic page, so they resolve to that path
# even when the classic step itself failed to enter `classic_pages` — otherwise
# every oil/digital job logged "could not resolve analysis_layer 'color_temperature'"
# and silently dropped the asset.
_CLASSIC_PAGE_LAYERS = {"color_temperature", "color_by_number"}


def build_lesson_plan(
    medium_cfg: dict,
    medium: str,
    detail_levels: dict,
    outline_composites: dict,
    value_zones_map: str | None,
    classic_pages: list[str],
    skill_level: str = "intermediate",
    profile: dict | None = None,
) -> list[dict]:
    """
    Resolve each medium teaching stage's `analysis_layers` keys against the
    real, already-generated asset paths for this job, so a lesson step names
    exactly what the learner should be looking at (instead of static text
    that never points anywhere).

    All inputs are already outputs-relative paths (post `_build_manifest`
    normalisation), so the result can be embedded directly in manifest.json.
    """
    classic_by_stem: dict[str, str] = {}
    classic_dir: str | None = None
    for p in classic_pages:
        if not p:
            continue
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        classic_by_stem[stem] = p
        # Remember the shared job directory so classic-page layers whose own
        # page failed to reach `classic_pages` can still resolve to the
        # canonical "<dir>/<stem>.png" location (all classic pages share it).
        if classic_dir is None and "/" in p:
            classic_dir = p.rsplit("/", 1)[0]

    steps: list[dict] = []
    for stage in medium_cfg.get("stages", []):
        assets: dict[str, str] = {}
        levels_referenced: list[int] = []

        for layer_key in stage.get("analysis_layers", []):
            m = _LEVEL_ASSET_RE.match(layer_key)
            if m:
                lvl, field = int(m.group(1)), m.group(2)
                levels_referenced.append(lvl)
                path = detail_levels.get(str(lvl), {}).get(field)
                if path:
                    assets[layer_key] = path
                else:
                    log.warning(
                        "lesson_plan: level %d field %r missing for stage %r (%s)",
                        lvl, field, stage.get("name"), medium,
                    )
                continue

            if layer_key in _GLOBAL_OUTLINE_KEYS:
                path = outline_composites.get(layer_key)
                if path:
                    assets[layer_key] = path
                else:
                    log.warning(
                        "lesson_plan: outline composite %r missing for stage %r (%s)",
                        layer_key, stage.get("name"), medium,
                    )
                continue

            if layer_key == "values" and value_zones_map:
                assets[layer_key] = value_zones_map
                continue

            if layer_key in classic_by_stem:
                assets[layer_key] = classic_by_stem[layer_key]
                continue

            # A well-known classic page referenced as a layer, whose own page
            # did not make it into `classic_pages` this run (step failed, or
            # was pruned). Resolve to its canonical sibling path so the lesson
            # step still points somewhere instead of dropping the asset.
            if layer_key in _CLASSIC_PAGE_LAYERS and classic_dir:
                assets[layer_key] = f"{classic_dir}/{layer_key}.png"
                continue

            log.warning(
                "lesson_plan: could not resolve analysis_layer %r for stage %r (%s)",
                layer_key, stage.get("name"), medium,
            )

        level = max(levels_referenced) if levels_referenced else 1
        steps.append({
            "order":       stage["order"],
            "name":        stage["name"],
            "description": stage["description"],
            "why":         stage.get("why", ""),
            "medium":      medium,
            "level":       level,
            "assets":      assets,
        })

    # ── Adaptive levers (deterministic, no-op without a profile) ─────────────
    levers = _profile_levers(profile, medium_cfg)
    force_value_warmup = False
    if levers:
        force_value_warmup = bool(levers["force_value_warmup"])
        target = levers["stage_order"]
        if target is not None:
            for step in steps:
                if step["order"] == target:
                    step["emphasis"] = True                 # emphasis lever
                    step["profile_notes"] = [levers["note"]]  # watch-out lever
                    break

    steps = _adapt_for_skill(
        steps, skill_level, medium, classic_by_stem, value_zones_map,
        force_value_warmup=force_value_warmup,
    )

    # Goal lever: name the weakness to beat this session. Sits on the first step
    # (the lesson has no top-level dict; the manifest surfaces the step order 0/1).
    if levers and levers.get("lesson_goal") and steps:
        steps[0]["lesson_goal"] = levers["lesson_goal"]

    return steps


def _value_warmup_step(
    medium: str,
    classic_by_stem: dict[str, str],
    value_zones_map: str | None,
) -> dict:
    """The order-0 value-study warm-up, shared by the beginner path and the
    profile-driven `force_value_warmup` lever so the two stay identical."""
    warmup_assets: dict[str, str] = {}
    if "notan" in classic_by_stem:
        warmup_assets["notan"] = classic_by_stem["notan"]
    if value_zones_map:
        warmup_assets["values"] = value_zones_map
    return {
        "order":       0,
        "name":        "Warm-up: paint the value study first",
        "description": "Before the real painting, copy the notan study at postcard size using only 3 values. "
                       "Spend no more than 15 minutes. This is a rehearsal, not a painting — throw it away afterwards.",
        "why":         "Every mistake you make in the rehearsal is one you won't make on the real surface. "
                       "Beginners who skip the value study spend the whole painting fighting problems that "
                       "were free to fix at postcard size.",
        "medium":      medium,
        "level":       1,
        "assets":      warmup_assets,
    }


def _adapt_for_skill(
    steps: list[dict],
    skill_level: str,
    medium: str,
    classic_by_stem: dict[str, str],
    value_zones_map: str | None,
    force_value_warmup: bool = False,
) -> list[dict]:
    """
    Adjust the lesson for the student, without renumbering the medium's own
    stage orders — the video chapter/overlay mapping is keyed on those orders,
    so inserted steps use order 0 (before) and 99 (after) instead.

    `force_value_warmup` (set by the adaptive profile when the student's top
    weakness is value_compression) inserts the same order-0 warm-up even for
    non-beginners; it never double-inserts when a warm-up already exists.
    """
    if skill_level == "beginner":
        steps = [_value_warmup_step(medium, classic_by_stem, value_zones_map)] + steps

    elif skill_level == "advanced":
        steps = steps + [{
            "order":       99,
            "name":        "Self-critique pass",
            "description": "Step back for ten minutes, then photograph your painting and upload it for critique. "
                           "Compare the value structure, temperature and edges against the reference before "
                           "deciding the painting is finished.",
            "why":         "At your level the gap is rarely technique — it is the ability to see your own work "
                           "objectively. A measured comparison against the reference catches the adaptation "
                           "errors your eye has already learned to ignore.",
            "medium":      medium,
            "level":       5,
            "assets":      {},
        }]

    if force_value_warmup and not any(s.get("order") == 0 for s in steps):
        steps = [_value_warmup_step(medium, classic_by_stem, value_zones_map)] + steps

    return steps
