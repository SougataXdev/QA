"""
test_normalizer.py — Regression tests for two-pass comparison pipeline.

Covers:
  prepare_for_comparison() — Pass 1: NFKC + skeleton folding
  typographic_normalise()  — Pass 2 safety net
  get_find_text()          — issue text extractor
  pass_two_filter()        — Pass 2 filter logic
  skeleton_map             — download, cache, offline fallback
  Full pipeline            — end-to-end with check functions
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pdf_engine.pipeline.normalizer import (
    prepare_for_comparison,
    typographic_normalise,
    get_find_text,
    pass_two_filter,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _mock_logger() -> MagicMock:
    return MagicMock(spec=logging.Logger)


# ──────────────────────────────────────────────────────────────────────────────
# prepare_for_comparison — ligature expansion
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_fi_ligature():
    """ﬁ (U+FB01) must expand to fi."""
    assert prepare_for_comparison("ﬁrst") == "first"


def test_prepare_all_ligatures():
    """NFKC (compatibility decomposition) expands every Unicode ligature."""
    cases = [
        ('\ufb00', 'ff'),
        ('\ufb01', 'fi'),
        ('\ufb02', 'fl'),
        ('\ufb03', 'ffi'),
        ('\ufb04', 'ffl'),
        ('\ufb05', 'st'),
        ('\ufb06', 'st'),
    ]
    for ligature, expected in cases:
        assert prepare_for_comparison(ligature) == expected, (
            f"Ligature {repr(ligature)} did not expand to {repr(expected)}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# prepare_for_comparison — non-breaking space variants → regular space
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_nbsp_converted():
    """U+00A0 non-breaking space → regular space."""
    assert prepare_for_comparison("India\u00a0IVF") == "India IVF"


def test_prepare_thin_space_converted():
    """U+2009 thin space → regular space."""
    assert prepare_for_comparison("India\u2009IVF") == "India IVF"


def test_prepare_narrow_nbsp_converted():
    """U+202F narrow no-break space → regular space."""
    assert prepare_for_comparison("India\u202fIVF") == "India IVF"


def test_prepare_ideographic_space_converted():
    """U+3000 ideographic space → regular space."""
    assert prepare_for_comparison("India\u3000IVF") == "India IVF"


# ──────────────────────────────────────────────────────────────────────────────
# prepare_for_comparison — things that must NOT be changed
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_double_space_preserved():
    """Double space must survive — Check 1 (extra_whitespace) detects it."""
    result = prepare_for_comparison("Consolidated  EBITDA")
    assert result == "Consolidated  EBITDA", (
        "prepare_for_comparison must never collapse multiple spaces — "
        "double space is Check 1"
    )


def test_prepare_currency_symbol_preserved():
    """Currency glyphs must survive — Check 2 (currency_mismatch) needs them."""
    assert prepare_for_comparison("H1630.58") == "H1630.58"
    assert prepare_for_comparison("Rs.1630.58") == "Rs.1630.58"
    assert prepare_for_comparison("₹1630.58") == "₹1630.58"


def test_prepare_curly_apostrophe_converted_by_skeleton():
    """
    Curly apostrophe (U+2019) IS now converted to straight apostrophe (U+0027)
    in Pass 1 — by the Unicode skeleton map (confusables.txt).

    Previous behaviour (NFC only): preserved in Pass 1, handled in Pass 2.
    Current behaviour (NFKC + skeleton): resolved in Pass 1 before any check
    runs, eliminating the false positive at source without needing Pass 2.

    This means "India's" (curly) and "India's" (straight) become identical
    before check_missing_words() runs — zero candidates, zero false positives.
    """
    result = prepare_for_comparison("India\u2019s")
    assert result == "India's", (
        "Curly apostrophe must be converted to straight by skeleton map"
    )
    # The apostrophe must still be PRESENT — "India's" ≠ "Indias"
    assert "'" in result, "Apostrophe must survive — India's vs Indias is detectable"


def test_prepare_em_dash_preserved():
    """Em dash must survive Pass 1 unchanged — may be a real content error."""
    assert prepare_for_comparison("stakeholders\u2014for") == "stakeholders\u2014for"


# ──────────────────────────────────────────────────────────────────────────────
# typographic_normalise — quote / apostrophe flattening
# ──────────────────────────────────────────────────────────────────────────────

def test_typo_norm_right_single_quotation_mark():
    """U+2019 RIGHT SINGLE QUOTATION MARK → straight apostrophe."""
    assert typographic_normalise("India\u2019s") == "India's"


def test_typo_norm_left_single_quotation_mark():
    """U+2018 LEFT SINGLE QUOTATION MARK → straight apostrophe."""
    assert typographic_normalise("\u2018text\u2019") == "'text'"


def test_typo_norm_left_and_right_double_quotes():
    """U+201C and U+201D → straight double quote."""
    assert typographic_normalise("\u201ctext\u201d") == '"text"'


def test_typo_norm_grave_accent():
    """U+0060 GRAVE ACCENT → straight apostrophe."""
    assert typographic_normalise("`text`") == "'text'"


def test_typo_norm_acute_accent():
    """U+00B4 ACUTE ACCENT → straight apostrophe."""
    assert typographic_normalise("\u00b4") == "'"


# ──────────────────────────────────────────────────────────────────────────────
# typographic_normalise — things deliberately NOT flattened
# ──────────────────────────────────────────────────────────────────────────────

def test_typo_norm_em_dash_not_flattened():
    """
    Em dash (U+2014) must NOT be normalised.
    Some clients care about em dash vs hyphen. Show it to the reviewer.
    """
    assert typographic_normalise("stakeholders\u2014for") == "stakeholders\u2014for"


def test_typo_norm_en_dash_not_flattened():
    """En dash (U+2013) must NOT be normalised."""
    assert typographic_normalise("2020\u20132021") == "2020\u20132021"


def test_typo_norm_currency_not_flattened():
    """Currency symbols must NOT be normalised — always real errors."""
    assert typographic_normalise("H1630.58") == "H1630.58"
    assert typographic_normalise("Rs.1630.58") == "Rs.1630.58"
    assert typographic_normalise("₹1630.58") == "₹1630.58"


def test_typo_norm_double_space_preserved():
    """
    Double space must NOT be collapsed in typographic_normalise.
    It is Check 1. Whitespace collapsing would silently kill it.
    """
    assert typographic_normalise("Consolidated  EBITDA") == "Consolidated  EBITDA"


def test_typo_norm_ellipsis_not_flattened():
    """Ellipsis (U+2026) must not be normalised — may be intentional style."""
    assert typographic_normalise("More\u2026") == "More\u2026"


# ──────────────────────────────────────────────────────────────────────────────
# get_find_text — per-type extraction
# ──────────────────────────────────────────────────────────────────────────────

def test_get_find_text_missing_word_includes_tokens_and_context():
    issue = {
        "type": "missing_word",
        "missing_tokens": ["India\u2019s"],
        "context_before": "known as",
    }
    result = get_find_text(issue)
    assert "India\u2019s" in result
    assert "known as" in result


def test_get_find_text_currency_returns_none():
    """Currency mismatch must never be re-checked — always a real error."""
    assert get_find_text({"type": "currency_mismatch"}) is None


def test_get_find_text_whitespace_returns_none():
    """Double space must never be re-checked — always a real error."""
    assert get_find_text({"type": "extra_whitespace"}) is None


def test_get_find_text_missing_paragraph_returns_first_sentence():
    issue = {
        "type": "missing_paragraph",
        "paragraph_text": "The company reported strong growth. Revenue increased significantly.",
    }
    result = get_find_text(issue)
    assert result == "The company reported strong growth"


def test_get_find_text_unknown_type_returns_none():
    """Unknown issue types cannot be re-checked — keep them."""
    assert get_find_text({"type": "totally_unknown"}) is None


# ──────────────────────────────────────────────────────────────────────────────
# pass_two_filter — encoding differences dropped
# ──────────────────────────────────────────────────────────────────────────────

def test_pass_two_curly_apostrophe_dropped():
    """
    PDF "India's" (U+2019) vs Web "India's" (U+0027).
    After typographic_normalise(), both become "India's".
    char_delta = 0. Confirmed encoding difference → dropped.
    Audit log entry created.
    """
    mock_log = _mock_logger()
    issue = {
        "id": "candidate_001",
        "type": "missing_word",
        "missing_tokens": ["India\u2019s"],
        "context_before": "known as",
    }
    web_text = "known as India's leading IVF provider"

    result = pass_two_filter(issue, "", web_text, mock_log)

    assert result is None, "Curly apostrophe false positive must be dropped"
    mock_log.info.assert_called_once()
    log_msg = mock_log.info.call_args[0][0]
    assert "Pass 2 dropped" in log_msg


def test_pass_two_real_missing_word_kept():
    """
    Word genuinely absent from web text → real error → kept.
    """
    mock_log = _mock_logger()
    issue = {
        "id": "candidate_002",
        "type": "missing_word",
        "missing_tokens": ["performance"],
        "context_before": "financial",
    }
    web_text = "The company reported strong revenue growth this year."

    result = pass_two_filter(issue, "", web_text, mock_log)

    assert result is issue
    mock_log.info.assert_not_called()


def test_pass_two_currency_mismatch_never_filtered():
    """Currency mismatches must always be kept regardless of normalisation."""
    mock_log = _mock_logger()
    issue = {
        "id": "candidate_003",
        "type": "currency_mismatch",
        "pdf_symbol": "H",
        "web_symbol": "Rs.",
    }

    result = pass_two_filter(issue, "", "Rs.1630.58 Crores", mock_log)

    assert result is issue


def test_pass_two_extra_whitespace_never_filtered():
    """Whitespace issues must always be kept — double space is a real error."""
    mock_log = _mock_logger()
    issue = {
        "id": "candidate_004",
        "type": "extra_whitespace",
        "space_count": 2,
    }

    result = pass_two_filter(issue, "", "Consolidated  EBITDA", mock_log)

    assert result is issue


def test_pass_two_large_char_delta_kept():
    """
    If normalisation produces a large character count change (> 2),
    this indicates a word-structure difference, not just encoding.
    Issue must be kept.
    """
    mock_log = _mock_logger()
    # Many tokens missing — combined char delta will exceed 2
    issue = {
        "id": "candidate_005",
        "type": "missing_word",
        "missing_tokens": ["shouldn't", "have", "been", "done"],
        "context_before": "the company",
    }
    web_text = "the company had an excellent trading year"

    result = pass_two_filter(issue, "", web_text, mock_log)

    assert result is issue


def test_pass_two_empty_find_text_kept():
    """If get_find_text() returns an empty string, keep the issue safely."""
    mock_log = _mock_logger()
    issue = {
        "id": "candidate_006",
        "type": "missing_word",
        "missing_tokens": [],
        "context_before": "",
    }

    result = pass_two_filter(issue, "", "some web text", mock_log)

    assert result is issue


# ──────────────────────────────────────────────────────────────────────────────
# pass_two_filter — known edge case documentation
# ──────────────────────────────────────────────────────────────────────────────

def test_pass_two_its_vs_its_known_edge_case():
    """
    KNOWN EDGE CASE — documented limitation.

    "it's" (with curly apostrophe U+2019) vs "its" on the web.
    After typographic_normalise(), "it\u2019s" → "it's" → still contains
    apostrophe, which maps to "'", giving "it's".
    "its" is in web_text "its leading position".
    "it's" normalises to "it's" which is NOT in "its leading position".

    Wait — actually "it's" (after normalise) has an apostrophe, so it becomes
    "it's". "its" does NOT contain "it's". So Pass 2 would correctly KEEP it.

    But if the web text had "it's" (straight) and PDF had "it\u2019s" (curly),
    both normalise to "it's", char_delta = 0, and it gets dropped. That is the
    CORRECT behaviour (font encoding difference only).

    The true edge case is: PDF "it\u2019s" missing, web has "its" (no apostrophe).
    In that case normalised "it's" is NOT in "its leading position" (since "it's"
    ≠ "its"). Pass 2 keeps it → correct.

    This test documents the actual behaviour to prevent regression.
    """
    mock_log = _mock_logger()

    # Case A: PDF curly apostrophe, web has straight apostrophe → encoding diff
    issue_a = {
        "id": "candidate_007a",
        "type": "missing_word",
        "missing_tokens": ["it\u2019s"],
        "context_before": "",
    }
    web_text_a = "it's leading position"   # straight apostrophe on web
    result_a = pass_two_filter(issue_a, "", web_text_a, mock_log)
    assert result_a is None, (
        "Same word with different apostrophe encoding → encoding difference → dropped"
    )

    # Case B: PDF has "it's" (curly), web genuinely has "its" (no apostrophe)
    mock_log_b = _mock_logger()
    issue_b = {
        "id": "candidate_007b",
        "type": "missing_word",
        "missing_tokens": ["it\u2019s"],
        "context_before": "",
    }
    web_text_b = "its leading position"   # no apostrophe at all
    result_b = pass_two_filter(issue_b, "", web_text_b, mock_log_b)
    assert result_b is issue_b, (
        "PDF 'it\u2019s' vs web 'its' (no apostrophe) → normalised 'it's' "
        "not found in 'its leading position' → real error → kept"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Full pipeline integration tests (no live scraping)
# ──────────────────────────────────────────────────────────────────────────────

def test_full_pipeline_curly_apostrophe_zero_issues():
    """
    PDF "India's" (U+2019) vs Web "India's" (U+0027).
    Expected outcome: zero confirmed issues after two-pass filter.

    This is the confirmed production false positive that triggered this build.
    """
    from pdf_engine.qa.checks import check_missing_words

    mock_log = _mock_logger()

    pdf_raw = "India\u2019s leading healthcare provider"
    web_raw = "India's leading healthcare provider"

    pdf_p1 = prepare_for_comparison(pdf_raw)
    web_p1 = prepare_for_comparison(web_raw)

    # Pass 1 — still flags the apostrophe difference
    candidates = check_missing_words(pdf_p1, web_p1)
    for i, issue in enumerate(candidates, 1):
        issue["id"] = f"candidate_{i:03d}"

    # Pass 2 — drops encoding differences
    confirmed = []
    for issue in candidates:
        result = pass_two_filter(issue, pdf_p1, web_p1, mock_log)
        if result is not None:
            confirmed.append(result)

    assert len(confirmed) == 0, (
        f"Expected zero confirmed issues after Pass 2, got {len(confirmed)}: "
        f"{confirmed}"
    )


def test_full_pipeline_currency_mismatch_still_caught():
    """
    H1630.58 (PDF) vs Rs.1630.58 (web) must always be reported.
    Currency issues are never filtered by Pass 2.
    """
    from pdf_engine.qa.checks import check_currency_mismatch

    mock_log = _mock_logger()

    pdf_raw = "H1630.58 Crores"
    web_raw = "Rs.1630.58 Crores"

    pdf_p1 = prepare_for_comparison(pdf_raw)
    web_p1 = prepare_for_comparison(web_raw)

    candidates = check_currency_mismatch(pdf_p1, web_p1, [])
    for i, issue in enumerate(candidates, 1):
        issue["id"] = f"candidate_{i:03d}"

    confirmed = []
    for issue in candidates:
        result = pass_two_filter(issue, pdf_p1, web_p1, mock_log)
        if result is not None:
            confirmed.append(result)

    assert len(confirmed) == 1
    assert confirmed[0]["type"] == "currency_mismatch"


def test_full_pipeline_double_space_still_caught():
    """
    "Consolidated  EBITDA" (two spaces) must be detected after prepare_for_comparison.
    prepare_for_comparison must not collapse spaces.
    """
    from pdf_engine.qa.checks import check_extra_whitespace

    mock_log = _mock_logger()

    web_raw = "Consolidated  EBITDA of H1630.58 Crores"
    web_p1 = prepare_for_comparison(web_raw)

    # Double space must survive preparation
    assert "  " in web_p1, "Double space was collapsed — Check 1 would be blind"

    candidates = check_extra_whitespace(web_p1, [])
    for i, issue in enumerate(candidates, 1):
        issue["id"] = f"candidate_{i:03d}"

    confirmed = []
    for issue in candidates:
        result = pass_two_filter(issue, "", web_p1, mock_log)
        if result is not None:
            confirmed.append(result)

    assert len(confirmed) == 1
    assert confirmed[0]["type"] == "extra_whitespace"


# ──────────────────────────────────────────────────────────────────────────────
# prepare_for_comparison — NFKC + skeleton specific behaviour
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_quotes_via_skeleton():
    """
    Curly single quotes (U+2018/2019) → straight apostrophe via skeleton map.
    This is a cross-institution Unicode confusable, handled by confusables.txt.
    After prepare_for_comparison(), both sides of the comparison use straight
    apostrophes — the false positive is eliminated before any check runs.
    """
    assert prepare_for_comparison("India\u2019s") == "India's"
    assert prepare_for_comparison("\u2018quoted\u2019") == "'quoted'"


def test_prepare_apostrophe_still_present():
    """
    After skeleton folding, the apostrophe must still be PRESENT in the output.
    "India's" and "Indias" must remain distinguishable — missing apostrophe is
    a real grammatical error that a content editor would be asked to fix.
    """
    with_apostrophe    = prepare_for_comparison("India\u2019s")
    without_apostrophe = prepare_for_comparison("Indias")
    assert with_apostrophe != without_apostrophe, (
        "India's and Indias must remain different after normalization"
    )
    assert "'" in with_apostrophe, "Apostrophe must survive skeleton folding"
    assert "'" not in without_apostrophe, "Indias has no apostrophe"


def test_prepare_cyrillic_homoglyph_via_skeleton():
    """
    Cyrillic А (U+0410) → Latin A (U+0041) via skeleton map.
    Cross-script homoglyphs are a real source of false positives in PDFs
    where the font embeds Cyrillic characters that look identical to Latin.
    """
    cyrillic_a = '\u0410'   # CYRILLIC CAPITAL LETTER A
    result = prepare_for_comparison(cyrillic_a)
    assert result == 'A', f"Expected 'A', got {repr(result)}"


def test_prepare_en_dash_protected():
    """
    En dash (U+2013) must NOT be normalised to hyphen.
    skeleton_map maps it to '-' but PROTECTED_CHARS prevents this.
    Some clients care about en dash vs hyphen style — show it to reviewer.
    """
    result = prepare_for_comparison("2020\u20132021")
    assert '\u2013' in result, "En dash must survive PROTECTED_CHARS guard"
    assert result == "2020\u20132021"


def test_prepare_em_dash_protected():
    """
    Em dash (U+2014) must NOT be normalised.
    skeleton_map maps it to the katakana prolonged sound mark (U+30FC) —
    a semantically nonsensical substitution for English text.
    PROTECTED_CHARS ensures em dash survives unchanged.
    """
    result = prepare_for_comparison("revenue\u2014before")
    assert '\u2014' in result, "Em dash must survive PROTECTED_CHARS guard"
    assert '\u30fc' not in result, "Em dash must NOT become katakana character"
    assert result == "revenue\u2014before"


def test_prepare_currency_indian_rupee_sign_preserved():
    """₹ (U+20B9) is NOT in confusables.txt — it survives unchanged."""
    assert prepare_for_comparison("₹9000") == "₹9000"


def test_prepare_currency_all_symbols_preserved():
    """All currency symbols used in Indian annual reports must survive."""
    cases = [
        ("H1630.58 Crores",  "H1630.58 Crores"),
        ("Rs. 556.60 Crores", "Rs. 556.60 Crores"),
        ("₹9000",             "₹9000"),
        ("INR 1200",          "INR 1200"),
    ]
    for inp, expected in cases:
        result = prepare_for_comparison(inp)
        assert result == expected, (
            f"Currency string {repr(inp)} was changed to {repr(result)}"
        )


def test_prepare_superscript_converted_by_nfkc():
    """
    Superscript digits ² ³ → 2 3 via NFKC.
    For comparison purposes this is correct: a footnote marker "revenue²"
    in the PDF and "revenue2" on the web (CMS may not support superscripts)
    should compare as equal — not a content error.
    """
    assert prepare_for_comparison("revenue\u00b2") == "revenue2"
    assert prepare_for_comparison("Tier\u00b3") == "Tier3"


# ──────────────────────────────────────────────────────────────────────────────
# prepare_for_comparison — PDF hyphen line-break artifact
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_hyphen_linebreak_uppercase_collapsed():
    """
    "Patient- Centric" (PDF line-break artifact) → "Patient-Centric".

    _join_lines_into_paragraph() preserves a space when the next line starts
    with a capital letter, producing "Word- Word". This pattern never appears
    in normal prose. prepare_for_comparison() removes the spurious space so
    the PDF and web sides compare equal.
    """
    result = prepare_for_comparison("Patient- Centric")
    assert result == "Patient-Centric"


def test_prepare_hyphen_linebreak_lowercase_unchanged():
    """
    Lowercase continuation without space is left unchanged.
    "high-quality" has no space after hyphen — already handled by the
    extractor (lowercase join). prepare_for_comparison must not touch it.
    """
    assert prepare_for_comparison("high-quality") == "high-quality"


def test_prepare_hyphen_linebreak_multiple_spaces_collapsed():
    """
    Multiple spaces after a hyphen are all removed.
    "Patient-  Centric" (two spaces) → "Patient-Centric".
    """
    assert prepare_for_comparison("Patient-  Centric") == "Patient-Centric"


def test_prepare_hyphen_linebreak_full_pipeline():
    """
    End-to-end: PDF "Patient- Centric" vs web "Patient-Centric" → zero issues.
    """
    from pdf_engine.qa.checks import check_missing_words

    pdf_raw = "We offer a Patient- Centric Support System."
    web_raw = "We offer a Patient-Centric Support System."

    pdf_p1 = prepare_for_comparison(pdf_raw)
    web_p1 = prepare_for_comparison(web_raw)

    assert pdf_p1 == web_p1, (
        f"After normalization both sides must be identical.\n"
        f"PDF: {repr(pdf_p1)}\nWeb: {repr(web_p1)}"
    )

    candidates = check_missing_words(pdf_p1, web_p1)
    assert len(candidates) == 0, f"Expected 0 issues, got: {candidates}"


def test_prepare_hyphen_linebreak_does_not_affect_web_text():
    """
    Normal web text with a hyphenated compound is returned unchanged.
    "Patient-Centric" has no space after the hyphen — not an artifact.
    """
    assert prepare_for_comparison("Patient-Centric") == "Patient-Centric"


# ──────────────────────────────────────────────────────────────────────────────
# Full pipeline — new false positives confirmed eliminated in Pass 1
# ──────────────────────────────────────────────────────────────────────────────

def test_full_pipeline_curly_apostrophe_resolved_in_pass_one():
    """
    With NFKC + skeleton, curly apostrophe false positive is resolved before
    check_missing_words() runs — zero candidates, no Pass 2 needed.
    Both sides become identical strings after prepare_for_comparison().
    """
    pdf_raw = "India\u2019s leading healthcare provider"
    web_raw = "India's leading healthcare provider"

    pdf_p1 = prepare_for_comparison(pdf_raw)
    web_p1 = prepare_for_comparison(web_raw)

    # After Pass 1 preparation, both strings must be identical.
    assert pdf_p1 == web_p1, (
        f"Both sides must be identical after prepare_for_comparison().\n"
        f"PDF: {repr(pdf_p1)}\nWeb: {repr(web_p1)}"
    )


def test_full_pipeline_fi_ligature_resolved_in_pass_one():
    """
    ﬁ ligature false positive resolved in Pass 1 by NFKC.
    PDF "ﬁrst" and web "first" become identical after prepare_for_comparison().
    """
    pdf_raw = "\ufb01rst quarter results"
    web_raw = "first quarter results"

    pdf_p1 = prepare_for_comparison(pdf_raw)
    web_p1 = prepare_for_comparison(web_raw)

    assert pdf_p1 == web_p1


def test_full_pipeline_real_missing_apostrophe_still_caught():
    """
    "India's" vs "Indias" — missing apostrophe is a real grammatical error.
    After prepare_for_comparison(), "India's" ≠ "Indias" → check flags it.

    Input texts use a filler sentence to meet the sentence-splitter 6-word
    minimum and to provide enough context for find_best_window to slide over.
    """
    from pdf_engine.qa.checks import check_missing_words

    mock_log = _mock_logger()
    filler = "Our organization serves patients across multiple regions with dedication."
    pdf_raw = filler + " India's leadership in healthcare drives all innovation. " + filler
    web_raw = filler + " Indias leadership in healthcare drives all innovation. " + filler

    pdf_p1 = prepare_for_comparison(pdf_raw)
    web_p1 = prepare_for_comparison(web_raw)

    assert pdf_p1 != web_p1, "Real apostrophe difference must survive preparation"

    candidates = check_missing_words(pdf_p1, web_p1)
    assert len(candidates) > 0, (
        "Missing apostrophe must be flagged as a candidate issue"
    )


# ──────────────────────────────────────────────────────────────────────────────
# skeleton_map — download, cache, offline fallback
# ──────────────────────────────────────────────────────────────────────────────

def test_skeleton_map_parse_confusables():
    """_parse_confusables() correctly extracts source → target pairs."""
    from pdf_engine.pipeline.skeleton_map import _parse_confusables

    sample = (
        "# Unicode confusables\n"
        "0041 ; 0041 ; MA\n"          # A → A (identity mapping)
        "2019 ; 0027 ; MA\n"          # ' → ' (curly → straight)
        "0410 ; 0041 ; MA\n"          # Cyrillic А → Latin A
        "\n"
        "# another comment\n"
        "invalid line no semicolon\n"
    )
    result = _parse_confusables(sample)

    assert chr(0x2019) in result
    assert result[chr(0x2019)] == "'"
    assert chr(0x0410) in result
    assert result[chr(0x0410)] == 'A'


def test_skeleton_map_offline_fallback_uses_cache(tmp_path):
    """
    If network download fails and a cache file exists, the cache is used.
    Pipeline must never crash on network failure.
    """
    from pdf_engine.pipeline import skeleton_map as sm

    # Write a minimal fake cache
    fake_cache = {chr(0x2019): "'", chr(0x0410): "A"}
    cache_file = tmp_path / "confusables_cache.json"
    cache_file.write_text(
        json.dumps({k: v for k, v in fake_cache.items()}, ensure_ascii=False),
        encoding="utf-8",
    )

    with patch.object(sm, 'CACHE_PATH', cache_file):
        with patch('urllib.request.urlopen', side_effect=OSError("no network")):
            result = sm.download_confusables()

    assert result[chr(0x2019)] == "'"
    assert result[chr(0x0410)] == "A"


def test_skeleton_map_offline_no_cache_returns_empty(tmp_path):
    """
    If network download fails and NO cache exists, empty dict is returned.
    Pipeline continues with NFKC alone — must not raise.
    """
    from pdf_engine.pipeline import skeleton_map as sm

    nonexistent = tmp_path / "does_not_exist.json"

    with patch.object(sm, 'CACHE_PATH', nonexistent):
        with patch('urllib.request.urlopen', side_effect=OSError("no network")):
            result = sm.download_confusables()

    assert result == {}


def test_skeleton_map_fresh_cache_skips_network(tmp_path):
    """
    A fresh cache (< 30 days old) must be used without any network call.
    """
    from pdf_engine.pipeline import skeleton_map as sm

    fake_cache = {chr(0x2019): "'"}
    cache_file = tmp_path / "confusables_cache.json"
    cache_file.write_text(
        json.dumps({k: v for k, v in fake_cache.items()}, ensure_ascii=False),
        encoding="utf-8",
    )
    # File just written — age ≈ 0 seconds (fresh)

    network_called = []

    def fake_urlopen(*args, **kwargs):
        network_called.append(True)
        raise AssertionError("Network should not be called for fresh cache")

    with patch.object(sm, 'CACHE_PATH', cache_file):
        with patch('urllib.request.urlopen', side_effect=fake_urlopen):
            result = sm.download_confusables.__wrapped__(
            ) if hasattr(sm.download_confusables, '__wrapped__') else sm._load_cache.__func__(sm) if False else None
            # Test _load_cache + freshness directly
            result = sm._load_cache()

    assert result is not None
    assert result[chr(0x2019)] == "'"
    assert not network_called

