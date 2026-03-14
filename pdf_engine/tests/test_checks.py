"""
tests/test_checks.py — Currency mismatch check regression tests.

Covers the confirmed false positive where ordinary English words containing
letter sequences that match currency prefixes (case-insensitively, mid-word)
were incorrectly extracted as currency figures.

False positive confirmed in production:
  "The PDF uses 'h' but the website uses 'rs'"
  The word "shareholders" (and similar) triggered the old pattern because:
  - re.IGNORECASE made lowercase 'h' and 'rs' match currency prefixes
  - No word-boundary anchors allowed mid-word matches
  - H(?=[\\d\\s,]) included \\s in the lookahead, enabling "h " to match
"""

from __future__ import annotations

import pytest

from pdf_engine.qa.checks import (
    _extract_figures,
    _CURRENCY_PATTERN,
    check_currency_mismatch,
)


# ──────────────────────────────────────────────────────────────────────────────
# _extract_figures — Pattern precision
# ──────────────────────────────────────────────────────────────────────────────

class TestCurrencyPatternFalsePositives:
    """
    Regression: ordinary words must never produce currency figure matches.

    The old re.IGNORECASE pattern matched 'rs' in "shareholders" and 'h'
    in any word containing that letter. These tests pin the fix so it cannot
    silently regress.
    """

    def test_shareholders_produces_zero_matches(self):
        """
        Regression (confirmed production false positive):
        "shareholders" must not produce any currency figure match.
        Old pattern with IGNORECASE matched 'rs' at the end of the word.
        """
        # Regression: confirmed false positive — "rs" in "shareholders"
        assert _extract_figures("shareholders") == []

    def test_shareholders_followed_by_number_no_match(self):
        """
        Regression: even when "shareholders" is followed by a number,
        the number must not be attributed to a currency prefix inside the word.
        """
        # Regression: "shareholde[rs] 1,234 Crores" — 'rs' + digits = false prefix
        assert _extract_figures("shareholders 1,234 Crores") == []
        assert _extract_figures("shareholders hold 1234 assets") == []

    def test_partners_produces_zero_matches(self):
        """'partners' ends in 'rs' — must not match Rs prefix."""
        assert _extract_figures("partners") == []

    def test_directors_produces_zero_matches(self):
        """'directors' ends in 'rs' — must not match Rs prefix."""
        assert _extract_figures("directors") == []

    def test_lowercase_h_in_word_no_match(self):
        """
        Regression: lowercase 'h' in any English word must not match
        the H (rupee glyph) prefix. Old IGNORECASE allowed this.
        """
        # Regression: 'h' in ordinary words matched as H currency prefix
        assert _extract_figures("shareholders hold the shares") == []
        assert _extract_figures("h shares outstanding") == []
        assert _extract_figures("the highlight of") == []

    def test_lowercase_rs_no_match(self):
        """
        Regression: 'rs' in lowercase must never match as Rs currency prefix.
        The ITFRupee/PDF context always uses capital R.
        """
        # Regression: case-insensitive match allowed lowercase 'rs' as prefix
        assert _extract_figures("rs.1234 Crores") == []
        assert _extract_figures("rs 1234") == []

    def test_lowercase_h_before_digits_no_match(self):
        """
        Regression: lowercase 'h1234' must not match. Only uppercase H
        (the ITFRupee glyph from PyMuPDF output) is a valid rupee prefix.
        """
        # Regression: IGNORECASE made 'h1234' fire as a currency match
        assert _extract_figures("h1234") == []
        assert _extract_figures("sh1234") == []

    def test_mid_word_h_no_match(self):
        """
        H embedded mid-word (no preceding word boundary) must not match.
        The \\b anchor prevents this.
        """
        # 'H' preceded by a word char has no \\b before it
        assert _extract_figures("theH1234") == []
        assert _extract_figures("eachH1630") == []

    def test_single_digit_h_no_match(self):
        """
        Rule 4 — Minimum 2 digits: 'H5' must not match.
        A single-digit amount is almost certainly a false positive
        from context like "Figure H, table 5" or similar.
        """
        # Regression guard: H5 or Rs.3 should not produce a figure
        assert _extract_figures("H5") == []
        assert _extract_figures("Rs.3") == []

    def test_cash_and_equivalents_no_match(self):
        """Common balance-sheet phrase must produce no currency matches."""
        assert _extract_figures("Cash and cash equivalents") == []
        assert _extract_figures("cash 40 units") == []


# ──────────────────────────────────────────────────────────────────────────────
# _extract_figures — True positives must still work
# ──────────────────────────────────────────────────────────────────────────────

