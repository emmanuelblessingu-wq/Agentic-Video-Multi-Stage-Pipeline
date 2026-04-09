"""Gemini client for text, vision, and JSON outputs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY is required for AI steps.")
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def generate_json(self, prompt: str, *, system: str | None = None) -> dict:
        """Single-turn JSON response from text only."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=system if system else None,
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        return self._parse_json_response(response)

    def generate_json_with_image(
        self,
        prompt: str,
        image_path: Path,
        *,
        system: str | None = None,
    ) -> dict:
        """JSON response using a slide image + text prompt."""
        data = image_path.read_bytes()
        mime = "image/png"
        parts = [
            types.Part.from_bytes(data=data, mime_type=mime),
            types.Part.from_text(text=prompt),
        ]
        user_content = types.Content(role="user", parts=parts)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=system if system else None,
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=[user_content],
            config=config,
        )
        return self._parse_json_response(response)

    def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=config,
        )
        text = getattr(response, "text", None) or ""
        if not text.strip():
            # Fallback: concatenate parts
            parts = []
            for c in response.candidates or []:
                for p in c.content.parts or []:
                    if p.text:
                        parts.append(p.text)
            text = "\n".join(parts)
        return text.strip()

    @staticmethod
    def _parse_json_response(response) -> dict:
        raw = getattr(response, "text", None) or ""
        if not raw.strip():
            for c in response.candidates or []:
                for p in c.content.parts or []:
                    if p.text:
                        raw = p.text
                        break
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start : end + 1])
            logger.error("Failed to parse JSON from model: %s", raw[:500])
            raise
