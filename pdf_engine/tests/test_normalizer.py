"""
test_normalizer.py — Regression tests for two-pass comparison pipeline.

Covers:
  prepare_for_comparison() — Pass 1 preparation
  typographic_normalise()  — Pass 2 aggressive normalisation
  get_find_text()          — issue text extractor
  pass_two_filter()        — Pass 2 filter logic
  Full pipeline            — end-to-end with check functions
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

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
    """Every ligature in LIGATURE_MAP must expand to its ASCII form."""
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


def test_prepare_curly_apostrophe_preserved():
    """
    Curly apostrophe (U+2019) must NOT be flattened in Pass 1.
    Pass 2 handles it. If we flattened here, Pass 2 could never
    distinguish it from a real word-structure error.
    """
    result = prepare_for_comparison("India\u2019s")
    assert result == "India\u2019s"


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


def test_get_find_text_extra_paragraph_returns_first_sentence():
    issue = {
        "type": "extra_paragraph",
        "paragraph_text": "This paragraph is extra. With more content here.",
    }
    result = get_find_text(issue)
    assert result == "This paragraph is extra"


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
