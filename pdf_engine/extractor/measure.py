"""
Phase 1 — Measure every PDF before extracting anything.

Opens each PDF, runs diagnostics on every page, and builds a
MeasurementReport dict of empirical constants. These constants
drive Phase 2 — nothing is hardcoded.

Library: PyMuPDF (fitz) only.

Key design decision:
  Some PDFs store text in span["chars"] rather than span["text"].
  We always try span["text"] first, then fall back to reconstructing
  from the chars array. This handles both encodings transparently.
"""

from __future__ import annotations

import os
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data class for per-file measurement results
# ──────────────────────────────────────────────

@dataclass
class MeasurementReport:
    """Empirical measurements for a single PDF file."""
    filepath: str
    page_count: int = 0

    # Page geometry
    page_width: float = 0.0
    page_height: float = 0.0
    has_rotation: bool = False
    rotated_pages: list[int] = field(default_factory=list)
    is_spread: bool = False
    mid_x: float | None = None

    # Text layer
    is_digital: bool = True
    non_digital_pages: list[int] = field(default_factory=list)
    uses_chars_encoding: bool = False  # True = text lives in chars[], not span.text

    # Header / footer zones (y-coordinates)
    header_y: float = 0.0         # deepest repeating y in top zone
    footer_y: float = 0.0         # highest repeating y in bottom zone
    header_strings: list[str] = field(default_factory=list)
    footer_strings: list[str] = field(default_factory=list)

    # Sidebar
    has_sidebar: bool = False
    sidebar_x: float = 0.0        # x threshold for sidebar noise
    sidebar_strings: list[str] = field(default_factory=list)

    # Fonts
    font_roles: dict = field(default_factory=dict)  # font → {sizes, count, role}
    font_size_min: float = 72.0
    font_size_max: float = 0.0

    # Noise
    min_content_size: float = 8.0   # smallest font size of real content
    decorative_threshold: float = 8.0

    # Column layout
    column_count: int = 1

    def to_constants(self) -> dict:
        """Derive extraction constants from measurements."""
        return {
            "HEADER_Y": round(self.header_y, 1),
            "FOOTER_Y": round(self.footer_y, 1),
            "SIDEBAR_X": round(self.sidebar_x, 1),
            "MID_X": round(self.mid_x, 1) if self.mid_x else None,
            "MIN_FONT": round(self.decorative_threshold, 1),
            "LINE_BUCKET": 6,
            "PAGE_WIDTH": round(self.page_width, 1),
            "PAGE_HEIGHT": round(self.page_height, 1),
            "IS_SPREAD": self.is_spread,
            "COLUMN_COUNT": self.column_count,
            "USES_CHARS": self.uses_chars_encoding,
            "HAS_ROTATION": self.has_rotation,
        }


# ──────────────────────────────────────────────
# Core span extraction — handles both text and chars encodings
# ──────────────────────────────────────────────

def _extract_span_text(span: dict) -> str:
    """
    Extract text from a span, handling both encoding styles:
      1. Normal: span["text"] has the content.
      2. chars-only: span["text"] is empty, but span["chars"] has per-char dicts.
    """
    text = span.get("text", "").strip()
    if text:
        return text

    # Fallback: reconstruct from chars array
    chars = span.get("chars", [])
    if chars:
        return "".join(ch.get("c", "") for ch in chars).strip()

    return ""


def _collect_spans(page: fitz.Page, clip: fitz.Rect | None = None) -> list[dict]:
    """
    Extract all text spans from a page using rawdict mode.
    Handles both standard text encoding and chars-only encoding.
    Returns flat list of span dicts.
    """
    kwargs: dict = {}
    if clip:
        kwargs["clip"] = clip
    raw = page.get_text("rawdict", **kwargs)

    spans = []
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:  # text blocks only
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = _extract_span_text(span)
                if not text:
                    continue
                spans.append({
                    "text": text,
                    "x0": span["bbox"][0],
                    "y0": span["bbox"][1],
                    "x1": span["bbox"][2],
                    "y1": span["bbox"][3],
                    "size": span.get("size", 0),
                    "font": span.get("font", ""),
                    "flags": span.get("flags", 0),
                    "color": span.get("color", 0),
                })
    return spans


