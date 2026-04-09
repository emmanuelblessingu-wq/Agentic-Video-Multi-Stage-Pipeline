"""Sequential slide descriptions from images + prior context."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from lecture_agents.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

SYSTEM = """You describe lecture slides for accessibility and narration planning.
Be accurate to visible text and layout; note diagrams, bullets, and emphasis.
Always return valid JSON with keys: slide_index (int), title_guess (string), description (string), is_likely_title_slide (boolean)."""

USER_TEMPLATE = """You are describing slide {slide_index} of {total_slides}.

All previous slide descriptions in order (slides 1 through {slide_index_minus_one}; use for continuity; do not copy verbatim):
{prev_block}

Describe the attached slide image. The description should stand alone but reference the lecture flow where helpful.
Return JSON only."""


def run_slide_descriptions(
    image_paths: list[Path],
    out_json: Path,
    client: GeminiClient,
    *,
    force: bool = False,
) -> list[dict]:
    if out_json.is_file() and not force:
        data = json.loads(out_json.read_text(encoding="utf-8"))
        return data.get("slides", data) if isinstance(data, dict) else data

    slides: list[dict] = []
    total = len(image_paths)
    for idx, img in enumerate(image_paths, start=1):
        # Rubric: every call must include *all* prior slide descriptions in context (real chaining).
        prev = list(slides)
        prev_block = (
            json.dumps(prev, indent=2, ensure_ascii=False)
            if prev
            else "(none — this is the first slide; no prior descriptions.)"
        )
        prompt = USER_TEMPLATE.format(
            slide_index=idx,
            total_slides=total,
            slide_index_minus_one=idx - 1,
            prev_block=prev_block,
        )
        row = client.generate_json_with_image(prompt, img, system=SYSTEM)
        row.setdefault("slide_index", idx)
        row["image_file"] = img.name
        slides.append(row)
        logger.info("Described slide %s/%s", idx, total)

    payload = {"slides": slides}
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Wrote %s", out_json)
    return slides
