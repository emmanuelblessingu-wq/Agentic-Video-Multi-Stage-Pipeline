"""Text-to-speech: ElevenLabs, optional Gemini TTS, or edge-tts fallback → MP3 per slide."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
from pathlib import Path

from google import genai
from google.genai import types

from lecture_agents.config import PipelineConfig

logger = logging.getLogger(__name__)


def _wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            wav_path.as_posix(),
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "2",
            mp3_path.as_posix(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def synthesize_gemini_tts(text: str, out_mp3: Path, api_key: str, voice_name: str = "Kore") -> None:
    """Gemini native TTS (WAV PCM) → MP3 via ffmpeg."""
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    response = client.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )
    candidates = response.candidates or []
    if not candidates:
        raise RuntimeError("Gemini TTS returned no candidates.")
    parts = candidates[0].content.parts or []
    data = None
    for p in parts:
        if p.inline_data and p.inline_data.data:
            data = p.inline_data.data
            break
    if not data:
        raise RuntimeError("Gemini TTS returned no audio bytes.")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(data)
        wav_path = Path(tmp.name)
    try:
        _wav_to_mp3(wav_path, out_mp3)
    finally:
        wav_path.unlink(missing_ok=True)


def synthesize_elevenlabs(text: str, out_mp3: Path, api_key: str) -> None:
    from elevenlabs.client import ElevenLabs

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    model_id = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    client = ElevenLabs(api_key=api_key)
    audio_iter = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=model_id,
        output_format="mp3_44100_128",
    )
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    with open(out_mp3, "wb") as f:
        for chunk in audio_iter:
            f.write(chunk)


async def _edge_save(text: str, out_mp3: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_mp3.as_posix())


def synthesize_edge(text: str, out_mp3: Path, voice: str | None = None) -> None:
    v = voice or os.environ.get("EDGE_TTS_VOICE", "en-US-GuyNeural")
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_edge_save(text, out_mp3, v))


def pick_engine(cfg: PipelineConfig) -> str:
    pref = cfg.tts_preference
    if pref == "elevenlabs" and cfg.elevenlabs_api_key:
        return "elevenlabs"
    if pref == "gemini":
        return "gemini"
    if pref == "edge":
        return "edge"
    # auto
    if cfg.elevenlabs_api_key:
        return "elevenlabs"
    return "gemini" if cfg.google_api_key else "edge"


def synthesize_slide_audio(
    text: str,
    out_mp3: Path,
    cfg: PipelineConfig,
    *,
    engine: str | None = None,
) -> None:
    eng = engine or pick_engine(cfg)
    if eng == "elevenlabs":
        if not cfg.elevenlabs_api_key:
            raise ValueError("ElevenLabs selected but ELEVENLABS_API_KEY is missing.")
        synthesize_elevenlabs(text, out_mp3, cfg.elevenlabs_api_key)
        return
    if eng == "gemini":
        try:
            synthesize_gemini_tts(
                text,
                out_mp3,
                cfg.google_api_key,
                voice_name=os.environ.get("GEMINI_TTS_VOICE", "Kore"),
            )
            return
        except Exception as e:
            logger.warning("Gemini TTS failed (%s); falling back to edge-tts.", e)
    synthesize_edge(text, out_mp3)


def synthesize_all_slides(
    narrations: list[dict],
    audio_dir: Path,
    cfg: PipelineConfig,
    *,
    engine: str | None = None,
) -> list[Path]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for row in narrations:
        idx = int(row["slide_index"])
        text = (row.get("narration") or "").strip()
        if not text:
            raise ValueError(f"Empty narration for slide {idx}")
        out = audio_dir / f"slide_{idx:03d}.mp3"
        synthesize_slide_audio(text, out, cfg, engine=engine)
        paths.append(out)
        logger.info("TTS slide_%03d.mp3", idx)
    return paths
