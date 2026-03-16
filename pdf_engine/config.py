"""
config.py — All tunable constants for the PDF QA Extraction Engine.

Every magic number lives here. Nothing is hardcoded elsewhere in the pipeline.

NOTE: PDF-level extraction constants (header_y, footer_y, sidebar_x, column
boundaries, etc.) are NOT hardcoded here. They are derived empirically by
the measure.py phase for each PDF individually.
"""

import os

# ─────────────────────────────────────────────
# Boilerplate fingerprinting
# ─────────────────────────────────────────────
BOILERPLATE_PAGE_THRESHOLD: int = 3    # block appearing on 3+ pages = boilerplate

# ─────────────────────────────────────────────
# Comparison — 3-tier engine
# ─────────────────────────────────────────────
MIN_CHUNK_LENGTH_FOR_TIER2: int = 20   # chars, below this skip to Tier 3

TIER2_THRESHOLDS: dict[tuple[int, int], float] = {
    (20, 50):     95.0,
    (50, 200):    97.0,
    (200, 999999): 98.5,
}

# ─────────────────────────────────────────────
# Paragraph detection
# ─────────────────────────────────────────────
PARAGRAPH_GAP_MULTIPLIER: float = 1.5  # gap > median_line_height * this = paragraph break
MAX_NORMAL_LINE_GAP_PX: int = 30       # gaps above this excluded from median calculation

# ─────────────────────────────────────────────
# FastAPI job
# ─────────────────────────────────────────────
JOB_TIMEOUT_SECONDS: int = 300

# ─────────────────────────────────────────────
# Playwright — DOM scraping
# ─────────────────────────────────────────────
PLAYWRIGHT_LOAD_TIMEOUT: int = 10000       # ms
PLAYWRIGHT_SCROLL_STEPS: int = 10
PLAYWRIGHT_SCROLL_PAUSE_MS: int = 300
PLAYWRIGHT_POST_EXPAND_WAIT_MS: int = 500

# ─────────────────────────────────────────────
# Scraper retry policy
# ─────────────────────────────────────────────
SCRAPER_RETRY_COUNT: int = 2
SCRAPER_RETRY_DELAY_S: int = 5

# ─────────────────────────────────────────────
# Redis
# ─────────────────────────────────────────────
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379")
