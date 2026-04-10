"""Per-slide narration using image + style + premise + arc + prior narrations."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from lecture_agents.gemini_client import GeminiClient

logger = logging.getLogger(__name__)


def _pause_between_slides() -> None:
    raw = os.environ.get("GEMINI_PAUSE_BETWEEN_SLIDES_SEC", "0") or "0"
    try:
        sec = float(raw)
    except ValueError:
        return
    if sec > 0:
        time.sleep(sec)


SYSTEM = """You write spoken lecture narration for a single slide.
Match the instructor style profile, premise, and arc. Be natural for text-to-speech: avoid markdown, avoid excessive abbreviations, use commas for short pauses.
Return valid JSON with keys: slide_index (int), narration (string), is_title_slide (boolean)."""

USER_TEMPLATE = """Context (do not read JSON keys aloud — use them to shape speech):

style.json:
{style}

premise.json:
{premise}

arc.json:
{arc}

slide_description.json (full deck):
{slide_descriptions}

All prior slide narrations in order (none on slide 1; continue smoothly and avoid contradicting earlier lines):
{prior_narrations}

Now write narration for slide {slide_index} only. Image attached.

Rules:
- Length: roughly {target_words} words (flexible), one spoken paragraph unless bullets require short list.
- If this is the title slide (slide 1 or is_likely_title_slide was true in description): the speaker introduces themselves with a plausible instructor name and role, then gives a short summary of the lecture topic. Keep it brief and welcoming.
- Otherwise: explain this slide in the instructor's voice; connect briefly to the previous slide when helpful.
- Do not say "this slide shows" repeatedly; vary phrasing.

Current slide description entry:
{current_slide_json}

Return JSON only."""


def _load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_narration_checkpoint(out_path: Path, narrations: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"slides": narrations}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_existing_narrations(out_path: Path) -> list[dict]:
    if not out_path.is_file():
        return []
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        raw = data.get("slides", data) if isinstance(data, dict) else data
        if not isinstance(raw, list):
            return []
        for i, row in enumerate(raw, start=1):
            if not isinstance(row, dict) or row.get("slide_index") != i:
                logger.warning(
                    "Checkpoint %s has bad slide_index; ignoring checkpoint.",
                    out_path.name,
                )
                return []
        return raw
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read %s (%s); starting narrations from scratch.", out_path, e)
        return []


def run_narrations(
    image_paths: list[Path],
    slide_desc_path: Path,
    style_path: Path,
    premise_path: Path,
    arc_path: Path,
    out_path: Path,
    client: GeminiClient,
    *,
    force: bool = False,
) -> list[dict]:
    total = len(image_paths)
    if out_path.is_file() and not force:
        narrations = _load_existing_narrations(out_path)
        if len(narrations) >= total:
            logger.info("Using complete %s (%s slides).", out_path.name, total)
            return narrations
        if narrations:
            logger.info(
                "Resuming narrations: %s slides done, continuing at %s/%s",
                len(narrations),
                len(narrations) + 1,
                total,
            )
    else:
        narrations = []

    style_s = style_path.read_text(encoding="utf-8")
    premise_s = premise_path.read_text(encoding="utf-8")
    arc_s = arc_path.read_text(encoding="utf-8")
    slide_blob = slide_desc_path.read_text(encoding="utf-8")
    sd = _load_json(slide_desc_path)
    slide_list = sd["slides"] if isinstance(sd, dict) and "slides" in sd else sd
    if not isinstance(slide_list, list):
        slide_list = []

    for idx in range(len(narrations) + 1, total + 1):
        img = image_paths[idx - 1]
        current = next((s for s in slide_list if s.get("slide_index") == idx), None)
        if current is None and idx - 1 < len(slide_list):
            current = slide_list[idx - 1]
        current_json = json.dumps(current or {"slide_index": idx}, indent=2, ensure_ascii=False)
        # Rubric: include every prior narration in context (none for slide 1).
        prior = [{"slide_index": n["slide_index"], "narration": n.get("narration", "")} for n in narrations]
        prior_block = (
            json.dumps(prior, indent=2, ensure_ascii=False)
            if prior
            else "(none — slide 1; no prior narrations.)"
        )
        target_words = 55 if idx == 1 else 85
        prompt = USER_TEMPLATE.format(
            style=style_s[:40_000],
            premise=premise_s[:40_000],
            arc=arc_s[:40_000],
            slide_descriptions=slide_blob[:200_000],
            prior_narrations=prior_block,
            slide_index=idx,
            target_words=target_words,
            current_slide_json=current_json,
        )
        row = client.generate_json_with_image(prompt, img, system=SYSTEM)
        row.setdefault("slide_index", idx)
        row["image_file"] = img.name
        desc_text = (current or {}).get("description") if isinstance(current, dict) else None
        row["slide_description"] = desc_text or ""
        narrations.append(row)
        _write_narration_checkpoint(out_path, narrations)
        logger.info("Narration slide %s/%s (checkpoint saved)", idx, total)
        _pause_between_slides()

    logger.info("Wrote %s", out_path)
    return narrations
