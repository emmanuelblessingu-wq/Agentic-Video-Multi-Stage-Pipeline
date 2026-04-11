"""Mux PNG + MP3 per slide, then concat to one MP4 with ffmpeg."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from lecture_agents.ffmpeg_paths import ffmpeg_executable

logger = logging.getLogger(__name__)


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd.as_posix() if cwd else None)
    if r.returncode != 0:
        logger.error("ffmpeg stderr: %s", r.stderr)
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, r.stderr)


def mux_slide(image: Path, audio: Path, segment_out: Path) -> None:
    """Still image + audio; `-shortest` ends the segment when audio ends (no long silent tail)."""
    segment_out.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_executable()
    cmd = [
        ff,
        "-y",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-i",
        image.as_posix(),
        "-i",
        audio.as_posix(),
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-shortest",
        segment_out.as_posix(),
    ]
    _run(cmd)


def concat_segments(segment_paths: list[Path], final_mp4: Path, *, cwd: Path) -> None:
    """Join segment MP4s into one playable file.

    Default: **filter_complex concat** (one encode pass) — reliable A/V for all slides;
    concat *demuxer* + re-encode broke playback for some QuickTime/ffmpeg builds.

    Set ``FFMPEG_CONCAT_COPY=1`` for fast stream-copy concat demuxer (only if segments match).
    """
    final_mp4.parent.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_executable()
    use_copy = os.environ.get("FFMPEG_CONCAT_COPY", "").strip() in ("1", "true", "yes")
    if use_copy:
        list_path = cwd / "_concat_list.txt"
        lines: list[str] = []
        for p in segment_paths:
            rel = p.relative_to(cwd)
            lines.append(f"file '{rel.as_posix()}'")
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            _run(
                [
                    ff,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    list_path.as_posix(),
                    "-c",
                    "copy",
                    final_mp4.resolve().as_posix(),
                ],
                cwd=cwd,
            )
        finally:
            list_path.unlink(missing_ok=True)
        return

    n = len(segment_paths)
    if n == 0:
        raise ValueError("No segments to concat.")
    cmd: list[str] = [ff, "-y"]
    resolved = [p.resolve() for p in segment_paths]
    for p in resolved:
        cmd.extend(["-i", p.as_posix()])
    parts = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n))
    filt = f"{parts}concat=n={n}:v=1:a=1[outv][outa]"
    cmd.extend(
        [
            "-filter_complex",
            filt,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-profile:v",
            "main",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            final_mp4.resolve().as_posix(),
        ]
    )
    _run(cmd)
    logger.info("Final concat via filter_complex (%s clips).", n)


def assemble_video(
    image_paths: list[Path],
    audio_paths: list[Path],
    pdf_stem: str,
    project_dir: Path,
) -> Path:
    if len(image_paths) != len(audio_paths):
        raise ValueError("Image and audio counts must match.")
    seg_dir = project_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    for i, (img, aud) in enumerate(zip(image_paths, audio_paths, strict=True), start=1):
        seg = seg_dir / f"part_{i:03d}.mp4"
        mux_slide(img, aud, seg)
        segments.append(seg)
        logger.info("Segment %s", seg.name)
    final_mp4 = project_dir / f"{pdf_stem}.mp4"
    concat_segments(segments, final_mp4, cwd=project_dir)
    logger.info("Wrote %s", final_mp4)
    return final_mp4
