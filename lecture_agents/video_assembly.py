"""Mux PNG + MP3 per slide, then concat to one MP4 with ffmpeg."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd.as_posix() if cwd else None)
    if r.returncode != 0:
        logger.error("ffmpeg stderr: %s", r.stderr)
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, r.stderr)


def mux_slide(image: Path, audio: Path, segment_out: Path) -> None:
    """Still image + audio; duration follows audio (-shortest drops silent tail on video loop)."""
    segment_out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
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
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        segment_out.as_posix(),
    ]
    _run(cmd)


def concat_segments(segment_paths: list[Path], final_mp4: Path, *, cwd: Path) -> None:
    """Write concat list with paths relative to cwd so ffmpeg resolves segments reliably."""
    final_mp4.parent.mkdir(parents=True, exist_ok=True)
    list_path = cwd / "_concat_list.txt"
    lines: list[str] = []
    for p in segment_paths:
        rel = p.relative_to(cwd)
        lines.append(f"file '{rel.as_posix()}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_path.as_posix(),
                "-c",
                "copy",
                final_mp4.as_posix(),
            ],
            cwd=cwd,
        )
    finally:
        list_path.unlink(missing_ok=True)


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
