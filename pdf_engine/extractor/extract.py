"""
Phase 2 — Extract text from measured PDFs.

Uses ONLY the empirical constants from Phase 1 MeasurementReport.
Library: PyMuPDF (fitz) only — rawdict mode with native clip rects.

Core rules:
  - No OCR (digital PDFs only)
  - No hardcoded dimensions (everything from measurement)
  - Never silently produce an empty .txt
  - Output is plain text — no JSON, no Markdown
  - One .txt per PDF — no exceptions

Key design:
  Text is extracted using _extract_span_text() which handles both
  standard span["text"] and chars-only encoding transparently.
"""

from __future__ import annotations

import os
import logging
from collections import defaultdict

import fitz  # PyMuPDF

from pdf_engine.extractor.measure import MeasurementReport, _extract_span_text

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Page delimiter in output
# ──────────────────────────────────────────────
PAGE_DELIMITER = "\n\n--- Page Break ---\n\n"


def _build_clip_rect(
    constants: dict,
    page_width: float,
    page_height: float,
    crop_top: float = 0.0,
    crop_bottom: float = 1.0,
    crop_left: float = 0.0,
    crop_right: float = 1.0,
) -> fitz.Rect:
    """
    Build the extraction clip rect combining UI crop values and empirical constants.
    """
    # 1. Start with exact crop percentages from UI
    y0 = page_height * crop_top
    y1 = page_height * crop_bottom
    x0 = page_width * crop_left
    x1 = page_width * crop_right

    # 2. Factor in empirical constants (the more restrictive wins)
    header_y = constants["HEADER_Y"]
    footer_y = constants["FOOTER_Y"]
    sidebar_x = constants["SIDEBAR_X"]

    if header_y > 0 and header_y < footer_y and header_y < page_height:
        y0 = max(y0, header_y)
    if footer_y < page_height and footer_y > header_y and footer_y > 0:
        y1 = min(y1, footer_y)

    if sidebar_x > 0 and sidebar_x < page_width:
        x1 = min(x1, sidebar_x)

    # Sanity checks
    if y0 >= y1:
        y0, y1 = 0, page_height
    if x0 >= x1:
        x0, x1 = 0, page_width

    return fitz.Rect(x0, y0, x1, y1)


def _extract_page_spans(
    page: fitz.Page,
    clip_rect: fitz.Rect,
    min_font: float,
) -> list[dict]:
    """
    Extract filtered spans from a single page using rawdict + clip.

    Handles both standard and chars-only text encoding via
    _extract_span_text().

    Filters:
      - block type != 0 (non-text blocks)
      - font size < min_font (decorative glyphs)
      - whitespace-only spans
    """
    raw = page.get_text("rawdict", clip=clip_rect)
    spans = []

    for block in raw.get("blocks", []):
        # Only text blocks (type 0)
        if block.get("type", 0) != 0:
            continue

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = _extract_span_text(span)
                if not text:
                    continue

                size = span.get("size", 0)
                if size < min_font:
                    continue

                spans.append({
                    "text": text,
                    "x0": span["bbox"][0],
                    "y0": span["bbox"][1],
                    "x1": span["bbox"][2],
                    "y1": span["bbox"][3],
                    "size": size,
                    "font": span.get("font", ""),
                })

    return spans


def _post_filter_noise(
    spans: list[dict],
    report: MeasurementReport,
) -> list[dict]:
    """
    Post-filter to remove noise spans that survived the clip rect.

    This handles cases where:
    - Sidebar tab text overlaps with content column x ranges
    - Header/footer text at the edge of clip boundaries

    Removes spans whose text exactly matches a known noise string.
    """
    noise_strings: set[str] = set()
    noise_strings.update(report.header_strings)
    noise_strings.update(report.footer_strings)
    noise_strings.update(report.sidebar_strings)

    if not noise_strings:
        return spans

    filtered = []
    for s in spans:
        if s["text"].strip() in noise_strings:
            logger.debug("Post-filtered noise string: '%s'", s["text"])
            continue
        filtered.append(s)

    removed = len(spans) - len(filtered)
    if removed > 0:
        logger.info("Post-filtered %d noise spans", removed)

    return filtered


def _split_spread(
    spans: list[dict],
    mid_x: float,
) -> tuple[list[dict], list[dict]]:
    """
    Split spans into LEFT and RIGHT sides at the spread midpoint.
    Used for spread layouts where one PDF page = two logical pages.
    """
    left = []
    right = []

    for s in spans:
        center_x = (s["x0"] + s["x1"]) / 2
        if center_x < mid_x:
            left.append(s)
        else:
            # Shift x coordinates to be relative to the right page
            right.append({
                **s,
                "x0": s["x0"] - mid_x,
                "x1": s["x1"] - mid_x,
            })

    return left, right


