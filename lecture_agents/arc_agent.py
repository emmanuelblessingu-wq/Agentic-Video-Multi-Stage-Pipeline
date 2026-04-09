"""premise + slide descriptions → arc.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from lecture_agents.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

SYSTEM = """You design a clear narrative arc for a narrated lecture video.
Output strictly valid JSON."""

PROMPT = """Using the premise and full slide descriptions, define a coherent story arc for narration.

premise.json:
{premise}

slide_description.json:
{slides}

Return JSON with keys:
- overview: string — one paragraph on how the lecture builds.
- phases: array of objects, each with: name (string), slide_range (string e.g. "1-4"), purpose (string), key_ideas (array of strings).
- transitions: array of strings — short bridge phrases between phases (optional hints, not full script).
- buildup_and_payoff: string — how tension or curiosity resolves.
- consistency_notes: string — reminders to stay aligned with premise and slide order.

JSON only."""


def run_arc(
    premise_path: Path,
    slide_desc_path: Path,
    out_path: Path,
    client: GeminiClient,
    *,
    force: bool = False,
) -> dict:
    if out_path.is_file() and not force:
        return json.loads(out_path.read_text(encoding="utf-8"))
    premise = premise_path.read_text(encoding="utf-8")
    slides = slide_desc_path.read_text(encoding="utf-8")
    prompt = PROMPT.format(premise=premise[:80_000], slides=slides[:200_000])
    data = client.generate_json(prompt, system=SYSTEM)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Wrote %s", out_path)
    return data
