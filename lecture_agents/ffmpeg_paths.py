"""Resolve ffmpeg executable: system PATH, then imageio-ffmpeg wheel binary."""

from __future__ import annotations

import logging
import shutil
from functools import lru_cache

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def ffmpeg_executable() -> str:
    """
    Return path to ffmpeg. Uses `shutil.which('ffmpeg')` first, then the
    bundled binary from the `imageio-ffmpeg` package (no Homebrew required).
    """
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        logger.info("Using ffmpeg from imageio-ffmpeg: %s", exe)
        return exe
    except ImportError as e:
        raise RuntimeError(
            "ffmpeg not found on PATH and imageio-ffmpeg is not installed. "
            "Install Homebrew ffmpeg (`brew install ffmpeg`) or run "
            "`pip install imageio-ffmpeg` to use a bundled binary.",
        ) from e
