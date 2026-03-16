"""
models.py — Pydantic request/response schemas for the PDF QA Extraction Engine.

Strict typing. No optional fields that can silently swallow data.
Compatible with Python 3.9+.
"""

from typing import List, Optional, Literal

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────

class ProcessRequest(BaseModel):
    """Query parameters for /process endpoint (file is multipart)."""
    url: str = Field(..., description="Target URL to scrape for DOM comparison")
    crop_top: float = Field(
        0.0,
        ge=0.0, le=1.0,
        description="Top crop ratio (0.0 = no crop, 0.1 = remove top 10%)"
    )
    crop_bottom: float = Field(
        1.0,
        ge=0.0, le=1.0,
        description="Bottom crop ratio (1.0 = no crop, 0.9 = remove bottom 10%)"
    )
    crop_left: float = Field(
        0.0,
        ge=0.0, le=1.0,
        description="Left crop ratio (0.0 = no crop, 0.1 = remove left 10%)"
    )
    crop_right: float = Field(
        1.0,
        ge=0.0, le=1.0,
        description="Right crop ratio (1.0 = no crop, 0.9 = remove right 10%)"
    )
    page_range_start: int = Field(
        0,
        ge=0,
        description="First page to process (0-indexed, inclusive)"
    )
    page_range_end: int = Field(
        -1,
        description="Last page to process (0-indexed, exclusive). -1 means all pages."
    )


# ─────────────────────────────────────────────
# Preflight
# ─────────────────────────────────────────────

class PreflightResult(BaseModel):
    page_count: int
    has_text_layer: bool = True


# ─────────────────────────────────────────────
# Layout zone
# ─────────────────────────────────────────────

class LayoutZone(BaseModel):
    zone_id: int
    col_count: int
    y_start: float
    y_end: float


# ─────────────────────────────────────────────
# New QA types
# ─────────────────────────────────────────────

class PDFLocation(BaseModel):
    page: Optional[int] = None
    paragraph: Optional[int] = None
    column: Optional[str] = None

class WebLocation(BaseModel):
    section: Optional[str] = None
    selector: Optional[str] = None

class QAIssue(BaseModel):
    id: str
    type: Literal[
        "extra_whitespace",
        "currency_mismatch",
        "missing_word",
        "missing_paragraph",
    ]
    severity: Literal["must_fix", "minor"]
    title: str
    explanation: str
    pdf_snippet: str
    web_snippet: str
    pdf_location: PDFLocation
    web_location: WebLocation
    # Typed diff data — present depending on `type`; absent fields are None.
    space_count: Optional[int] = None           # extra_whitespace
    pdf_symbol: Optional[str] = None            # currency_mismatch
    web_symbol: Optional[str] = None            # currency_mismatch
    numeric_value: Optional[str] = None         # currency_mismatch
    unit: Optional[str] = None                  # currency_mismatch
    missing_tokens: Optional[List[str]] = None  # missing_word
    paragraph_text: Optional[str] = None        # missing_paragraph
    context_before: Optional[str] = None        # extra_whitespace, currency_mismatch, missing_word
    context_after: Optional[str] = None         # extra_whitespace, currency_mismatch, missing_word

class QASummary(BaseModel):
    must_fix: int
    minor: int
    extra_whitespace_count: int
    currency_mismatch_count: int
    missing_word_count: int
    missing_paragraph_count: int

# ─────────────────────────────────────────────
# Job response (final)
# ─────────────────────────────────────────────

class JobResponse(BaseModel):
    status: str  # "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED"
    progress: int = 0
    message: Optional[str] = None
    error: Optional[str] = None

    # QA report fields
    brand: Optional[str] = None
    pdf_source: Optional[str] = None
    web_source: Optional[str] = None
    run_date: Optional[str] = None
    overall: Optional[Literal["needs_fixing", "minor_issues", "all_clear"]] = None
    summary: Optional[QASummary] = None
    issues: Optional[List[QAIssue]] = None


# ─────────────────────────────────────────────
# Job creation response
# ─────────────────────────────────────────────

class JobCreatedResponse(BaseModel):
    job_id: str
    poll_url: str
