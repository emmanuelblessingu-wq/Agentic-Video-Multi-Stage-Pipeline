"""Derive instructor speaking style from transcript → style.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from lecture_agents.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

STYLE_SYSTEM = """You are an expert in discourse analysis and instructional communication.
Given a lecture transcript, extract a structured profile of how the instructor speaks.
Be specific and grounded in the transcript (quote short examples where helpful).
Output must be valid JSON matching the user's schema request exactly."""

STYLE_PROMPT = """Analyze the full lecture transcript below and return a JSON object with these keys:
- tone: string — overall vocal/semantic tone (e.g. conversational, formal, enthusiastic).
- pacing: string — how fast ideas move; use of pauses, digressions, density.
- fillers_and_hedges: array of strings — recurring fillers or hedges if any.
- framing_devices: array of strings — how they introduce, contrast, or summarize ideas.
- vocabulary_register: string — technical vs. plain language balance.
- rhetorical_patterns: array of strings — recurring patterns (rhetorical questions, analogies, lists).
- audience_address: string — how they address the audience (you, we, imperative).
- example_phrases: array of strings — 3–8 short verbatim phrases that exemplify their voice.
- narration_guidance: string — concise instructions for a narrator to imitate this style credibly.

Transcript:
---
{transcript}
---
Return only JSON, no markdown."""


def build_style_json(transcript_path: Path, out_path: Path, client: GeminiClient) -> dict:
    text = transcript_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError(f"Transcript is empty: {transcript_path}")
    prompt = STYLE_PROMPT.format(transcript=text[:120_000])
    data = client.generate_json(prompt, system=STYLE_SYSTEM)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Wrote %s", out_path)
    return data


def load_or_build_style(
    transcript_path: Path,
    style_path: Path,
    client: GeminiClient,
    *,
    force: bool = False,
) -> dict:
    if style_path.is_file() and not force:
        return json.loads(style_path.read_text(encoding="utf-8"))
    return build_style_json(transcript_path, style_path, client)
