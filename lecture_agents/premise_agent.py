"""slide_description.json → premise.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from lecture_agents.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

SYSTEM = """You infer the pedagogical premise of a lecture from slide descriptions.
Output strictly valid JSON."""

PROMPT = """From the following slide_descriptions JSON, infer the lecture premise.

Input:
{input_json}

Return JSON with keys:
- thesis: string — central claim or purpose of the session.
- scope: string — what is in/out of scope.
- learning_objectives: array of strings — what a learner should take away.
- intended_audience: string — level and background assumed.
- key_themes: array of strings — major themes in order of importance.
- constraints_for_narration: string — tone/accuracy constraints given the deck.

JSON only, no markdown."""


def run_premise(slide_desc_path: Path, out_path: Path, client: GeminiClient, *, force: bool = False) -> dict:
    if out_path.is_file() and not force:
        return json.loads(out_path.read_text(encoding="utf-8"))
    raw = slide_desc_path.read_text(encoding="utf-8")
    prompt = PROMPT.format(input_json=raw[:200_000])
    data = client.generate_json(prompt, system=SYSTEM)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Wrote %s", out_path)
    return data
