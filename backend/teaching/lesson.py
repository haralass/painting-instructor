from __future__ import annotations
import logging
import re

log = logging.getLogger(__name__)

_LEVEL_ASSET_RE = re.compile(r"^level_(\d)_(values|colours|outlines|regions)$")

_GLOBAL_OUTLINE_KEYS = {
    "outlines_primary", "outlines_primary_secondary", "outlines_detailed", "outlines_full",
}


def build_lesson_plan(
    medium_cfg: dict,
    medium: str,
    detail_levels: dict,
    outline_composites: dict,
    value_zones_map: str | None,
    classic_pages: list[str],
    skill_level: str = "intermediate",
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
    for p in classic_pages:
        if not p:
            continue
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        classic_by_stem[stem] = p

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

    return _adapt_for_skill(steps, skill_level, medium, classic_by_stem, value_zones_map)


def _adapt_for_skill(
    steps: list[dict],
    skill_level: str,
    medium: str,
    classic_by_stem: dict[str, str],
    value_zones_map: str | None,
) -> list[dict]:
    """
    Adjust the lesson for the student, without renumbering the medium's own
    stage orders — the video chapter/overlay mapping is keyed on those orders,
    so inserted steps use order 0 (before) and 99 (after) instead.
    """
    if skill_level == "beginner":
        warmup_assets: dict[str, str] = {}
        if "notan" in classic_by_stem:
            warmup_assets["notan"] = classic_by_stem["notan"]
        if value_zones_map:
            warmup_assets["values"] = value_zones_map
        steps = [{
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
        }] + steps

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

    return steps
