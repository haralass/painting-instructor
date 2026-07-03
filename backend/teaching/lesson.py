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
            "medium":      medium,
            "level":       level,
            "assets":      assets,
        })

    return steps
