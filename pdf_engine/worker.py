"""
worker.py — ARQ async worker for the PDF QA pipeline.

Uses the PyMuPDF-based extractor (measure → extract) for PDF text,
Playwright-based scraper for web text, and 5 QA checks for comparison.

Writes progress to Redis so the frontend can show a live progress bar.
Implements every error handler from the error table — no silent failures.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import traceback

import fitz  # PyMuPDF
from arq import create_pool
from arq.connections import RedisSettings

from pdf_engine.config import (
    JOB_STATUS_TTL,
    JOB_TIMEOUT_SECONDS,
    REDIS_URL,
)
from pdf_engine.extractor.measure import measure_pdf
from pdf_engine.extractor.extract import extract_pdf
from pdf_engine.qa.web_scraper import scrape_microsite
from pdf_engine.qa.checks import (
    check_extra_whitespace,
    check_currency_mismatch,
    check_missing_words,
    check_missing_paragraphs,
)
from pdf_engine.qa.report_builder import build_report
from pdf_engine.pipeline.preflight import run_preflight
from pdf_engine.pipeline.normalizer import (
    prepare_for_comparison,
    pass_two_filter,
    get_find_text,
    typographic_normalise,
)

logger = logging.getLogger(__name__)


def _parse_redis_url(url: str) -> RedisSettings:
    """Parse a redis:// URL into ARQ RedisSettings (handles auth + host + port)."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
    )


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
    if status in ("COMPLETE", "FAILED"):
        await redis.expire(f"job:{job_id}", JOB_STATUS_TTL)
    await redis.close()


