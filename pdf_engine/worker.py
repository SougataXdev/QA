"""
worker.py — ARQ async worker for the PDF QA extraction pipeline.

Uses the PyMuPDF-based extractor (measure → extract) instead of pdfplumber.
The extractor handles column detection, reading order, noise filtering,
and spread layouts internally — no need for external geometry/sorter/stitcher.

Writes progress to Redis so the frontend can show a live progress bar.
Implements every error handler from the error table — no silent failures.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import tempfile
import traceback

import fitz  # PyMuPDF
from arq import create_pool
from arq.connections import RedisSettings

from pdf_engine.config import (
    JOB_TIMEOUT_SECONDS,
    REDIS_URL,
)
from pdf_engine.extractor.measure import measure_pdf
from pdf_engine.extractor.extract import extract_pdf
from pdf_engine.pipeline.comparator import compare
from pdf_engine.pipeline.fingerprint import strip_boilerplate
from pdf_engine.pipeline.normalizer import normalize
from pdf_engine.pipeline.scraper import scrape_dom
from pdf_engine.pipeline.preflight import run_preflight

logger = logging.getLogger(__name__)


def _parse_redis_url(url: str) -> RedisSettings:
    """Parse a redis:// URL into ARQ RedisSettings."""
    url = url.replace("redis://", "")
    parts = url.split(":")
    host = parts[0] if parts[0] else "localhost"
    port = int(parts[1]) if len(parts) > 1 else 6379
    return RedisSettings(host=host, port=port)


async def _get_redis():
    """Get an ARQ redis pool for status updates."""
    return await create_pool(_parse_redis_url(REDIS_URL))


async def set_status(
    job_id: str,
    status: str,
    progress: int = 0,
    message: str | None = None,
    error: str | None = None,
    **extra,
) -> None:
    """Write job status to Redis."""
    redis = await _get_redis()
    data = {
        "status": status,
        "progress": progress,
    }
    if message:
        data["message"] = message
    if error:
        data["error"] = error
    data.update(extra)

    await redis.set(f"job:{job_id}", json.dumps(data).encode())
    await redis.close()


