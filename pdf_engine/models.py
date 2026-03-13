"""
models.py — Pydantic request/response schemas for the PDF QA Extraction Engine.

Strict typing. No optional fields that can silently swallow data.
Compatible with Python 3.9+.
"""

from typing import List, Optional

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
# Comparison result (per-paragraph)
# ─────────────────────────────────────────────

class DiffDetail(BaseModel):
    added: List[str] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    block_id: int
    page: Optional[int] = None
    pdf_text: str
    status: str  # "PASS" | "WARNING" | "FAIL"
    tier: int    # 1, 2, or 3
    score: Optional[float] = None
    diff: Optional[DiffDetail] = None
    flag: Optional[str] = None


# ─────────────────────────────────────────────
# Stitch flag
# ─────────────────────────────────────────────

class StitchFlag(BaseModel):
    type: str
    location: str
    text_fragment: str


# ─────────────────────────────────────────────
# Job summary
# ─────────────────────────────────────────────

class JobSummary(BaseModel):
    total: int
    passed: int
    warnings: int
    failures: int


# ─────────────────────────────────────────────
# Job response (final)
# ─────────────────────────────────────────────

class JobResponse(BaseModel):
    status: str  # "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED"
    progress: int = 0
    message: Optional[str] = None
    error: Optional[str] = None
    summary: Optional[JobSummary] = None
    results: Optional[List[ComparisonResult]] = None
    boilerplate_stripped: Optional[List[str]] = None
    flags: Optional[List[StitchFlag]] = None
    stitch_log: Optional[List[str]] = None


# ─────────────────────────────────────────────
# Job creation response
# ─────────────────────────────────────────────

class JobCreatedResponse(BaseModel):
    job_id: str
    poll_url: str
