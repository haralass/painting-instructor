from __future__ import annotations
import base64
import logging
import mimetypes
import os
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("ANTHROPIC_OBSERVATIONS_MODEL", "claude-sonnet-5")

_SYSTEM_PROMPT = (
    "You are a painting instructor giving a student specific, actionable "
    "observations about their own reference photo before they start painting "
    "it. You have already been given the exact palette, value zones, and "
    "region count a classical computer-vision pipeline extracted from this "
    "image — ground your answer in those real numbers and in what you "
    "actually see in the photo. Never give generic textbook advice that "
    "could apply to any photo. Write 3-5 short sentences, plain prose, no "
    "headings or bullet points. Speak directly to the student as 'you'."
)


def _build_user_prompt(
    medium: str,
    medium_cfg: dict,
    palette: list[dict],
    value_zone_list: list[dict],
    region_count: int,
) -> str:
    top_colours = ", ".join(
        f"{c.get('name', '?')} ({c.get('area_fraction', 0) * 100:.0f}%)"
        for c in palette[:5]
    ) or "no dominant colours extracted"
    zones = ", ".join(z.get("label", "") for z in value_zone_list) or "not computed"
    medium_name = medium_cfg.get("name", medium.title())

    return (
        f"Medium: {medium_name}.\n"
        f"Extracted palette (top 5 by area): {top_colours}.\n"
        f"Value zones detected: {zones}.\n"
        f"Region hierarchy found {region_count} distinct regions at the finest level.\n\n"
        "Look at the attached reference photo. Tell the student, specifically for "
        "THIS photo: what the dominant light/shadow story is, which real colour or "
        "shape they should block in first and why, and one concrete risk specific "
        "to this composition (e.g. a busy area that will tempt overworking, or a "
        "value that reads deceptively in the photo vs on canvas)."
    )


def generate_observations(
    reference_path: str,
    medium: str,
    medium_cfg: dict,
    palette: list[dict],
    value_zone_list: list[dict],
    region_count: int,
) -> str | None:
    """
    One Claude vision call that grounds a few sentences of teaching text in
    this specific job's already-computed analysis data (palette/value zones/
    region count) plus the actual reference image — as opposed to every other
    piece of teaching copy in this app, which is a static per-medium template.

    Returns None (never raises) if ANTHROPIC_API_KEY is unset, the client
    library is missing, or the API call fails for any reason — mirroring how
    line_art degrades when its optional ML dependency isn't installed, so a
    missing/broken LLM integration never breaks the rest of the pipeline.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        log.info("generate_observations: ANTHROPIC_API_KEY not set, skipping")
        return None

    try:
        import anthropic
    except ImportError:
        log.warning("generate_observations: anthropic package not installed, skipping")
        return None

    path = Path(reference_path)
    if not path.exists():
        log.warning("generate_observations: reference image %r not found", reference_path)
        return None

    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    image_b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=400,
            system=_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": image_b64},
                    },
                    {
                        "type": "text",
                        "text": _build_user_prompt(medium, medium_cfg, palette, value_zone_list, region_count),
                    },
                ],
            }],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text").strip()
        return text or None
    except Exception:
        log.warning("generate_observations: Claude call failed", exc_info=True)
        return None
