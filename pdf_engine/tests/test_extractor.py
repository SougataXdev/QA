"""
tests/test_extractor.py — Regression tests for extract.py.

Focus areas:
  TestJoinLines          — _join_lines_into_paragraph() hyphen + soft-hyphen rules
  TestGroupSpansToLines  — _group_spans_to_lines() Pattern D (span trailing spaces)
"""

from __future__ import annotations

import pytest

from pdf_engine.extractor.extract import (
    _join_lines_into_paragraph,
    _group_spans_to_lines,
)


# ──────────────────────────────────────────────────────────────────────────────
# TestJoinLines — _join_lines_into_paragraph()
# ──────────────────────────────────────────────────────────────────────────────

class TestJoinLines:
    """
    Regression tests for the hyphenated-word-break false positive.

    Root cause: the old " ".join(lines) unconditionally inserted a space after
    every line, producing "agnostic- approach" instead of "agnostic-approach"
    when a word was broken across a narrow column line.
    """

    # ── Rule 1: hard hyphen + lowercase start ──

    def test_hyphen_lowercase_joins_without_space(self):
        """
        Confirmed false positive case: line ending with '-' + next line
        starting with a lowercase letter must merge with NO space inserted.
        """
        lines = ["agnostic-", "approach"]
        assert _join_lines_into_paragraph(lines) == "agnostic-approach"

    def test_hyphen_lowercase_midparagraph(self):
        """The fix must work when the hyphenated break is in the middle."""
        lines = ["We are a technology-", "agnostic firm."]
        assert _join_lines_into_paragraph(lines) == "We are a technology-agnostic firm."

    def test_hyphen_lowercase_multiple_breaks(self):
        """Multiple hyphenated breaks in one paragraph must all be fixed."""
        lines = ["cost-", "effective and tech-", "nology driven"]
        assert _join_lines_into_paragraph(lines) == "cost-effective and tech-nology driven"

    def test_high_quality_confirmed_instance(self):
        """
        REGRESSION — second confirmed false positive from page 1 col LEFT.

        "delivering high-" on one narrow-column line, "quality," on the next.
        The comma attached to "quality," must survive the join.
        """
        lines = ["delivering high-", "quality, accessible"]
        assert _join_lines_into_paragraph(lines) == "delivering high-quality, accessible"

    def test_chained_hyphen_word(self):
        """
        A line ending in "-" where the next line itself contains a hyphen.
        "end-" + "of-line" → the word "end-of-line" must be intact.
        """
        lines = ["end-", "of-line sentence continues"]
        assert _join_lines_into_paragraph(lines) == "end-of-line sentence continues"

    def test_hyphen_uppercase_preserves_space(self):
        """
        Negative case: hyphen at end of line + uppercase start of next line is
        NOT a broken word — it is a legitimate sentence boundary or proper noun.
        Space must be preserved.
        """
        lines = ["agnostic-", "Approach"]
        result = _join_lines_into_paragraph(lines)
        assert result == "agnostic- Approach"

    def test_high_quality_uppercase_preserves_space(self):
        """
        REGRESSION negative case — same layout as the confirmed 'high-quality'
        instance, but with an uppercase continuation.
        "high-" + "Quality," must produce "high- Quality," (space kept).
        """
        lines = ["delivering high-", "Quality, accessible"]
        assert _join_lines_into_paragraph(lines) == "delivering high- Quality, accessible"

    def test_hyphen_digit_preserves_space(self):
        """
        Hyphen + digit at start of next line is not a broken word.
        e.g. "Q3-" then "2024" might be a figure reference. Preserve space.
        """
        lines = ["results Q3-", "2024 outlook"]
        result = _join_lines_into_paragraph(lines)
        assert result == "results Q3- 2024 outlook"

    def test_no_hyphen_normal_join(self):
        """Lines without trailing hyphens are joined with a single space."""
        lines = ["The quick brown", "fox jumps over", "the lazy dog."]
        assert _join_lines_into_paragraph(lines) == "The quick brown fox jumps over the lazy dog."

    def test_single_line_returned_unchanged(self):
        """A single-element list returns that element as-is."""
        assert _join_lines_into_paragraph(["Hello world"]) == "Hello world"

    def test_empty_list_returns_empty_string(self):
        """Empty input must return empty string, not raise."""
        assert _join_lines_into_paragraph([]) == ""

    # ── Rule 2: soft hyphen U+00AD (Pattern A) ──

    def test_soft_hyphen_stripped_and_joined(self):
        """
        Pattern A: Soft hyphens (U+00AD) are layout artefacts inserted by
        typesetting engines. They must be stripped and the word joined directly.
        """
        lines = ["capa\u00ad", "bility"]
        assert _join_lines_into_paragraph(lines) == "capability"

    def test_hard_hyphen_with_trailing_soft_hyphen(self):
        """
        Mixed sequence: hard hyphen followed by soft hyphen at line end.

        Old code: endswith("-") is False (ends with \\u00ad) → Rule 1 misses it;
                  Rule 2 fires → rstrip("\\u00ad") → "high-" → joins directly ✓
                  (happened to work by accident, hard hyphen preserved).
        New code: Step 0 strips soft hyphens first → tail = "high-" →
                  Rule 1 fires with the correct uppercase check → ✓

        This test pins the correct behaviour so it can never regress.
        """
        # "high-\u00ad" stripped to "high-" → next starts lowercase → join
        lines = ["high-\u00ad", "quality,"]
        assert _join_lines_into_paragraph(lines) == "high-quality,"

    def test_hard_hyphen_with_trailing_soft_hyphen_uppercase(self):
        """
        Mixed sequence + uppercase next line: space must be preserved.

        Step 0 strips \\u00ad → tail = "high-" → next starts uppercase →
        Rule 1b fires → "high- Quality," (space inserted, hyphen kept).
        """
        lines = ["high-\u00ad", "Quality,"]
        assert _join_lines_into_paragraph(lines) == "high- Quality,"

    def test_soft_hyphen_multiple(self):
        """Multiple trailing soft hyphens are all stripped."""
        lines = ["inter\u00ad\u00ad", "national"]
        assert _join_lines_into_paragraph(lines) == "international"

    def test_soft_hyphen_midparagraph(self):
        """Soft hyphen fix works when surrounded by normal lines."""
        lines = ["We operate inter\u00ad", "nationally with high", "standards."]
        assert _join_lines_into_paragraph(lines) == "We operate internationally with high standards."

    # ── Pattern B: column seam ──

    def test_column_seam_hyphen_carried_across(self):
        """
        Pattern B: When multi-column reading order places col-1's last line
        directly before col-2's first line, the hyphen rule applies at that
        seam. Verify the join function handles it transparently.
        """
        # col-1 ends with "technology-", col-2 starts with "agnostic"
        lines = [
            "We use a",
            "technology-",   # ← column seam here
            "agnostic",
            "approach.",
        ]
        assert _join_lines_into_paragraph(lines) == "We use a technology-agnostic approach."

    # ── Whitespace edge cases ──

    def test_lines_with_leading_trailing_spaces_stripped(self):
        """Input lines with extra whitespace must be stripped before joining."""
        lines = ["  Hello  ", "  world  "]
        assert _join_lines_into_paragraph(lines) == "Hello world"

    def test_empty_line_in_middle_skipped(self):
        """Empty/whitespace-only lines after stripping are skipped."""
        lines = ["Hello", "   ", "world"]
        assert _join_lines_into_paragraph(lines) == "Hello world"


