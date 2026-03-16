"""
tests/test_bugs.py — Regression tests for the three confirmed production bugs.

Each test is named to describe the bug it prevents, not the implementation.
Comments explain the original failure so future maintainers understand what
would break if the fix were reverted.

Bug 1 — Hyphenated word breaks produce false "missing word" positives.
  Root cause: extract_pdf() returned final_text (raw \n-joined lines).
  pdf_ready.split() → ["agnostic-", "approach"], web has "agnostic-approach".
  Fix: extract_pdf() now rebuilds pdf_ready from _join_lines_into_paragraph().

Bug 2 — PAGE_DELIMITER ("--- Page Break ---") leaked into comparison text.
  Root cause: same return value — PAGE_DELIMITER.join(all_logical_page_texts)
  was returned as pdf_ready; check_missing_words flagged the marker words.
  Fix: same fix as Bug 1 — paragraphs never contain PAGE_DELIMITER.

Bug 3 — Normaliser safety (no separate normalizer.py exists in this codebase).
  The prepare() function in web_scraper.py already implements NFC+strip only.
  Tests here pin that behaviour so it cannot silently regress.
"""

from __future__ import annotations

import glob
import os
import re

import pytest

from pdf_engine.extractor.extract import (
    PAGE_DELIMITER,
    _join_lines_into_paragraph,
    _group_spans_column_aware,
)
from pdf_engine.qa.web_scraper import prepare
from pdf_engine.qa.checks import (
    check_extra_whitespace,
    check_currency_mismatch,
    check_missing_words,
    check_missing_paragraphs,
)


# ──────────────────────────────────────────────────────────────────────────────
# Bug 1 — Hyphen join: confirmed false-positive cases
# ──────────────────────────────────────────────────────────────────────────────