def _group_spans_to_lines(
    spans: list[dict],
    line_bucket: int,
) -> list[str]:
    """
    Group spans into reading-order lines within a SINGLE column.

    1. Round each span's y0 to the nearest LINE_BUCKET multiple → line key
    2. Sort lines by y key
    3. Sort spans within each line by x0
    4. Join spans within a line with spaces
    """
    lines: defaultdict[int, list[dict]] = defaultdict(list)

    for s in spans:
        key = round(s["y0"] / line_bucket) * line_bucket
        lines[key].append(s)

    result = []
    for y_key in sorted(lines.keys()):
        line_spans = sorted(lines[y_key], key=lambda s: s["x0"])
        # Pattern D: strip individual span text before joining.
        # PyMuPDF sometimes includes trailing spaces inside span["text"].
        # Stripping here prevents double spaces within a single output line.
        line_text = " ".join(s["text"].strip() for s in line_spans)
        if line_text.strip():
            result.append(line_text)

    return result


# ── Column-aware reading order ──

# Minimum gap between columns in points
COLUMN_GUTTER_MIN_PT = 60.0


def _detect_column_boundaries(
    spans: list[dict],
) -> list[tuple[float, float]]:
    """
    Detect column boundaries by finding gaps in x0 positions.

    Groups spans by x0 position, finds clusters of x0 values
    with gaps > COLUMN_GUTTER_MIN_PT, and returns column ranges
    as (x_start, x_end) tuples sorted left-to-right.
    """
    if not spans:
        return []

    # Collect all unique x0 positions rounded to nearest int
    x0_positions = sorted(set(round(s["x0"]) for s in spans))

    if not x0_positions:
        return []

    # Find gaps > gutter threshold → column boundaries
    columns: list[list[int]] = [[x0_positions[0]]]

    for i in range(1, len(x0_positions)):
        gap = x0_positions[i] - x0_positions[i - 1]
        if gap > COLUMN_GUTTER_MIN_PT:
            columns.append([x0_positions[i]])
        else:
            columns[-1].append(x0_positions[i])

    # Build column ranges
    col_ranges = []
    for col_x0s in columns:
        col_start = min(col_x0s)
        col_end = max(col_x0s)
        col_ranges.append((float(col_start), float(col_end)))

    return col_ranges


def _assign_spans_to_columns(
    spans: list[dict],
    columns: list[tuple[float, float]],
) -> list[list[dict]]:
    """
    Assign each span to its nearest column based on x0 position.
    Returns one list of spans per column, in column order.
    """
    column_spans: list[list[dict]] = [[] for _ in columns]

    for s in spans:
        x0 = s["x0"]
        # Find the column whose x_start is closest to this span's x0
        best_col = 0
        best_dist = abs(x0 - columns[0][0])
        for ci in range(1, len(columns)):
            dist = abs(x0 - columns[ci][0])
            if dist < best_dist:
                best_dist = dist
                best_col = ci
        column_spans[best_col].append(s)

    return column_spans


def _group_spans_column_aware(
    spans: list[dict],
    line_bucket: int,
) -> list[str]:
    """
    Enhanced reading order: detects columns, reads each column
    top-to-bottom, then moves to the next column.

    Falls back to simple left-to-right line grouping if only 1 column.
    """
    if not spans:
        return []

    columns = _detect_column_boundaries(spans)

    if len(columns) <= 1:
        # Single column — use simple line grouping
        return _group_spans_to_lines(spans, line_bucket)

    # Multi-column: read each column sequentially
    column_spans = _assign_spans_to_columns(spans, columns)

    all_lines: list[str] = []
    for col_spans in column_spans:
        if col_spans:
            col_lines = _group_spans_to_lines(col_spans, line_bucket)
            all_lines.extend(col_lines)

    return all_lines


