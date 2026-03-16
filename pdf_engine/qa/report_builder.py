"""
report_builder.py — Assemble the final QA report object.

Combines results from all 5 checks into a single report dict
with summary counts, numbered issues, and overall status.
"""

from __future__ import annotations

import datetime
import logging

logger = logging.getLogger(__name__)


def build_report(
    brand_name: str,
    pdf_filename: str,
    url: str,
    all_issues: list[dict],
) -> dict:
    """
    Build the final report dict from all detected issues.

    Args:
        brand_name:  Brand/company name for the report header.
        pdf_filename: Original PDF filename.
        url:         Web URL that was scraped.
        all_issues:  Combined list of issue dicts from all 5 checks.

    Returns:
        Complete report dict ready for JSON serialization.
    """
    # Number issues sequentially
    for i, issue in enumerate(all_issues, 1):
        issue["id"] = f"issue_{i:03d}"

    must_fix_count = sum(1 for i in all_issues if i["severity"] == "must_fix")
    minor_count = len(all_issues) - must_fix_count

    # Determine overall status
    if must_fix_count > 0:
        overall = "needs_fixing"
    elif all_issues:
        overall = "minor_issues"
    else:
        overall = "all_clear"

    report = {
        "brand": brand_name,
        "pdf_source": pdf_filename,
        "web_source": url,
        "run_date": datetime.date.today().isoformat(),
        "overall": overall,
        "summary": {
            "must_fix": must_fix_count,
            "minor": minor_count,
            "extra_whitespace_count": sum(
                1 for i in all_issues if i["type"] == "extra_whitespace"
            ),
            "currency_mismatch_count": sum(
                1 for i in all_issues if i["type"] == "currency_mismatch"
            ),
            "missing_word_count": sum(
                1 for i in all_issues if i["type"] == "missing_word"
            ),
            "missing_paragraph_count": sum(
                1 for i in all_issues if i["type"] == "missing_paragraph"
            ),
        },
        "issues": all_issues,
    }

    logger.info(
        "Report built: %s — %d must-fix, %d minor, overall=%s",
        brand_name, must_fix_count, minor_count, overall,
    )

    return report
