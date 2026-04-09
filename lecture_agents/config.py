"""Environment and CLI-derived settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    google_api_key: str
    elevenlabs_api_key: str | None
    agent_model: str
    tts_preference: str  # "gemini" | "elevenlabs" | "edge"

    @classmethod
    def from_env(cls) -> "PipelineConfig":
        key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        eleven = os.environ.get("ELEVENLABS_API_KEY") or None
        agent_model = os.environ.get("GEMINI_AGENT_MODEL", "gemini-2.0-flash")
        tts = (os.environ.get("LECTURE_TTS", "auto") or "auto").lower()
        return cls(
            google_api_key=key,
            elevenlabs_api_key=eleven,
            agent_model=agent_model,
            tts_preference=tts,
        )