class TestCurrencyPatternTruePositives:
    """
    Confirm that real currency figures are still detected after the fix.
    The false-positive fix must not break legitimate currency extraction.
    """

    def test_uppercase_h_prefix_detected(self):
        """H (ITFRupee glyph, always uppercase in PyMuPDF) must match."""
        result = _extract_figures("H1630")
        assert len(result) == 1
        assert result[0]["prefix"] == "H"
        assert result[0]["number"] == "1630"

    def test_uppercase_h_with_commas_and_crores(self):
        """
        Real production value: H1,630.58 Crores must match correctly.
        Comma-separated thousands must be handled without breaking the match.
        """
        # This was the case failing after the first lookahead fix attempt
        result = _extract_figures("H1,630.58 Crores")
        assert len(result) == 1
        assert result[0]["prefix"] == "H"
        assert result[0]["number"] == "1630.58"
        assert result[0]["unit"] == "Crores"

    def test_rs_dot_prefix(self):
        """Rs. prefix (with dot) must match."""
        result = _extract_figures("Rs.556.60 Crores")
        assert len(result) == 1
        assert result[0]["prefix"] == "Rs."
        assert result[0]["number"] == "556.60"

    def test_rs_no_dot_prefix(self):
        """Rs prefix (no dot) must match."""
        result = _extract_figures("Rs 900")
        assert len(result) == 1
        assert result[0]["prefix"] == "Rs"

    def test_rupee_symbol_prefix(self):
        """₹ (Unicode rupee sign) must match."""
        result = _extract_figures("₹9000")
        assert len(result) == 1
        assert result[0]["prefix"] == "₹"
        assert result[0]["number"] == "9000"

    def test_rupee_symbol_with_space(self):
        """₹ with a space before the number must match."""
        result = _extract_figures("₹ 1,200")
        assert len(result) == 1
        assert result[0]["number"] == "1200"

    def test_inr_prefix(self):
        """INR prefix must match."""
        result = _extract_figures("INR 1200")
        assert len(result) == 1
        assert result[0]["prefix"] == "INR"

    def test_minimum_two_digit_amount(self):
        """H56 (2-digit amount) must match — minimum length threshold passes."""
        result = _extract_figures("H56")
        assert len(result) == 1
        assert result[0]["prefix"] == "H"
        assert result[0]["number"] == "56"

    def test_multiple_figures_in_text(self):
        """Multiple currency figures in the same text are all extracted."""
        text = "Revenue of H1,630 Crores and Rs.556.60 Crores in profit."
        result = _extract_figures(text)
        assert len(result) == 2
        prefixes = {f["prefix"] for f in result}
        assert "H" in prefixes
        assert "Rs." in prefixes


# ──────────────────────────────────────────────────────────────────────────────
# check_currency_mismatch — End-to-end false positive prevention
# ──────────────────────────────────────────────────────────────────────────────

class TestCurrencyMismatchCheck:
    """
    End-to-end tests for Check 2, verifying the full comparison pipeline
    does not produce false positives from ordinary English words.
    """

    def test_shareholders_word_no_false_positive(self):
        """
        Regression (confirmed production bug):
        "shareholders" in both PDF and web text must not trigger a currency
        mismatch issue. The old code reported: "PDF uses 'h', web uses 'rs'".
        """
        # Regression: confirmed production false positive
        pdf_text = "Total shareholders equity of 5,000 units."
        web_text = "shareholders equity and reserve"
        issues = check_currency_mismatch(pdf_text, web_text, [])
        assert issues == [], (
            f"False positive: 'shareholders' triggered currency mismatch.\n"
            f"Issues: {issues}"
        )

    def test_real_mismatch_still_detected(self):
        """
        After the fix, real currency mismatches (H vs Rs. for same value)
        must still be detected — the fix must not suppress real errors.
        """
        # PDF uses H (ITFRupee glyph), web uses Rs. — confirmed mismatch
        pdf_text = "Revenue of H1,630 Crores."
        web_text = "Revenue of Rs.1,630 Crores."
        issues = check_currency_mismatch(pdf_text, web_text, [])
        assert len(issues) == 1, (
            f"Real currency mismatch was not detected after fix.\n"
            f"Issues: {issues}"
        )
        assert issues[0]["pdf_symbol"] == "H"
        assert issues[0]["web_symbol"] == "Rs."
        assert issues[0]["numeric_value"] == "1630"

    def test_matching_currency_symbols_no_issue(self):
        """Same currency prefix on both sides → no issue (not a mismatch)."""
        pdf_text = "Profit: H1,630 Crores"
        web_text = "Profit: H1,630 Crores"
        issues = check_currency_mismatch(pdf_text, web_text, [])
        assert issues == []

    def test_no_currency_in_either_no_issue(self):
        """Text with no currency at all → zero issues."""
        issues = check_currency_mismatch(
            "Operating in 42 countries with strong partnerships.",
            "Operating in 42 countries with strong partners.",
            [],
        )
        assert issues == []

    def test_pattern_is_case_sensitive(self):
        """
        The pattern must not have re.IGNORECASE. Verify by checking that
        lowercase lookalikes do not produce matches.
        """
        import re
        # Pattern flags must NOT include re.IGNORECASE (value 2)
        assert not (_CURRENCY_PATTERN.flags & re.IGNORECASE), (
            "re.IGNORECASE must not be set — it causes mid-word false positives"
        )