def _extract_text_from_pdf(
    file_bytes: bytes,
    page_start: int,
    page_end: int,
) -> tuple[list[list[str]], list[int], int]:
    """
    Extract text from PDF bytes using (measure → extract) pipeline.

    Writes file_bytes to a temp file (PyMuPDF measure/extract work on paths),
    runs the full extraction, then reads the output .txt and splits by page
    delimiter to produce a list of page-blocks compatible with downstream.

    Returns:
        (all_pages_blocks, skipped_pages, total_pages)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "input.pdf")
        output_dir = os.path.join(tmpdir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # Write bytes to temp file
        with open(pdf_path, "wb") as f:
            f.write(file_bytes)

        # ── Phase 1: Measure ──
        report = measure_pdf(pdf_path)

        # ── Phase 2: Extract ──
        result = extract_pdf(pdf_path, output_dir, report)

        # Read the extracted text
        txt_path = result["output_path"]
        with open(txt_path, "r", encoding="utf-8") as f:
            full_text = f.read()

        # Split by page delimiter to get per-page text
        PAGE_DELIMITER = "\n\n--- Page Break ---\n\n"
        page_texts = full_text.split(PAGE_DELIMITER)

        # Apply page range filter if needed
        total_logical_pages = len(page_texts)

        # For spread layouts, each physical page = 2 logical pages
        # The page_start/page_end are physical page indices (0-based)
        # Our extractor already processes ALL pages, so we slice the result
        if report.is_spread:
            # Physical page N → logical pages 2N and 2N+1
            logical_start = page_start * 2
            logical_end = min(page_end * 2, total_logical_pages)
        else:
            logical_start = page_start
            logical_end = min(page_end, total_logical_pages)

        selected_texts = page_texts[logical_start:logical_end]

        # Convert each page text into a list of paragraphs (blocks)
        # Split on double newlines to approximate paragraph boundaries
        all_pages_blocks: list[list[str]] = []
        for page_text in selected_texts:
            page_text = page_text.strip()
            if not page_text or page_text.startswith("[EMPTY"):
                all_pages_blocks.append([])
                continue

            # Split into paragraphs: blocks separated by blank lines
            raw_paragraphs = page_text.split("\n\n")
            blocks = []
            for para in raw_paragraphs:
                # Join lines within a paragraph into a single block
                cleaned = " ".join(
                    line.strip() for line in para.split("\n") if line.strip()
                )
                if cleaned:
                    blocks.append(cleaned)
            all_pages_blocks.append(blocks)

        skipped = result.get("skipped", [])
        total_pages = result.get("pages", 0)

        return all_pages_blocks, skipped, total_pages


async def run_pipeline(
    ctx: dict,
    job_id: str,
    file_bytes: bytes,
    url: str,
    crop_top: float,
    crop_bottom: float,
    page_start: int,
    page_end: int,
) -> None:
    """
    Full PDF QA extraction pipeline.

    Uses PyMuPDF extractor for text extraction (replaces pdfplumber).
    The downstream comparison pipeline remains unchanged.

    Error handling:
      - CORRUPTED_PDF → 400 + message
      - NO_TEXT_LAYER → 400 + message
      - EMPTY_OUTPUT → extraction produced no text
      - EMPTY_DOM → hard fail job
      - SCRAPER_TIMEOUT → retry ×2, then fail
      - UNEXPECTED_ERROR → catch-all, log traceback, fail
    """
    try:
        await set_status(job_id, "RUNNING", progress=0)

        # ── Step 1: Preflight ──
        try:
            preflight = run_preflight(file_bytes)
        except ValueError as e:
            await set_status(job_id, "FAILED", error=str(e))
            return

        await set_status(job_id, "RUNNING", progress=5, message="Preflight passed")

        # ── Resolve page range ──
        total_doc_pages = preflight["page_count"]
        if page_end == -1 or page_end > total_doc_pages:
            page_end = total_doc_pages

        if page_start >= page_end:
            await set_status(
                job_id, "FAILED",
                error=f"Invalid page range: {page_start}-{page_end}"
            )
            return

        # ── Step 2: PyMuPDF extraction (measure → extract) ──
        await set_status(
            job_id, "RUNNING", progress=10,
            message="Measuring PDF layout...",
        )

        try:
            all_pages_blocks, skipped_pages, total_pages = _extract_text_from_pdf(
                file_bytes, page_start, page_end,
            )
        except Exception as exc:
            logger.error("PDF extraction failed: %s", exc)
            await set_status(
                job_id, "FAILED",
                error=f"EXTRACTION_ERROR: {str(exc)}",
            )
            return

        # Check for empty extraction
        total_blocks = sum(len(page) for page in all_pages_blocks)
        if total_blocks == 0:
            await set_status(
                job_id, "FAILED",
                error="EMPTY_OUTPUT: extraction produced no text blocks",
            )
            return

        await set_status(
            job_id, "RUNNING", progress=55,
            message=f"Extracted {total_blocks} blocks from {len(all_pages_blocks)} pages",
        )

        # ── Step 3: Boilerplate fingerprinting ──
        clean_blocks, boilerplate = strip_boilerplate(all_pages_blocks)
        flat_pdf_text = [p for page_blocks in clean_blocks for p in page_blocks]
        await set_status(
            job_id, "RUNNING", progress=65,
            message="Boilerplate stripped",
        )

        # ── Step 4: Normalize PDF text ──
        flat_pdf_text = [normalize(p) for p in flat_pdf_text]

        # ── Step 5: Scrape DOM ──
        await set_status(
            job_id, "RUNNING", progress=70,
            message="Scraping DOM",
        )
        try:
            dom_text = await scrape_dom(url)
        except ValueError as e:
            await set_status(job_id, "FAILED", error=str(e))
            return

        # ── Step 6: Compare ──
        await set_status(
            job_id, "RUNNING", progress=85,
            message="Running comparison",
        )
        results = compare(flat_pdf_text, dom_text)

        # ── Enrich results with page numbers ──
        block_cursor = 0
        for page_idx, page_blocks in enumerate(clean_blocks):
            for _ in page_blocks:
                if block_cursor < len(results):
                    results[block_cursor]["page"] = page_start + page_idx + 1
                block_cursor += 1

        # ── Step 7: Build final response ──
        final = {
            "status": "COMPLETE",
            "progress": 100,
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r["status"] == "PASS"),
                "warnings": sum(1 for r in results if r["status"] == "WARNING"),
                "failures": sum(1 for r in results if r["status"] == "FAIL"),
            },
            "results": results,
            "boilerplate_stripped": boilerplate,
            "flags": [],
            "stitch_log": [],
        }

        if skipped_pages:
            final["skipped_pages"] = skipped_pages

        redis = await _get_redis()
        await redis.set(f"job:{job_id}", json.dumps(final).encode())
        await redis.close()

        logger.info(
            "Job %s complete: %d blocks, %d passed, %d warnings, %d failures",
            job_id,
            final["summary"]["total"],
            final["summary"]["passed"],
            final["summary"]["warnings"],
            final["summary"]["failures"],
        )

    except ValueError as e:
        await set_status(job_id, "FAILED", error=str(e))
    except Exception as e:
        logger.error("UNEXPECTED_ERROR in job %s:\n%s", job_id, traceback.format_exc())
        await set_status(
            job_id, "FAILED",
            error=f"UNEXPECTED_ERROR: {str(e)}",
        )


class WorkerSettings:
    """ARQ worker settings."""
    functions = [run_pipeline]
    redis_settings = _parse_redis_url(REDIS_URL)
    job_timeout = JOB_TIMEOUT_SECONDS
