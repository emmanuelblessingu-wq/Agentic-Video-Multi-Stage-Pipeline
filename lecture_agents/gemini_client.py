"""Gemini client for text, vision, and JSON outputs."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

logger = logging.getLogger(__name__)

# Transient overload / rate / gateway issues (e.g. 503 UNAVAILABLE).
_RETRYABLE_HTTP = frozenset({408, 429, 500, 502, 503, 504})


class GeminiClient:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY is required for AI steps.")
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def _generate_with_retry(self, **kwargs):
        max_attempts = max(1, int(os.environ.get("GEMINI_MAX_RETRIES", "12")))
        base_sec = float(os.environ.get("GEMINI_RETRY_BASE_SEC", "4"))
        last_err: BaseException | None = None
        for attempt in range(max_attempts):
            try:
                return self._client.models.generate_content(**kwargs)
            except genai_errors.APIError as e:
                last_err = e
                if e.code not in _RETRYABLE_HTTP or attempt >= max_attempts - 1:
                    raise
                delay = min(120.0, base_sec * (2**attempt))
                logger.warning(
                    "Gemini HTTP %s (%s); waiting %.0fs then retry %s/%s",
                    e.code,
                    (e.message or str(e))[:120],
                    delay,
                    attempt + 2,
                    max_attempts,
                )
                time.sleep(delay)
        assert last_err is not None
        raise last_err

    def generate_json(self, prompt: str, *, system: str | None = None) -> dict:
        """Single-turn JSON response from text only."""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            system_instruction=system if system else None,
        )
        response = self._generate_with_retry(
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
        response = self._generate_with_retry(
            model=self._model,
            contents=[user_content],
            config=config,
        )
        return self._parse_json_response(response)

    def generate_text(self, prompt: str, *, system: str | None = None) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system if system else None,
        )
        response = self._generate_with_retry(
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
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(raw[start : end + 1])
            else:
                logger.error("Failed to parse JSON from model: %s", raw[:500])
                raise
        return GeminiClient._coerce_json_to_dict(parsed)

    @staticmethod
    def _coerce_json_to_dict(parsed: object) -> dict:
        """Gemini sometimes returns a one-element JSON array instead of an object."""
        if isinstance(parsed, dict):
            slides = parsed.get("slides")
            if (
                len(parsed) == 1
                and isinstance(slides, list)
                and len(slides) == 1
                and isinstance(slides[0], dict)
            ):
                # Model wrapped the slide row as {"slides": [{...}]}
                return slides[0]
            return parsed
        if isinstance(parsed, list):
            if not parsed:
                raise ValueError("Model returned an empty JSON array.")
            if not isinstance(parsed[0], dict):
                raise ValueError(
                    f"Model JSON array must contain objects; got {type(parsed[0]).__name__}.",
                )
            if len(parsed) > 1:
                logger.warning(
                    "Model returned a JSON array with %s elements; using the first object.",
                    len(parsed),
                )
            return parsed[0]
        raise ValueError(f"Expected JSON object or [...] object list; got {type(parsed).__name__}.")
