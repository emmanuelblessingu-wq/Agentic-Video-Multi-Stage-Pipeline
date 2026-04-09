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
