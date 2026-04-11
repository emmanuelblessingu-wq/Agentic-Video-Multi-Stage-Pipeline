"""Rasterize each PDF page to a PNG under slide_images/."""

from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def rasterize_pdf(pdf_path: Path, out_dir: Path, zoom: float = 2.0) -> list[Path]:
    """
    Render each page to slide_XXX.png. Returns ordered list of paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(zoom, zoom)
    paths: list[Path] = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            name = f"slide_{i + 1:03d}.png"
            dest = out_dir / name
            pix.save(dest.as_posix())
            paths.append(dest)
            logger.info("Wrote %s", dest.name)
    finally:
        doc.close()
    return paths


def pdf_page_count(pdf_path: Path) -> int:
    doc = fitz.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def load_existing_slide_images(out_dir: Path, pdf_path: Path) -> list[Path]:
    """
    Use slide_001.png … slide_NNN.png already on disk (must match PDF page count).
    For reruns when rasterization is unchanged and you want to skip re-exporting PNGs.
    """
    n = pdf_page_count(pdf_path)
    if not out_dir.is_dir():
        raise FileNotFoundError(f"slide_images directory missing: {out_dir}")
    paths: list[Path] = []
    for i in range(1, n + 1):
        p = out_dir / f"slide_{i:03d}.png"
        if not p.is_file():
            raise FileNotFoundError(
                f"Expected {p.name} for {n}-page PDF; run without --skip-rasterize once, "
                f"or fix slide_images/.",
            )
        paths.append(p)
    logger.info("Using %s existing PNGs in %s (--skip-rasterize)", n, out_dir)
    return paths
