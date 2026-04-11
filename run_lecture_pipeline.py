#!/usr/bin/env python3
"""
Entry point: transcript → style.json; PDF → slide images → descriptions → premise → arc
→ narrations → TTS → ffmpeg → one MP4.

Run from repository root. Requires GOOGLE_API_KEY (or GEMINI_API_KEY). Video/TTS WAV→MP3
need ffmpeg (system PATH or via `pip install imageio-ffmpeg`). Lecture transcript for
style extraction if style.json missing. Place Lecture_17_AI_screenplays.pdf in
the repo root (or pass --pdf).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

from lecture_agents.arc_agent import run_arc
from lecture_agents.config import PipelineConfig
from lecture_agents.gemini_client import GeminiClient
from lecture_agents.narration_agent import run_narrations
from lecture_agents.pdf_rasterize import load_existing_slide_images, rasterize_pdf
from lecture_agents.premise_agent import run_premise
from lecture_agents.slide_description_agent import run_slide_descriptions
from lecture_agents.style_agent import build_style_json, load_or_build_style
from lecture_agents.tts_step import pick_engine, synthesize_all_slides
from lecture_agents.video_assembly import assemble_video

REPO_ROOT = Path(__file__).resolve().parent


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _require_ffmpeg() -> None:
    from lecture_agents.ffmpeg_paths import ffmpeg_executable

    ffmpeg_executable()  # raises with install hints if missing


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lecture PDF → narrated video pipeline.")
    p.add_argument(
        "--pdf",
        type=Path,
        default=REPO_ROOT / "Lecture_17_AI_screenplays.pdf",
        help="Path to slide PDF (default: repo root Lecture_17_AI_screenplays.pdf).",
    )
    p.add_argument(
        "--transcript",
        type=Path,
        default=REPO_ROOT / "Lecture_17_transcript.txt",
        help="Lecture transcript text file for style.json (default: Lecture_17_transcript.txt).",
    )
    p.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Use this existing project folder instead of creating project_YYYYMMDD_HHMMSS.",
    )
    p.add_argument(
        "--tts-engine",
        choices=("auto", "gemini", "elevenlabs", "edge"),
        default=None,
        help="Override LECTURE_TTS / auto detection.",
    )
    p.add_argument("--force-style", action="store_true", help="Regenerate style.json from transcript.")
    p.add_argument("--force-slides", action="store_true", help="Regenerate slide descriptions.")
    p.add_argument("--force-premise", action="store_true")
    p.add_argument("--force-arc", action="store_true")
    p.add_argument("--force-narration", action="store_true")
    p.add_argument("--force-tts", action="store_true", help="Regenerate all slide MP3s.")
    p.add_argument("--skip-video", action="store_true", help="Stop after TTS (no ffmpeg).")
    p.add_argument("--skip-tts", action="store_true", help="Stop after narration JSON.")
    p.add_argument(
        "--skip-rasterize",
        action="store_true",
        help="Do not re-render PDF; require slide_001.png… under project slide_images/ matching PDF page count.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    if load_dotenv is not None:
        load_dotenv(REPO_ROOT / ".env")

    cfg = PipelineConfig.from_env()
    if args.tts_engine:
        cfg.tts_preference = args.tts_engine

    pdf = args.pdf.resolve()
    if not pdf.is_file():
        logging.error("PDF not found: %s", pdf)
        return 1

    style_path = REPO_ROOT / "style.json"
    transcript_path = args.transcript.resolve()

    if args.force_style or not style_path.is_file():
        if not transcript_path.is_file():
            logging.error(
                "Transcript missing (%s). Add it or pass --transcript. "
                "Required to build style.json unless the file already exists.",
                transcript_path,
            )
            return 1
        client = GeminiClient(cfg.google_api_key, cfg.agent_model)
        build_style_json(transcript_path, style_path, client)
    else:
        client = GeminiClient(cfg.google_api_key, cfg.agent_model)
        load_or_build_style(transcript_path, style_path, client, force=False)

    if not style_path.is_file():
        logging.error("style.json missing after style step.")
        return 1

    projects_root = REPO_ROOT / "projects"
    projects_root.mkdir(parents=True, exist_ok=True)

    if args.project_dir is not None:
        project_dir = args.project_dir.resolve()
        project_dir.mkdir(parents=True, exist_ok=True)
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = projects_root / f"project_{stamp}"
        project_dir.mkdir(parents=True, exist_ok=False)

    slide_img_dir = project_dir / "slide_images"
    audio_dir = project_dir / "audio"

    logging.info("Project directory: %s", project_dir)

    try:
        if args.skip_rasterize:
            image_paths = load_existing_slide_images(slide_img_dir, pdf)
        else:
            image_paths = rasterize_pdf(pdf, slide_img_dir)
    except FileNotFoundError as e:
        logging.error("%s", e)
        return 1
    slide_desc_path = project_dir / "slide_description.json"
    run_slide_descriptions(
        image_paths,
        slide_desc_path,
        client,
        force=args.force_slides,
    )

    premise_path = project_dir / "premise.json"
    run_premise(slide_desc_path, premise_path, client, force=args.force_premise)

    arc_path = project_dir / "arc.json"
    run_arc(premise_path, slide_desc_path, arc_path, client, force=args.force_arc)

    narr_path = project_dir / "slide_description_narration.json"
    narrations = run_narrations(
        image_paths,
        slide_desc_path,
        style_path,
        premise_path,
        arc_path,
        narr_path,
        client,
        force=args.force_narration,
    )

    if args.skip_tts:
        logging.info("Skipping TTS and video (--skip-tts).")
        return 0

    if args.force_tts:
        for f in audio_dir.glob("slide_*.mp3"):
            f.unlink(missing_ok=True)

    tts_engine = pick_engine(cfg)
    logging.info("TTS engine: %s", tts_engine)
    synthesize_all_slides(narrations, audio_dir, cfg, engine=tts_engine)

    if args.skip_video:
        logging.info("Skipping video assembly (--skip-video).")
        return 0

    _require_ffmpeg()
    audio_paths = sorted(audio_dir.glob("slide_*.mp3"))
    if len(audio_paths) != len(image_paths):
        logging.error("Expected %s audio files, found %s", len(image_paths), len(audio_paths))
        return 1

    assemble_video(image_paths, audio_paths, pdf.stem, project_dir)
    logging.info("Done. Video: %s", project_dir / f"{pdf.stem}.mp4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
