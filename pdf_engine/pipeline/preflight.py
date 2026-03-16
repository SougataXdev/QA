"""
pipeline/preflight.py — PDF validation and text layer detection.

Uses PyMuPDF (fitz) for validation. No pdfplumber dependency.
Rejects corrupted PDFs immediately. Detects image-only PDFs (OCR required).
Never partially parses — fail fast, fail loud.
"""

from __future__ import annotations

import io
import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def run_preflight(file_bytes: bytes) -> dict:
    """
    Validate a PDF and check for a native text layer.

    Args:
        file_bytes: Raw PDF file bytes.

    Returns:
        {"page_count": int, "has_text_layer": True}

    Raises:
        ValueError: CORRUPTED_PDF if the file cannot be opened.
        ValueError: NO_TEXT_LAYER if no extractable text found on sampled pages.
    """
    # ── Step 1: Attempt to open ──
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.error("Preflight failed: cannot open PDF — %s", exc)
        raise ValueError("CORRUPTED_PDF") from exc

    with doc:
        page_count = len(doc)

        if page_count == 0:
            logger.error("Preflight failed: PDF has 0 pages")
            raise ValueError("CORRUPTED_PDF")

        # ── Step 2: Sample first 3 pages for text layer ──
        sample_size = min(3, page_count)
        all_empty = True

        for i in range(sample_size):
            page = doc[i]
            try:
                text = page.get_text().strip()
            except Exception as exc:
                logger.warning(
                    "Preflight: get_text failed on page %d — %s", i, exc
                )
                continue

            if text and len(text) > 10:
                all_empty = False
                break

        if all_empty:
            logger.error(
                "Preflight failed: no text layer detected on first %d pages",
                sample_size,
            )
            raise ValueError(
                "NO_TEXT_LAYER — OCR required, not supported in this engine"
            )

        logger.info(
            "Preflight passed: %d pages, text layer confirmed", page_count
        )

        return {"page_count": page_count, "has_text_layer": True}