# ──────────────────────────────────────────────────────────────────────────────
# TestGroupSpansToLines — Pattern D: span trailing spaces
# ──────────────────────────────────────────────────────────────────────────────

class TestGroupSpansToLines:
    """
    Pattern D: PyMuPDF occasionally includes a trailing space inside
    span["text"] (e.g. "Hello " instead of "Hello"). When two such spans are
    joined with " ".join(), the result is "Hello  world" (double space).

    Fix: each span's text is stripped before joining.
    """

    def _make_span(self, text: str, x0: float, y0: float = 10.0) -> dict:
        """Helper: build a minimal span dict for _group_spans_to_lines()."""
        return {
            "text": text,
            "x0": x0,
            "y0": y0,
            "x1": x0 + 50,
            "y1": y0 + 10,
            "size": 10.0,
            "font": "Arial",
        }

    def test_span_trailing_space_does_not_produce_double_space(self):
        """
        Regression for Pattern D: span text "Hello " followed by "world"
        must produce "Hello world" not "Hello  world".
        """
        spans = [
            self._make_span("Hello ", x0=10.0),
            self._make_span("world", x0=70.0),
        ]
        lines = _group_spans_to_lines(spans, line_bucket=6)
        assert lines == ["Hello world"]
        assert "  " not in lines[0], "Double space must not appear in output"

    def test_span_leading_space_does_not_produce_double_space(self):
        """
        Span with leading space (e.g. " world") must also be stripped.
        """
        spans = [
            self._make_span("Hello", x0=10.0),
            self._make_span(" world", x0=70.0),
        ]
        lines = _group_spans_to_lines(spans, line_bucket=6)
        assert lines == ["Hello world"]
        assert "  " not in lines[0]

    def test_clean_spans_unaffected(self):
        """Normal spans without trailing spaces must join correctly."""
        spans = [
            self._make_span("The", x0=10.0),
            self._make_span("quick", x0=40.0),
            self._make_span("brown", x0=80.0),
        ]
        lines = _group_spans_to_lines(spans, line_bucket=6)
        assert lines == ["The quick brown"]

    def test_multiple_lines_preserved(self):
        """Spans on different Y positions must produce separate lines."""
        spans = [
            self._make_span("Line one", x0=10.0, y0=10.0),
            self._make_span("Line two", x0=10.0, y0=30.0),
        ]
        lines = _group_spans_to_lines(spans, line_bucket=6)
        assert len(lines) == 2
        assert lines[0] == "Line one"
        assert lines[1] == "Line two"

    def test_whitespace_only_span_excluded(self):
        """A span whose text is only spaces must not produce a blank line."""
        spans = [
            self._make_span("   ", x0=10.0, y0=10.0),
        ]
        lines = _group_spans_to_lines(spans, line_bucket=6)
        assert lines == []


