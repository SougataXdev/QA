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
    check_missing_words,
    split_into_sentences,
    find_best_window,
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


# ──────────────────────────────────────────────────────────────────────────────
# check_missing_words — Sentence-aligned architecture regression tests
# ──────────────────────────────────────────────────────────────────────────────

class TestMissingWordsCheck:
    """
    Regression tests for the sentence-aligned local difflib architecture.

    Architecture under test:
      1. split_into_sentences() — regex-based, no NLP libraries
      2. find_best_window()     — rapidfuzz.partial_ratio, order-invariant
      3. check_missing_words()  — local difflib on aligned pairs only

    These tests replace any tests for the old full-document ndiff + reorder
    guard, which was the wrong architecture.
    """

    # ── TEST 1 — Single missing word detected ────────────────────────────────

    def test_single_missing_word_detected(self):
        """
        TEST 1: A single word present in PDF but absent from web is detected.

        PDF: "We deliver high-quality accessible fertility care to all patients."
        Web: same sentence without "high-quality"
        Expected: missing_word issue for "high-quality"
        """
        pdf_text = "We deliver high-quality accessible fertility care to all patients."
        web_text = (
            "Our clinics have been operational for many years across the region. "
            "We deliver accessible fertility care to all patients in our network. "
            "Our dedicated team works tirelessly to improve patient outcomes daily."
        )
        issues = check_missing_words(pdf_text, web_text)
        missing_tokens = [tok for issue in issues if issue["type"] == "missing_word" for tok in issue["missing_tokens"]]
        assert "high-quality" in missing_tokens, (
            f"Single missing word 'high-quality' was not detected. Issues: {issues}"
        )

    # ── TEST 2 — Multiple missing words detected ─────────────────────────────

    def test_multiple_missing_words_detected(self):
        """
        TEST 2: Multiple words present in PDF but absent from web are all detected.

        PDF: "Our continued commitment to quality healthcare values drives all decisions."
        Web: same sentence without "continued" and "quality"
        Expected: missing_word issues for both "continued" and "quality"
        """
        pdf_text = "Our continued commitment to quality healthcare values drives all decisions."
        web_text = (
            "We have operated for many years with strong values in everything we do. "
            "Our commitment to healthcare values drives all decisions across the organization. "
            "We continue to serve patients every day with precision and genuine care."
        )
        issues = check_missing_words(pdf_text, web_text)
        missing_tokens = [tok for issue in issues if issue["type"] == "missing_word" for tok in issue["missing_tokens"]]
        assert "continued" in missing_tokens, (
            f"'continued' not detected as missing. All missing: {missing_tokens}"
        )
        assert "quality" in missing_tokens, (
            f"'quality' not detected as missing. All missing: {missing_tokens}"
        )

    # ── TEST 3 — Section reorder — no false positive ─────────────────────────

    def test_section_reorder_no_false_positive(self):
        """
        TEST 3: Content present in web but in a different section order must
        produce zero missing_word issues.

        PDF order:     block A then block B
        Website order: block B then block A
        Expected: zero missing_word issues (content is present, just reordered)
        """
        block_a = (
            "We deliver high-quality accessible fertility care to all patients in our network."
        )
        block_b = (
            "Our mission is to provide world-class healthcare services across every community."
        )
        pdf_text = block_a + " " + block_b
        web_text = block_b + " " + block_a  # reversed order

        issues = check_missing_words(pdf_text, web_text)
        assert issues == [], (
            f"False positive from section reorder. issues: {issues}"
        )

    # ── TEST 4 — Section reorder with missing word inside ────────────────────

    def test_section_reorder_with_missing_word_inside(self):
        """
        TEST 4: Section reordering is handled architecturally, AND a genuinely
        missing word inside the reordered section is still detected.

        PDF order:     block A then block B (with "world-class")
        Website order: block B first (without "world-class") then block A
        Expected: missing_word issue for "world-class" despite the reorder
        """
        block_a = (
            "We deliver high-quality accessible fertility care to all patients in our network."
        )
        block_b_pdf = (
            "Our mission is to provide world-class healthcare services across every community."
        )
        block_b_web = (
            "Our mission is to provide healthcare services across every community."
        )
        pdf_text = block_a + " " + block_b_pdf
        web_text = block_b_web + " " + block_a  # B (without word) first, then A

        issues = check_missing_words(pdf_text, web_text)
        missing_tokens = [tok for issue in issues if issue["type"] == "missing_word" for tok in issue["missing_tokens"]]
        assert "world-class" in missing_tokens, (
            f"'world-class' was not detected despite section reorder. "
            f"Issues: {issues}"
        )

    # ── TEST 5 — Sentence below 70% match — not raised as missing word ───────

    def test_sentence_below_70_percent_not_raised_as_missing_word(self):
        """
        TEST 5: A PDF sentence not found on the website at all (score < 70%)
        must NOT be raised as a missing_word issue.
        Missing paragraphs are handled by Check 4 (rapidfuzz per paragraph).
        Check 3 must not duplicate that responsibility.

        Expected: zero missing_word issues
        """
        pdf_text = (
            "This clinical governance section was only included in the annual report document."
        )
        web_text = (
            "Our organization has been serving diverse patients across multiple states for many years. "
            "We are committed to improving healthcare access for all communities we serve. "
            "Our teams work hard every day to deliver excellent care to every patient."
        )
        issues = check_missing_words(pdf_text, web_text)
        assert issues == [], (
            f"Sentence with score < 70% was raised as missing_word "
            f"(should be Check 4 only). Issues: {issues}"
        )

    # ── TEST 6 — Perfect match — no issue ────────────────────────────────────

    def test_perfect_match_no_issue(self):
        """
        TEST 6: A PDF sentence that appears identically on the website must
        produce zero issues.

        Expected: zero issues
        """
        sentence = "We deliver high-quality accessible fertility care to all patients."
        pdf_text = sentence
        web_text = (
            "Our clinics serve many patients across the region every single day. "
            + sentence
            + " Our teams are dedicated to excellence in healthcare."
        )
        issues = check_missing_words(pdf_text, web_text)
        assert issues == [], (
            f"Perfect match produced an issue: {issues}"
        )

    # ── TEST 7 — Sentence splitter — decimal protection ──────────────────────

    def test_sentence_splitter_decimal_protection(self):
        """
        TEST 7: Decimal numbers must not cause sentence splitting.

        "revenues of H1630.58 Crores increased by 9.34% annually"
        The dots in 1630.58 and 9.34 must not trigger a sentence boundary.
        Expected: treated as one sentence, not split at decimal
        """
        text = "revenues of H1630.58 Crores increased by 9.34% annually across all segments."
        sentences = split_into_sentences(text)
        assert len(sentences) == 1, (
            f"Decimal point incorrectly split the sentence. Got: {sentences}"
        )
        assert "1630.58" in sentences[0], "Decimal number was corrupted during protection"
        assert "9.34" in sentences[0], "Decimal number was corrupted during protection"

    # ── TEST 8 — Sentence splitter — abbreviation protection ─────────────────

    def test_sentence_splitter_abbreviation_protection(self):
        """
        TEST 8: Known abbreviations with periods must not cause sentence splitting.

        "Dr. Singh leads our clinical team at Rs. 500 Crores"
        Neither "Dr." nor "Rs." should trigger a sentence boundary split.
        Expected: not split at Dr. or Rs.
        """
        text = "Dr. Singh leads our clinical team managing Rs. 500 Crores in healthcare."
        sentences = split_into_sentences(text)
        assert len(sentences) == 1, (
            f"Abbreviation period incorrectly split the sentence. Got: {sentences}"
        )
        assert "Dr." in sentences[0], "Abbreviation was corrupted"
        assert "Rs." in sentences[0], "Abbreviation was corrupted"

    # ── TEST 9 — Confirmed production case resolved ───────────────────────────

    def test_section_swap_awareness_accessibility_reliability(self):
        """
        TEST 9: Confirmed production case — AWARENESS/ACCESSIBILITY/RELIABILITY
        section order swap between PDF and website.

        PDF order:     AWARENESS → ACCESSIBILITY → RELIABILITY
        Website order: AWARENESS → RELIABILITY → ACCESSIBILITY

        Old architecture (full-document ndiff): ACCESSIBILITY falsely flagged as missing.
        New architecture (sentence-aligned):    zero false positives.

        Expected: zero missing_word issues from section swap
        """
        awareness = (
            "We are deeply committed to raising awareness about our services "
            "and healthcare outreach programs for all patients."
        )
        accessibility = (
            "Our accessibility initiatives ensure every patient can access "
            "quality care affordably across every region we serve."
        )
        reliability = (
            "Reliability is at the core of our healthcare delivery system "
            "and builds lasting patient trust across the nation."
        )
        pdf_text = awareness + " " + accessibility + " " + reliability
        web_text = awareness + " " + reliability + " " + accessibility  # swap

        issues = check_missing_words(pdf_text, web_text)
        assert issues == [], (
            f"False positives from AWARENESS/ACCESSIBILITY/RELIABILITY section swap: {issues}"
        )

    # ── TEST 10 — Currency difference not raised as missing word ─────────────

    def test_currency_difference_not_raised_as_missing_word(self):
        """
        TEST 10: A currency symbol difference (H vs Rs.) must not be raised
        as a missing_word issue by Check 3.

        "revenues of H1630.58 Crores" is 4 words — below the 6-word minimum
        threshold in split_into_sentences(). The splitter discards it.
        Check 3 never processes the fragment.
        The currency difference (H vs Rs. for same numeric value) is the
        responsibility of Check 2 (check_currency_mismatch).

        Expected: zero missing_word issues
        """
        pdf_text = "revenues of H1630.58 Crores"   # 4 words — below 6-word minimum
        web_text = "revenues of Rs. 1630.58 Crores"
        issues = check_missing_words(pdf_text, web_text)
        assert issues == [], (
            f"Currency difference raised as missing_word; should be Check 2 only. "
            f"Issues: {issues}"
        )