async def run_pipeline(
    ctx: dict,
    job_id: str,
    file_bytes: bytes,
    url: str,
    crop_top: float,
    crop_bottom: float,
    crop_left: float,
    crop_right: float,
    page_start: int,
    page_end: int,
) -> None:
    """
    Full PDF QA pipeline.

    1. Preflight validation
    2. Extract PDF text (measure → extract)
    3. Scrape website (Playwright)
    4. Run all 5 QA checks
    5. Build report and store in Redis

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

        # ── Step 2: Extract PDF text ──
        await set_status(
            job_id, "RUNNING", progress=10,
            message="Extracting PDF text...",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "input.pdf")
            output_dir = os.path.join(tmpdir, "output")
            os.makedirs(output_dir, exist_ok=True)

            with open(pdf_path, "wb") as f:
                f.write(file_bytes)

            try:
                # Phase 1: Measure PDF structure (detect headers, footers, sidebars)
                await set_status(
                    job_id, "RUNNING", progress=15,
                    message="Measuring PDF structure...",
                )
                measurement = measure_pdf(pdf_path)

                # Phase 2: Extract text using crop + measurement report
                await set_status(
                    job_id, "RUNNING", progress=20,
                    message="Extracting PDF text...",
                )
                pdf_ready, pdf_paragraphs = extract_pdf(
                    file_bytes,
                    output_dir,
                    report=measurement,
                    crop_top=crop_top,
                    crop_bottom=crop_bottom,
                    crop_left=crop_left,
                    crop_right=crop_right,
                    page_start=page_start,
                    page_end=page_end,
                )
            except Exception as exc:
                logger.error("PDF extraction failed: %s", exc)
                await set_status(
                    job_id, "FAILED",
                    error=f"EXTRACTION_ERROR: {str(exc)}",
                )
                return

            if not pdf_paragraphs:
                await set_status(
                    job_id, "FAILED",
                    error="EMPTY_OUTPUT: extraction produced no text",
                )
                return

            await set_status(
                job_id, "RUNNING", progress=40,
                message=f"Extracted {len(pdf_paragraphs)} paragraphs from PDF",
            )

        # ── Step 3: Scrape website ──
        await set_status(
            job_id, "RUNNING", progress=45,
            message="Scraping website...",
        )

        try:
            web_ready, web_sections, web_paragraphs = await scrape_microsite(url)
        except ValueError as e:
            await set_status(job_id, "FAILED", error=str(e))
            return
        except Exception as exc:
            logger.error("Scraper failed: %s", exc)
            await set_status(
                job_id, "FAILED",
                error=f"SCRAPER_ERROR: {str(exc)}",
            )
            return

        await set_status(
            job_id, "RUNNING", progress=70,
            message=f"Scraped {len(web_paragraphs)} paragraphs from website",
        )

        # ── Step 4: Pass 1 — prepare text and run all 5 QA checks ──
        await set_status(
            job_id, "RUNNING", progress=75,
            message="Running QA checks...",
        )

        # CRITICAL: Check 1 runs before prepare_for_comparison().
        # Checks 2-5 run after. See comment in Step 4 block below.
        #
        # BEFORE (original, pre-two-pass):
        #   all_issues = run_checks(pdf_ready, web_ready)
        #
        # AFTER (current): see below.

        # BEFORE (previous session):
        #   pdf_p1 = prepare_for_comparison(pdf_ready)
        #   web_p1 = prepare_for_comparison(web_ready)
        #   candidates = check_extra_whitespace(web_p1, ...) + ...
        #
        # AFTER — Check 1 runs on raw web text, Checks 2-5 on prepared text:

        # Check 1 — extra whitespace — runs on raw web text BEFORE
        # prepare_for_comparison(). NFKC converts \u00a0 (nbsp) to a
        # regular space, which is correct for comparison but must not hide
        # real double-space issues in the web source. Running Check 1 on
        # the raw scraped text is architecturally clean and ensures
        # correctness for all current and future space variants.
        whitespace_issues = check_extra_whitespace(web_ready, web_sections)

        # Checks 2-5 run on NFKC + skeleton-prepared text.
        # This eliminates font encoding differences (ligatures, quote
        # variants, cross-script homoglyphs) that would cause false
        # positives, while preserving all real content differences.
        pdf_p1 = prepare_for_comparison(pdf_ready)
        web_p1 = prepare_for_comparison(web_ready)

        candidates = (
            whitespace_issues +
            check_currency_mismatch(pdf_p1, web_p1, web_sections) +
            check_missing_words(pdf_p1, web_p1) +
            check_missing_paragraphs(pdf_p1, web_p1, pdf_paragraphs)
        )

        # Assign candidate IDs for Pass 2 audit trail.
        # build_report() will renumber confirmed issues with final IDs.
        for i, issue in enumerate(candidates, 1):
            issue["id"] = f"candidate_{i:03d}"

        logger.info("Pass 1 found %d candidate issues", len(candidates))

        # ── Step 4b: Pass 2 — filter encoding differences ──
        confirmed: list[dict] = []
        dropped_by_pass_two: list[dict] = []

        for issue in candidates:
            result = pass_two_filter(issue, pdf_p1, web_p1, logger)
            if result is not None:
                confirmed.append(result)
            else:
                # Build audit log entry for every silently dropped issue.
                # Never drop without a structured record.
                find_text = get_find_text(issue) or ""
                find_norm = typographic_normalise(find_text) if find_text else ""
                original_chars   = len(find_text.replace(' ', ''))
                normalised_chars = len(find_norm.replace(' ', ''))
                dropped_by_pass_two.append({
                    "id":         issue.get("id", "unknown"),
                    "type":       issue.get("type"),
                    "find_text":  find_text,
                    "normalised": find_norm,
                    "reason":     "typographic variant found in web text",
                    "char_delta": abs(original_chars - normalised_chars),
                })

        logger.info(
            "Pass 2: %d confirmed issues, %d dropped as encoding differences",
            len(confirmed), len(dropped_by_pass_two),
        )

        await set_status(
            job_id, "RUNNING", progress=90,
            message=(
                f"Found {len(confirmed)} issues "
                f"({len(dropped_by_pass_two)} encoding variants dropped)"
            ),
        )

        # ── Step 5: Build report ──
        # Derive brand from URL hostname
        from urllib.parse import urlparse
        parsed = urlparse(url)
        brand = parsed.hostname or "Unknown"
        brand = brand.replace(".vercel.app", "").replace("-", " ").title()

        pdf_filename = "uploaded.pdf"

        # build_report() receives only confirmed real errors.
        # It assigns final sequential IDs (issue_001, issue_002, …).
        report = build_report(brand, pdf_filename, url, confirmed)

        # Attach the Pass 2 audit log for debugging and encoding profiling.
        report["dropped_by_pass_two"] = dropped_by_pass_two

        # ── Step 6: Store final result ──
        final = {
            "status": "COMPLETE",
            "progress": 100,
            **report,
        }

        redis = await _get_redis()
        await redis.set(f"job:{job_id}", json.dumps(final).encode())
        await redis.expire(f"job:{job_id}", JOB_STATUS_TTL)
        await redis.close()

        logger.info(
            "Job %s complete: %d confirmed issues (%d must_fix, %d minor), "
            "%d dropped by Pass 2",
            job_id,
            len(confirmed),
            report["summary"]["must_fix"],
            report["summary"]["minor"],
            len(dropped_by_pass_two),
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