def _join_lines_into_paragraph(lines: list[str]) -> str:
    """
    Join extracted text lines into a single paragraph string.

    Standard joining inserts a space between every line. That is correct for
    most lines, but produces a spurious space inside hyphenated words that are
    broken across PDF column lines:

        "agnostic-" + "approach" → "agnostic- approach"  ← WRONG
                                 → "agnostic-approach"   ← CORRECT

    Rules applied in order for each pair (current tail, next line):

      Step 0 — Strip trailing soft hyphens (U+00AD) unconditionally.
        Soft hyphens are invisible typesetting hints inserted at permissible
        break points. They carry no semantic meaning. Stripping them first
        exposes the actual last meaningful character and handles mixed
        sequences like "word-\u00ad" (hard hyphen then soft hyphen at line end).

      Rule 1 — Hard hyphen at end (after soft hyphens stripped) + lowercase:
        Join directly without a space. The hard hyphen is kept — it is part
        of the compound word.
        "high-"       + "quality,"  → "high-quality,"
        "agnostic-"   + "approach"  → "agnostic-approach"
        "high-\u00ad" + "quality,"  → "high-quality,"   (soft hyphen stripped)

      Rule 1b — Hard hyphen at end + uppercase/digit/other:
        Real sentence-level hyphen — preserve the hyphen and insert a space.
        "high-"     + "Quality,"  → "high- Quality,"
        "agnostic-" + "Approach"  → "agnostic- Approach"

      Rule 2 — Soft hyphen(s) only (no hard hyphen underneath):
        Pure layout artefact. Drop all soft hyphens and join directly without
        a space — the word has no real hyphen.
        "capa\u00ad"   + "bility" → "capability"
        "inter\u00ad"  + "national" → "international"

      Rule 3 — All other pairs:
        Join with a single space (standard behaviour).

    Pattern B (column seams): column-aware reading order already places each
    column's lines sequentially in `lines`; Rules 1-2 apply at column seams
    exactly as they do within a column — no separate handling needed.

    Pattern C (page boundaries): PAGE_DELIMITER creates \\n\\n separators
    upstream, so paragraphs are split before reaching this function.
    Page-crossing re-joins never reach this function.
    """
    if not lines:
        return ""

    result = lines[0].strip()

    for next_line in lines[1:]:
        next_line = next_line.strip()
        if not next_line:
            continue

        # Step 0: strip trailing soft hyphens (U+00AD) unconditionally.
        # This exposes the real last character and handles "-\u00ad" sequences
        # where a hard hyphen is followed by a trailing soft hyphen.
        tail = result.rstrip("\u00ad")

        if tail.endswith("-"):
            # Rule 1 / 1b: hard hyphen exposed after removing soft hyphens.
            # Lowercase start → broken compound word → join without space.
            # Uppercase/other start → real hyphen → join with space.
            if next_line[0].islower():
                # Keep the hard hyphen; drop any trailing soft hyphens.
                # "high-" + "quality," → "high-quality,"
                result = tail + next_line
            else:
                # Real sentence hyphen; preserve it and insert a space.
                # "high-" + "Quality," → "high- Quality,"
                result = tail + " " + next_line

        elif tail != result:
            # Rule 2: soft hyphens only — no hard hyphen underneath.
            # Drop all soft hyphens; join directly (the word is unhyphenated).
            # "capa\u00ad" + "bility" → "capability"
            result = tail + next_line

        else:
            # Rule 3: no trailing hyphens — standard join with a single space.
            result = result + " " + next_line

    return result