def _detect_chars_encoding(page: fitz.Page) -> bool:
    """
    Check whether this PDF stores text in the chars array
    instead of span["text"]. Sample the first text block.
    """
    raw = page.get_text("rawdict")
    for block in raw.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                chars = span.get("chars", [])
                if chars and not text:
                    return True
                if text:
                    return False
    return False


# ──────────────────────────────────────────────
# Noise detection
# ──────────────────────────────────────────────

def _detect_header_footer(
    all_pages_spans: list[list[dict]],
    page_width: float,
    page_height: float,
) -> tuple[float, float, list[str], list[str]]:
    """
    Detect header/footer Y boundaries by finding repeating text
    in the top/bottom zones across multiple pages.

    IMPORTANT: Excludes text positioned at extreme right x-coordinates
    (sidebar tabs) from header zone calculations, as these would falsely
    inflate the header boundary.

    Returns: (header_y, footer_y, header_strings, footer_strings)
    """
    top_zone = page_height * 0.12
    bottom_zone = page_height * 0.88
    sidebar_exclusion_x = page_width * 0.85  # Exclude sidebar-positioned text

    top_text_counter: Counter[str] = Counter()
    bottom_text_counter: Counter[str] = Counter()
    top_y_per_text: dict[str, float] = {}
    bottom_y_per_text: dict[str, float] = {}

    for page_spans in all_pages_spans:
        seen_top: set[str] = set()
        seen_bottom: set[str] = set()
        for s in page_spans:
            txt = s["text"].strip()
            if not txt:
                continue

            # Header zone: exclude sidebar-positioned text (high x0)
            if s["y0"] < top_zone and s["x0"] < sidebar_exclusion_x and txt not in seen_top:
                seen_top.add(txt)
                top_text_counter[txt] += 1
                # Track the deepest (largest) y1 for this text
                if txt not in top_y_per_text or s["y1"] > top_y_per_text[txt]:
                    top_y_per_text[txt] = s["y1"]

            if s["y1"] > bottom_zone and txt not in seen_bottom:
                seen_bottom.add(txt)
                bottom_text_counter[txt] += 1
                # Track the shallowest (smallest) y0 for this text
                if txt not in bottom_y_per_text or s["y0"] < bottom_y_per_text[txt]:
                    bottom_y_per_text[txt] = s["y0"]

    num_pages = len(all_pages_spans)
    min_repeat = max(2, num_pages // 2)

    # Header: find the deepest y1 among repeating top-zone strings
    header_y = 0.0
    header_strings: list[str] = []
    for txt, count in top_text_counter.most_common():
        if count >= min_repeat:
            header_strings.append(txt)
            y1 = top_y_per_text.get(txt, 0.0)
            if y1 > header_y:
                header_y = y1

    # Footer: find the shallowest y0 among repeating bottom-zone strings
    footer_y = page_height
    footer_strings: list[str] = []
    for txt, count in bottom_text_counter.most_common():
        if count >= min_repeat:
            footer_strings.append(txt)
            y0 = bottom_y_per_text.get(txt, page_height)
            if y0 < footer_y:
                footer_y = y0

    # Add buffer: 5pt below header, 5pt above footer
    header_y_clipped = header_y + 5.0
    footer_y_clipped = footer_y - 5.0

    return header_y_clipped, footer_y_clipped, header_strings, footer_strings


def _detect_sidebar(
    all_pages_spans: list[list[dict]],
    page_width: float,
    header_y: float,
    footer_y: float,
) -> tuple[bool, float, list[str]]:
    """
    Detect sidebar tabs (text at extreme right x positions that repeats).

    IMPORTANT: We detect sidebar strings for post-filtering, but we do NOT
    set sidebar_x below the page width if body content columns extend near
    the sidebar zone. This avoids clipping real content.

    Returns: (has_sidebar, sidebar_x_threshold, sidebar_strings).
    """
    right_zone = page_width * 0.85
    right_text_counter: Counter[str] = Counter()
    right_x_per_text: dict[str, float] = {}

    for page_spans in all_pages_spans:
        seen: set[str] = set()
        for s in page_spans:
            if s["x0"] > right_zone:
                txt = s["text"].strip()
                if txt and txt not in seen:
                    seen.add(txt)
                    right_text_counter[txt] += 1
                    if txt not in right_x_per_text or s["x0"] < right_x_per_text[txt]:
                        right_x_per_text[txt] = s["x0"]

    num_pages = len(all_pages_spans)
    min_repeat = max(2, num_pages // 2)

    sidebar_strings: list[str] = []
    sidebar_min_x = page_width

    for txt, count in right_text_counter.most_common():
        if count >= min_repeat:
            sidebar_strings.append(txt)
            x0 = right_x_per_text.get(txt, page_width)
            if x0 < sidebar_min_x:
                sidebar_min_x = x0

    has_sidebar = len(sidebar_strings) > 0

    # Check if body content extends near the sidebar zone.
    # If yes, do NOT clip — instead, sidebar noise will be post-filtered.
    body_max_x1 = 0.0
    for page_spans in all_pages_spans:
        for s in page_spans:
            # Only check body-zone spans (not in header/footer)
            if s["y0"] >= header_y and s["y1"] <= footer_y:
                if s["x1"] > body_max_x1:
                    body_max_x1 = s["x1"]

    if has_sidebar and body_max_x1 > (sidebar_min_x - 20):
        # Body content overlaps sidebar zone — don't clip x, use post-filter
        logger.info(
            "Body content extends to x1=%.1f, near sidebar at x0=%.1f. "
            "Using post-filter instead of x-clip.",
            body_max_x1, sidebar_min_x,
        )
        sidebar_x = page_width  # Don't clip
    elif has_sidebar:
        sidebar_x = sidebar_min_x - 5.0
    else:
        sidebar_x = page_width

    return has_sidebar, sidebar_x, sidebar_strings


def _detect_spread(
    all_pages_spans: list[list[dict]],
    page_width: float,
    page_height: float,
) -> tuple[bool, float | None]:
    """
    Detect spread layout by checking if the page is landscape
    AND content appears on both halves.
    """
    if page_width <= page_height:
        return False, None

    mid_x = page_width / 2
    left_total = 0
    right_total = 0

    for page_spans in all_pages_spans:
        for s in page_spans:
            center = (s["x0"] + s["x1"]) / 2
            if center < mid_x:
                left_total += 1
            else:
                right_total += 1

    # Both halves should have at least 10% of content each
    total = left_total + right_total
    if total == 0:
        return False, None

    left_pct = left_total / total
    right_pct = right_total / total

    is_spread = left_pct > 0.10 and right_pct > 0.10
    return is_spread, mid_x if is_spread else None


def _detect_columns(
    all_pages_spans: list[list[dict]],
    page_width: float,
    header_y: float,
    footer_y: float,
    sidebar_x: float,
    band_width: float = 80.0,
) -> int:
    """
    Detect column count by bucketing body-text x0 positions
    into fixed-width bands and counting peaks.
    """
    histogram: Counter[int] = Counter()

    for page_spans in all_pages_spans:
        for s in page_spans:
            # Only count body-zone spans within sidebar bounds
            if s["y0"] < header_y or s["y1"] > footer_y:
                continue
            if s["x0"] > sidebar_x:
                continue
            if s["size"] < 8:
                continue
            bucket = int(s["x0"] / band_width)
            histogram[bucket] += 1

    if not histogram:
        return 1

    max_count = max(histogram.values())
    threshold = max_count * 0.15
    num_buckets = int(page_width / band_width) + 1

    peaks = []
    for b in range(num_buckets):
        count = histogram.get(b, 0)
        if count > threshold:
            left = histogram.get(b - 1, 0)
            right = histogram.get(b + 1, 0)
            if count >= left and count >= right:
                peaks.append(b)

    # Merge adjacent peaks (within 1 bucket)
    merged_peaks = []
    for p in sorted(peaks):
        if merged_peaks and p - merged_peaks[-1] <= 1:
            continue
        merged_peaks.append(p)

    # Cap at reasonable column count
    col_count = max(1, min(len(merged_peaks), 6))
    return col_count


def _analyse_fonts(
    all_pages_spans: list[list[dict]],
) -> tuple[dict, float, float, float]:
    """
    Analyse fonts and determine size thresholds.
    Returns: (font_roles, min_size, max_size, decorative_threshold)
    """
    font_data: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "sizes": set(), "samples": []}
    )
    size_counter: Counter[float] = Counter()

    for page_spans in all_pages_spans:
        for s in page_spans:
            fd = font_data[s["font"]]
            fd["count"] += 1
            fd["sizes"].add(round(s["size"], 1))
            if len(fd["samples"]) < 3:
                fd["samples"].append(s["text"][:40])
            size_counter[round(s["size"], 1)] += 1

    # Find the most common body text size
    if not size_counter:
        return {}, 0.0, 0.0, 8.0

    body_size = size_counter.most_common(1)[0][0]

    # All unique sizes sorted
    all_sizes = sorted(size_counter.keys())
    min_size = all_sizes[0] if all_sizes else 0.0
    max_size = all_sizes[-1] if all_sizes else 0.0

    # Decorative threshold: anything significantly below body text size
    # Use the smallest size that has substantial usage (> 5 spans)
    real_sizes = [s for s, c in size_counter.items() if c >= 5]
    if real_sizes:
        min_real = min(real_sizes)
        decorative_threshold = min_real - 0.5
    else:
        decorative_threshold = body_size - 1.0

    # Assign roles
    font_roles = {}
    for font_name, fd in font_data.items():
        sizes = sorted(fd["sizes"])
        font_roles[font_name] = {
            "count": fd["count"],
            "sizes": sizes,
            "samples": fd["samples"],
        }

    return dict(font_roles), min_size, max_size, max(0, decorative_threshold)


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def measure_pdf(pdf_path: str) -> MeasurementReport:
    """
    Run full diagnostics on a single PDF file.
    Returns a MeasurementReport with all empirical constants.
    """
    report = MeasurementReport(filepath=pdf_path)

    doc = fitz.open(pdf_path)
    report.page_count = len(doc)

    if report.page_count == 0:
        logger.warning("PDF has 0 pages: %s", pdf_path)
        doc.close()
        return report

    # ── Page dimensions (from first page) ──
    first_page = doc[0]
    report.page_width = first_page.rect.width
    report.page_height = first_page.rect.height

    # ── Rotation check ──
    rotated = []
    for pn in range(report.page_count):
        rot = doc[pn].rotation
        if rot != 0:
            rotated.append(pn + 1)
    report.has_rotation = len(rotated) > 0
    report.rotated_pages = rotated

    # ── Check text encoding (chars vs text) ──
    report.uses_chars_encoding = _detect_chars_encoding(first_page)
    if report.uses_chars_encoding:
        logger.info("PDF uses chars-only encoding: %s", pdf_path)

    # ── Collect spans from all pages ──
    all_pages_spans: list[list[dict]] = []

    for page_num in range(report.page_count):
        page = doc[page_num]

        # Handle rotation
        if page.rotation != 0:
            page.remove_rotation()

        # Text layer check
        plain = page.get_text().strip()
        if len(plain) < 50:
            report.non_digital_pages.append(page_num + 1)
            all_pages_spans.append([])
            logger.warning(
                "Page %d has < 50 chars of text: possibly non-digital", page_num + 1
            )
            continue

        spans = _collect_spans(page)

        if not spans and len(plain) > 50:
            # Spans extraction failed despite text existing — log this
            xobjects = page.get_xobjects()
            logger.warning(
                "Page %d: rawdict returned 0 spans despite %d chars in get_text(). "
                "XObjects: %d. Rotation: %d",
                page_num + 1, len(plain), len(xobjects), page.rotation,
            )

        all_pages_spans.append(spans)

    report.is_digital = len(report.non_digital_pages) == 0

    # ── Spread detection ──
    is_spread, mid_x = _detect_spread(
        all_pages_spans, report.page_width, report.page_height,
    )
    report.is_spread = is_spread
    report.mid_x = mid_x

    # ── Header / Footer detection ──
    header_y, footer_y, header_strings, footer_strings = _detect_header_footer(
        all_pages_spans, report.page_width, report.page_height,
    )
    report.header_y = header_y
    report.footer_y = footer_y
    report.header_strings = header_strings
    report.footer_strings = footer_strings

    # ── Sidebar detection ──
    has_sidebar, sidebar_x, sidebar_strings = _detect_sidebar(
        all_pages_spans, report.page_width, header_y, footer_y,
    )
    report.has_sidebar = has_sidebar
    report.sidebar_x = sidebar_x
    report.sidebar_strings = sidebar_strings

    # ── Font analysis ──
    font_roles, size_min, size_max, decorative_threshold = _analyse_fonts(
        all_pages_spans,
    )
    report.font_roles = font_roles
    report.font_size_min = size_min
    report.font_size_max = size_max
    report.min_content_size = decorative_threshold + 0.5
    report.decorative_threshold = decorative_threshold

    # ── Column detection ──
    report.column_count = _detect_columns(
        all_pages_spans,
        report.page_width,
        header_y,
        footer_y,
        sidebar_x,
    )

    doc.close()
    return report