# ──────────────────────────────────────────────────────────────────────────────
# TestSpanPipelineHyphenJoin — span dict → grouped lines → joined paragraph
# ──────────────────────────────────────────────────────────────────────────────

class TestSpanPipelineHyphenJoin:
    """
    Integration tests: span dicts (as PyMuPDF produces them) flow through
    _group_spans_to_lines() and then _join_lines_into_paragraph(), replicating
    the exact pipeline used by the extractor for the confirmed false positive.

    Line 1 spans simulate the first column line ending with "agnostic-".
    Line 2 spans simulate the next line beginning with "approach".
    Using y0 values that fall in different LINE_BUCKET=6 groups ensures the
    spans are assigned to separate lines before joining.
    """

    _LINE_BUCKET = 6

    def _make_span(self, text: str, x0: float, y0: float) -> dict:
        """Minimal span dict matching the shape _group_spans_to_lines expects."""
        return {
            "text": text,
            "x0": x0,
            "y0": y0,
            "x1": x0 + len(text) * 6,
            "y1": y0 + 10,
            "size": 10.0,
            "font": "Helvetica",
        }

    def test_hyphen_break_lowercase_join_without_space(self):
        """
        REGRESSION — confirmed false positive (positive case).

        Span layout:
          Line 1 spans: [{"text": "This doctor agnostic-", ...}]
          Line 2 spans: [{"text": "approach reduces our reliance", ...}]

        After _group_spans_to_lines() groups them into two separate lines,
        _join_lines_into_paragraph() must detect the trailing '-' and lowercase
        start, and join without a space:

          Expected: "This doctor agnostic-approach reduces our reliance"
          Wrong:    "This doctor agnostic- approach reduces our reliance"
        """
        # y0=100 → bucket key 102; y0=114 → bucket key 114 — two different lines
        line1_spans = [
            self._make_span("This doctor ", x0=50.0, y0=100.0),
            self._make_span("agnostic-",   x0=122.0, y0=100.0),
        ]
        line2_spans = [
            self._make_span("approach reduces our reliance", x0=50.0, y0=114.0),
        ]

        all_spans = line1_spans + line2_spans
        lines = _group_spans_to_lines(all_spans, self._LINE_BUCKET)

        # Verify grouping produced two distinct lines
        assert len(lines) == 2, (
            f"Expected 2 lines from span grouping, got {len(lines)}: {lines!r}"
        )
        assert lines[0].rstrip().endswith("agnostic-"), (
            f"Line 1 must end with 'agnostic-', got: {lines[0]!r}"
        )
        assert lines[1].startswith("approach"), (
            f"Line 2 must start with 'approach', got: {lines[1]!r}"
        )

        result = _join_lines_into_paragraph(lines)

        # Positive assertion: correct join
        assert "agnostic-approach" in result, (
            f"Expected 'agnostic-approach' (no space). Got: {result!r}"
        )
        # Negative assertion: the false positive must not appear
        assert "agnostic- approach" not in result, (
            f"Spurious space still present. Got: {result!r}"
        )

    def test_hyphen_break_uppercase_preserves_space(self):
        """
        NEGATIVE CASE — uppercase continuation after hyphen keeps the space.

        Span layout:
          Line 1 spans: [{"text": "This doctor agnostic-", ...}]
          Line 2 spans: [{"text": "Approach reduces our reliance", ...}]

        "Approach" starts with uppercase → this is NOT a broken compound word.
        A space must remain so the tokens are readable and distinct.

          Expected: "This doctor agnostic- Approach reduces our reliance"
          Wrong:    "This doctor agnostic-Approach reduces our reliance"
        """
        line1_spans = [
            self._make_span("This doctor ", x0=50.0, y0=100.0),
            self._make_span("agnostic-",   x0=122.0, y0=100.0),
        ]
        line2_spans = [
            self._make_span("Approach reduces our reliance", x0=50.0, y0=114.0),
        ]

        all_spans = line1_spans + line2_spans
        lines = _group_spans_to_lines(all_spans, self._LINE_BUCKET)

        assert len(lines) == 2, (
            f"Expected 2 lines, got {len(lines)}: {lines!r}"
        )

        result = _join_lines_into_paragraph(lines)

        # Positive assertion: space preserved before uppercase
        assert "agnostic- Approach" in result, (
            f"Expected 'agnostic- Approach' (space preserved). Got: {result!r}"
        )
        # Negative assertion: must not strip the space
        assert "agnostic-Approach" not in result, (
            f"Space incorrectly removed before uppercase. Got: {result!r}"
        )