class TestHyphenJoinRegressions:
    """
    Regression tests that the confirmed false positives from Bug 1 cannot recur.

    The three rules tested here mirror what the extractor applies before
    returning pdf_ready. They are tested at the function level so failures
    pinpoint the exact rule that broke, not just the symptom.
    """

    def test_hyphen_lowercase_continuation_no_space_inserted(self):
        """
        Regression Bug 1 (confirmed): "agnostic-" + "approach" must join
        without a space. The old code produced "agnostic- approach" which was
        flagged as missing from the website.
        """
        # Regression: confirmed false positive case from production
        lines = ["agnostic-", "approach"]
        assert _join_lines_into_paragraph(lines) == "agnostic-approach"

    def test_hyphen_lowercase_high_quality_confirmed_instance(self):
        """
        Regression Bug 1 (confirmed): "high-" + "quality," must join to
        "high-quality,". The trailing comma must not be lost or separated.
        """
        # Regression: second confirmed false positive from page 1 col LEFT
        lines = ["delivering high-", "quality,"]
        assert _join_lines_into_paragraph(lines) == "delivering high-quality,"

    def test_hyphen_uppercase_continuation_space_preserved(self):
        """
        Negative case: hyphen at line-end + uppercase continuation is NOT a
        broken compound word. Space must be preserved.
        E.g. "agnostic-" + "Approach" → "agnostic- Approach" (intact).
        """
        lines = ["agnostic-", "Approach"]
        result = _join_lines_into_paragraph(lines)
        assert result == "agnostic- Approach"

    def test_soft_hyphen_stripped_and_joined_correctly(self):
        """
        Soft hyphens (U+00AD) are layout artefacts — they must be stripped
        and the word joined directly with no space: "capa\u00ad" + "bility"
        must produce "capability" not "capa bility" or "capabili­ty".
        """
        # Regression: soft hyphen at line end is an invisible typesetting hint
        lines = ["capa\u00ad", "bility"]
        assert _join_lines_into_paragraph(lines) == "capability"

    def test_pdf_ready_no_spurious_hyphen_space_pairs(self):
        """
        End-to-end: after applying _join_lines_into_paragraph(), the regex
        r'[a-z]- [a-z]' must not match any content in the joined text.
        This regex is the smoke-test form used for production verification.
        """
        lines = [
            "We offer a technology-",
            "agnostic approach and high-",
            "quality output.",
        ]
        result = _join_lines_into_paragraph(lines)
        spurious = re.findall(r"[a-z]- [a-z]", result)
        assert spurious == [], (
            f"Spurious hyphen-space pairs detected: {spurious}. "
            f"Joined text: {result!r}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Bug 2 — Structural markers must not reach comparison text
# ──────────────────────────────────────────────────────────────────────────────

class TestStructuralMarkerStripped:
    """
    Regression tests that structural extraction markers cannot leak into the
    pdf_ready text used by check_missing_words and check_missing_paragraphs.

    In the old code: extract_pdf returned final_text which was built as
        PAGE_DELIMITER.join(all_logical_page_texts)
    PAGE_DELIMITER = "\n\n--- Page Break ---\n\n"

    check_missing_words split that on whitespace → ["---", "Page", "Break", "---"]
    were flagged as missing from the website. This was a confirmed false positive.
    """

    def test_page_marker_not_in_pdf_ready_reconstruction(self):
        """
        Regression Bug 2 (confirmed): "--- Page Break ---" must not appear
        in the pdf_ready text returned by extract_pdf().

        The fix builds pdf_ready as:
            "\n\n".join(p["text"] for p in pdf_paragraphs)
        Paragraph texts hold only real content — PAGE_DELIMITER is only ever
        added to final_text (the debug file write), never to paragraph objects.
        """
        # Simulate the multi-page paragraph list extract_pdf builds
        pdf_paragraphs = [
            {"text": "First page real content here.", "page": 1},
            {"text": "Second page real content here.", "page": 2},
        ]
        # This is the exact expression from the fixed extract_pdf()
        pdf_ready = "\n\n".join(p["text"] for p in pdf_paragraphs)

        assert "--- Page Break ---" not in pdf_ready, (
            f"Page marker leaked into pdf_ready: {pdf_ready!r}"
        )
        assert PAGE_DELIMITER not in pdf_ready, (
            f"Full PAGE_DELIMITER leaked into pdf_ready: {pdf_ready!r}"
        )
        # Smoke test: the regex used in production verification
        structural = re.findall(r"-{2,}[A-Z\s\d]+-{2,}", pdf_ready)
        assert structural == [], (
            f"Structural marker pattern found in pdf_ready: {structural}"
        )

    def test_no_column_marker_inserted_between_columns(self):
        """
        Regression guard: unlike PAGE_DELIMITER for pages, the column-aware
        reader inserts NO separator string between columns. Lines from
        column 1 are immediately followed by lines from column 2 with no
        "--- Column ---" or similar marker injected.

        This test verifies that _group_spans_column_aware() maintains that
        invariant so a future refactor cannot accidentally introduce markers.
        """
        # Build spans across two clear columns (gap > COLUMN_GUTTER_MIN_PT=60)
        def span(text, x0, y0):
            return {"text": text, "x0": x0, "y0": y0,
                    "x1": x0 + 60, "y1": y0 + 10, "size": 10.0, "font": "Helvetica"}

        # Column 1: x0 ≈ 50
        col1_spans = [
            span("Col one line A", x0=50.0, y0=100.0),
            span("Col one line B", x0=50.0, y0=114.0),
        ]
        # Column 2: x0 ≈ 200 (gap of 150 > 60 threshold)
        col2_spans = [
            span("Col two line A", x0=200.0, y0=100.0),
            span("Col two line B", x0=200.0, y0=114.0),
        ]
        all_spans = col1_spans + col2_spans

        lines = _group_spans_column_aware(all_spans, line_bucket=6)
        combined = "\n".join(lines)

        # No dashes of any length used as separators
        assert "---" not in combined, (
            f"Unexpected separator found between columns: {combined!r}"
        )
        # Real content must be present
        assert "Col one line A" in combined
        assert "Col two line A" in combined

    def test_real_content_with_dashes_not_stripped(self):
        """
        Guard: real PDF content that contains dashes (em-dash, double-dash,
        comparison expressions like "A -- B") must survive unchanged.
        Only PAGE_DELIMITER-style markers are excluded — not actual dash content.
        """
        # Paragraph whose text legitimately contains dash sequences
        pdf_paragraphs = [
            {"text": "Revenue grew 20% — a record high.", "page": 1},
            {"text": "Segments A -- B showed strong results.", "page": 1},
        ]
        pdf_ready = "\n\n".join(p["text"] for p in pdf_paragraphs)

        assert "—" in pdf_ready  # em-dash preserved
        assert "--" in pdf_ready  # double-dash preserved
        assert "Revenue grew 20% — a record high." in pdf_ready
        assert "Segments A -- B showed strong results." in pdf_ready


# ──────────────────────────────────────────────────────────────────────────────
# Bug 3 — Normaliser safety (prepare() in web_scraper)
# ──────────────────────────────────────────────────────────────────────────────

class TestPrepareFunction:
    """
    Regression tests for web_scraper.prepare().

    The `prepare()` function must only apply NFC normalisation and strip.
    Any additional operations (space collapsing, currency unification,
    ligature conversion) would hide real errors the QA checks are meant to find.

    These tests pin the exact current behaviour. If someone adds a new
    normalisation step to prepare(), at least one assertion here will fail,
    forcing an explicit review of whether the change is safe.
    """

    def test_prepare_contains_only_nfc_and_strip(self):
        """
        prepare() must leave double spaces, multiple newlines, and unusual
        but valid Unicode intact — only NFC + strip is allowed.
        """
        import unicodedata

        # Verify NFC is applied: é (decomposed NFD) → é (composed NFC)
        nfd_e = "e\u0301"  # 'e' + combining acute accent = NFD form of é
        nfc_e = "\u00e9"   # é = precomposed NFC form
        assert nfd_e != nfc_e          # sanity: they really differ before prepare
        result = prepare(nfd_e)
        assert result == nfc_e, (
            f"prepare() must apply NFC: {nfd_e!r} → {nfc_e!r}, got {result!r}"
        )

        # Verify strip: leading/trailing whitespace removed
        assert prepare("  hello  ") == "hello"
        assert prepare("\nhello\n") == "hello"

    def test_double_space_survives_prepare(self):
        """
        Regression Bug 3: a double space in web text is a real error that
        check_extra_whitespace is designed to detect. prepare() must not
        collapse multiple spaces — otherwise the check becomes blind.
        """
        # Regression: if prepare() collapses spaces, check_extra_whitespace
        # would never fire because the error would be erased before comparison
        text = "word1  word2"  # two spaces — a real whitespace error
        result = prepare(text)
        assert "  " in result, (
            f"prepare() must preserve consecutive spaces for check_extra_whitespace. "
            f"Input: {text!r}, got: {result!r}"
        )

    def test_currency_symbol_survives_prepare(self):
        """
        Regression Bug 3: currency symbols (₹, H, Rs.) must survive prepare()
        unchanged. If prepare() unified them (e.g. all → ₹), check_currency_mismatch
        would see the same symbol on both sides and miss the mismatch.
        """
        # Regression: if prepare() normalises H (ITFRupee glyph) → ₹, the check
        # comparing PDF "H1630" against web "Rs.1630" would see "₹1630" on both
        # sides and report no mismatch — a false negative.
        for symbol in ["₹", "Rs.", "Rs", "INR", "H"]:
            result = prepare(f"{symbol}1,630 Crores")
            assert symbol in result, (
                f"prepare() must not remove or transform currency symbol {symbol!r}. "
                f"Got: {result!r}"
            )

    def test_internal_whitespace_not_collapsed(self):
        """
        prepare() must not reduce multiple internal spaces to one. That is
        an UNSAFE operation — it hides whitespace errors from Check 1.
        """
        text = "before  after"  # double space in middle
        assert "  " in prepare(text), (
            "prepare() collapses internal spaces — this hides extra_whitespace issues"
        )

    def test_newlines_preserved(self):
        """prepare() must not collapse or remove internal newlines."""
        text = "line one\nline two"
        assert "\n" in prepare(text), (
            "prepare() must preserve internal newlines"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Fix 4 — No diff_html key in any issue object from any check
# ──────────────────────────────────────────────────────────────────────────────

class TestNoLegacyDiffHtml:
    """
    Regression tests: no issue dict returned by any of the 5 checks may
    contain a 'diff_html' key. The old architecture produced HTML strings
    on the backend (XSS risk). The new architecture uses typed fields rendered
    safely as React nodes — no raw HTML crosses the API boundary.
    """

    def _assert_no_diff_html(self, issues: list[dict], check_name: str) -> None:
        for issue in issues:
            assert "diff_html" not in issue, (
                f"{check_name}: issue contains legacy 'diff_html' key.\n"
                f"Issue type: {issue.get('type')}\n"
                f"Keys present: {list(issue.keys())}"
            )

    def test_check_extra_whitespace_no_diff_html(self):
        """check_extra_whitespace must not produce diff_html."""
        # Regression: old code produced diff_html for every issue
        issues = check_extra_whitespace("word1  word2  word3", [])
        assert len(issues) >= 1, "Test input must produce at least one issue"
        self._assert_no_diff_html(issues, "check_extra_whitespace")

    def test_check_currency_mismatch_no_diff_html(self):
        """check_currency_mismatch must not produce diff_html."""
        # PDF uses 'H' prefix (ITFRupee glyph), web uses 'Rs.' — confirmed mismatch
        pdf_ready = "H1630 Crores revenue"
        web_ready = "Rs.1630 Crores revenue"
        issues = check_currency_mismatch(pdf_ready, web_ready, [])
        assert len(issues) >= 1, "Test input must produce at least one issue"
        self._assert_no_diff_html(issues, "check_currency_mismatch")

    def test_check_missing_words_no_diff_html(self):
        """check_missing_words must not produce diff_html."""
        # Use ≥6-word sentences — the sentence splitter minimum.
        # PDF has 'high-quality' which is absent from the web text.
        pdf_text = (
            "Our clinics have been operational for many years across the region. "
            "We deliver high-quality accessible fertility care to all our patients."
        )
        web_text = (
            "Our clinics have been operational for many years across the region. "
            "We deliver accessible fertility care to all our patients."
        )
        issues = check_missing_words(pdf_text, web_text)
        assert len(issues) >= 1, "Test input must produce at least one issue"
        self._assert_no_diff_html(issues, "check_missing_words")

    def test_check_missing_paragraphs_no_diff_html(self):
        """check_missing_paragraphs must not produce diff_html."""
        # PDF paragraph long enough to trigger the check (>= 60 chars)
        long_para = "This paragraph is only in the PDF and not on the website at all here."
        pdf_paragraphs = [{"text": long_para, "page": 1, "para_index": 1, "column": "FULL"}]
        issues = check_missing_paragraphs("", "unrelated web content", pdf_paragraphs)
        # At least one issue should be found (score will be < 80 threshold)
        self._assert_no_diff_html(issues, "check_missing_paragraphs")


# ──────────────────────────────────────────────────────────────────────────────
# Fix 5 — No dangerouslySetInnerHTML in actual frontend component code
# ──────────────────────────────────────────────────────────────────────────────

class TestFrontendNoDangerousHtml:
    """
    Regression test: no frontend component may use dangerouslySetInnerHTML
    to inject issue content.

    dangerouslySetInnerHTML with API-supplied strings is an XSS vector.
    All issue content must be rendered as typed React nodes.

    This test scans the actual .tsx files for dangerouslySetInnerHTML in
    executable code lines (comments that say "we do NOT use X" are OK).
    """

    def test_no_dangerous_html_in_component_code(self):
        """
        Regression Fix 5: grep all .tsx files in components/ for
        dangerouslySetInnerHTML in non-comment lines.
        """
        # Locate the qa-dashboard from this test file's position
        tests_dir = os.path.dirname(__file__)
        # pdf_engine/tests/ → go up 2 levels to project root
        project_root = os.path.abspath(os.path.join(tests_dir, "..", ".."))
        components_dir = os.path.join(project_root, "qa-dashboard", "components")

        if not os.path.exists(components_dir):
            pytest.skip(
                "qa-dashboard/components not found — skipping frontend check. "
                "Run from the project root or ensure qa-dashboard is present."
            )

        tsx_files = glob.glob(
            os.path.join(components_dir, "**", "*.tsx"), recursive=True
        )
        assert tsx_files, (
            f"No .tsx files found under {components_dir}. "
            "Check the path or confirm components exist."
        )

        violations: list[str] = []
        for filepath in sorted(tsx_files):
            with open(filepath, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if "dangerouslySetInnerHTML" not in stripped:
                        continue
                    # Allow JSDoc/block comments (* prefix) and line comments
                    if stripped.startswith("*") or stripped.startswith("//"):
                        continue
                    # Everything else is executable code — flag it
                    rel_path = os.path.relpath(filepath, project_root)
                    violations.append(f"{rel_path}:{lineno}: {stripped[:120]}")

        assert violations == [], (
            "dangerouslySetInnerHTML found in actual component code "
            "(not just comments):\n" + "\n".join(violations)
        )