def print_measurement_report(report: MeasurementReport) -> None:
    """Print a human-readable measurement report to stdout."""
    constants = report.to_constants()
    filename = os.path.basename(report.filepath)

    print("\n" + "═" * 64)
    print(f"  MEASUREMENT REPORT: {filename}")
    print("═" * 64)

    print(f"\n  Page dimensions     {report.page_width:.1f} × {report.page_height:.1f} pt")
    print(f"  Page count          {report.page_count}")
    print(f"  Rotation            {'⚠ Pages ' + str(report.rotated_pages) if report.has_rotation else '✓ None'}")
    print(f"  Is spread layout?   {'YES (landscape + two-sided content)' if report.is_spread else 'NO'}")
    if report.mid_x:
        print(f"  Spread midpoint     MID_X = {report.mid_x:.1f}")
    print(f"  Text layer          {'✓ DIGITAL' if report.is_digital else '⚠ MIXED'}")
    if report.non_digital_pages:
        print(f"                      Non-digital pages: {report.non_digital_pages}")
    print(f"  Text encoding       {'chars[] reconstruction' if report.uses_chars_encoding else 'standard span.text'}")

    print(f"\n  Header zone         y ≤ {report.header_y:.1f}")
    if report.header_strings:
        for hs in report.header_strings[:5]:
            print(f"                        → '{hs}'")
    print(f"  Footer zone         y ≥ {report.footer_y:.1f}")
    if report.footer_strings:
        for fs in report.footer_strings[:5]:
            print(f"                        → '{fs}'")
    print(f"  Sidebar             {'⚠ DETECTED at x > ' + str(round(report.sidebar_x, 1)) if report.has_sidebar else '✓ None'}")
    if report.sidebar_strings:
        for ss in report.sidebar_strings[:5]:
            print(f"                        → '{ss}'")

    print(f"\n  Fonts present       {len(report.font_roles)} unique")
    for fn, fd in sorted(report.font_roles.items()):
        sizes_str = ", ".join(str(s) for s in fd["sizes"])
        print(f"                        • {fn} ({fd['count']} spans, sizes: {sizes_str})")
    print(f"  Font size range     {report.font_size_min:.1f} – {report.font_size_max:.1f} pt")
    print(f"  Decorative cutoff   < {report.decorative_threshold:.1f} pt")

    print(f"\n  Column count        {report.column_count}")

    print(f"\n  ─── Derived Constants ───")
    for k, v in constants.items():
        print(f"  {k:<14}  =  {v}")

    print("═" * 64 + "\n")
