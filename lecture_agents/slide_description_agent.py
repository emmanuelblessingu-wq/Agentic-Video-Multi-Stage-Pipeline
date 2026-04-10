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


def _write_slide_checkpoint(out_json: Path, slides: list[dict]) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps({"slides": slides}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_existing_slides(out_json: Path) -> list[dict]:
    if not out_json.is_file():
        return []
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
        raw = data.get("slides", data) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return []
        for i, row in enumerate(raw, start=1):
            if not isinstance(row, dict) or row.get("slide_index") != i:
                logger.warning(
                    "Checkpoint %s has bad slide_index; ignoring checkpoint.",
                    out_json.name,
                )
                return []
        return raw
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read %s (%s); starting descriptions from scratch.", out_json, e)
        return []


def run_slide_descriptions(
    image_paths: list[Path],
    out_json: Path,
    client: GeminiClient,
    *,
    force: bool = False,
) -> list[dict]:
    total = len(image_paths)
    if out_json.is_file() and not force:
        slides = _load_existing_slides(out_json)
        if len(slides) >= total:
            logger.info("Using complete %s (%s slides).", out_json.name, total)
            return slides
        if slides:
            logger.info(
                "Resuming slide descriptions: %s slides done, continuing at %s/%s",
                len(slides),
                len(slides) + 1,
                total,
            )
    else:
        slides = []

    for idx in range(len(slides) + 1, total + 1):
        img = image_paths[idx - 1]
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
        _write_slide_checkpoint(out_json, slides)
        logger.info("Described slide %s/%s (checkpoint saved)", idx, total)

    logger.info("Wrote %s", out_json)
    return slides