def _process_logical_pages(
    spans: list[dict],
    constants: dict,
) -> list[list[str]]:
    """
    Process a PDF page's spans into one or more logical page outputs.
    If spread, splits into left/right and returns two sets of lines.
    Otherwise returns one set.

    Uses column-aware reading order to handle multi-column layouts.
    """
    mid_x = constants.get("MID_X")
    line_bucket = constants.get("LINE_BUCKET", 6)

    if mid_x is not None:
        left_spans, right_spans = _split_spread(spans, mid_x)
        logical_pages = []
        if left_spans:
            logical_pages.append(_group_spans_column_aware(left_spans, line_bucket))
        if right_spans:
            logical_pages.append(_group_spans_column_aware(right_spans, line_bucket))
        return logical_pages
    else:
        lines = _group_spans_column_aware(spans, line_bucket)
        return [lines] if lines else []


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def extract_pdf(
    pdf_bytes: bytes,
    output_dir: str,
    report: MeasurementReport | None = None,
    crop_top: float = 0.0,
    crop_bottom: float = 1.0,
    crop_left: float = 0.0,
    crop_right: float = 1.0,
    page_start: int = 0,
    page_end: int = -1,
) -> tuple[str, list[dict]]:
    """
    Main extraction entrypoint.
    Takes PDF bytes and writes clean text to {output_dir}/{stem}.txt.
    Returns (pdf_ready_text, pdf_paragraphs).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    # For reporting, just use a dummy stem since we don't have filename here
    stem = "input"

    if report is None:
        logger.warning("No measurement report provided to extractor for %s.pdf", stem)
        constants = MeasurementReport(filepath=f"{stem}.pdf").to_constants()
    else:
        constants = report.to_constants()

    os.makedirs(output_dir, exist_ok=True)

    # We don't have a filename, so we'll use a dummy one for output path
    output_path = os.path.join(output_dir, f"{stem}.txt")

    # Determine pages
    total_pages = len(doc)
    start_idx = max(0, min(page_start, total_pages - 1))
    end_idx = total_pages if page_end < 0 else min(page_end, total_pages)

    total_words = 0
    skipped_pages: list[int] = []
    all_logical_page_texts: list[str] = []
    extracted_pages = [] # This variable was in the provided snippet but not used in the original context. Keeping it for now.
    pdf_paragraphs: list[dict] = [] # This variable was in the provided snippet but not used in the original context. Keeping it for now.
    global_para_index = 0 # This variable was in the provided snippet but not used in the original context. Keeping it for now.

    min_font = constants.get("MIN_FONT", 8)

    for page_num in range(start_idx, end_idx):
        page = doc[page_num]

        # ── Step 1: Handle rotation ──
        if page.rotation != 0:
            logger.info("Removing rotation (%d°) on page %d", page.rotation, page_num + 1)
            page.remove_rotation()

        # Use full rect from PyMuPDF
        rect = page.rect
        page_width, page_height = rect.width, rect.height

        # Build clip
        clip_rect = _build_clip_rect(
            constants,
            page_width,
            page_height,
            crop_top,
            crop_bottom,
            crop_left,
            crop_right,
        )
        # ── Step 2: Digital check ──
        plain = page.get_text().strip()
        if len(plain) < 50:
            logger.warning(
                "⚠ %s.pdf page %d — skipped: insufficient text layer (%d chars)",
                stem, page_num + 1, len(plain),
            )
            print(f"  ⚠ {stem}.pdf page {page_num + 1} — skipped: insufficient text ({len(plain)} chars)")
            continue

        # ── Step 3: Extract with rawdict + clip ──
        spans = _extract_page_spans(page, clip_rect, min_font)

        if not spans:
            logger.warning(
                "⚠ %s page %d — 0 spans after filtering (text layer exists: %d chars)",
                stem, page_num + 1, len(plain),
            )
            continue

        # ── Step 4: Post-filter noise strings ──
        if report is not None:
            spans = _post_filter_noise(spans, report)

        # ── Step 5: Process into logical pages ──
        logical_pages = _process_logical_pages(spans, constants)

        for lp_lines in logical_pages:
            page_text = "\n".join(lp_lines)
            word_count = sum(len(line.split()) for line in lp_lines)
            total_words += word_count
            all_logical_page_texts.append(page_text)

            # Save paragraph text and metadata
            raw_paragraphs = page_text.split("\n\n")

            for para_text in raw_paragraphs:
                para_text = para_text.strip()
                if not para_text:
                    continue

                # Join wrapped lines (handles hyphenated word breaks across lines).
                # _join_lines_into_paragraph() merges "word-" + "wrap" → "word-wrap"
                # instead of producing the spurious "word- wrap".
                para_lines = [line.strip() for line in para_text.split("\n") if line.strip()]
                joined = _join_lines_into_paragraph(para_lines)

                if not joined:
                    continue

                global_para_index += 1
                pdf_paragraphs.append({
                    "text": joined,
                    "page": page_num + 1,
                    "para_index": global_para_index,
                    "column": "FULL",
                })

    doc.close()

    # ── Step 6: Join pages ──
    final_text = PAGE_DELIMITER.join(all_logical_page_texts)

    # ── Step 7: Write output ──
    if not final_text.strip():
        # Never silently produce an empty .txt
        logger.error("EMPTY_OUTPUT: %s.pdf produced no extractable text", stem)
        print(f"  ✗ {stem}.pdf — EMPTY OUTPUT (no extractable text)")
        final_text = f"[EMPTY — no extractable text from {stem}.pdf]"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    # ── Report ──
    logical_count = len(all_logical_page_texts)
    print(
        f"  ✓ {stem}.pdf → {os.path.basename(output_dir)}/{stem}.txt  "
        f"({logical_count} logical pages, {total_words} words)"
    )

    # Rebuild comparison corpus from properly joined paragraphs.
    # This fixes two confirmed production bugs with a single change:
    #   Bug 1 — Hyphenated word breaks: raw `final_text` contains line endings
    #     like "agnostic-\napproach"; pdf_ready.split() → ["agnostic-", "approach"];
    #     check_missing_words flags "agnostic-" as missing from the website.
    #     pdf_paragraphs already has the correct joined text via
    #     _join_lines_into_paragraph() (e.g. "agnostic-approach") — use that.
    #   Bug 2 — Structural markers: PAGE_DELIMITER ("--- Page Break ---") is
    #     inserted into final_text at Step 6 above. It never appears in
    #     pdf_paragraphs. Rebuilding from paragraphs eliminates it automatically.
    # The file write above still uses final_text unchanged (for debug output).
    pdf_ready = "\n\n".join(p["text"] for p in pdf_paragraphs)
    return pdf_ready, pdf_paragraphs
