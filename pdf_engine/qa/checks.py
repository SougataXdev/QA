"""
checks.py — All QA checks for the microsite comparison system.

PDF is the single source of truth. Only deviations where the website
is missing or alters PDF content are flagged. Extra web-only content
is not an issue.

Each check returns a list of issue dicts with the structure specified
in the QA prompt. All checks are always run — never skip even if zero results.

Check 1: Extra whitespace (web text only)
Check 2: Currency mismatch (PDF vs web)
Check 3: Missing words (difflib.ndiff, PDF → web direction only)
Check 4: Missing paragraphs (rapidfuzz)
"""

from __future__ import annotations

import difflib
import re
import logging

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Fuzzy match threshold for paragraph checks
MISSING_PARA_THRESHOLD = 80


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _find_section(position: int, web_ready: str, web_sections: list[dict]) -> dict:
    """
    Find which web section a character position belongs to.

    Extracts a 60-char snippet from web_ready at the given position and checks
    which section's captured text contains it. Falls back to first section, then
    a generic location.
    """
    if web_sections:
        snippet = web_ready[max(0, position - 20):position + 40].strip()[:60].lower()
        if snippet:
            for sec in reversed(web_sections):
                if snippet in sec.get("text", "").lower():
                    return {
                        "section": sec["section"],
                        "selector": sec["selector"],
                    }
        # Snippet not found in any section's captured text — fall back to first
        return {
            "section": web_sections[0].get("section", "Page content"),
            "selector": web_sections[0].get("selector", "body"),
        }
    return {
        "section": "Search the website for the first few words of this text.",
        "selector": "body",
    }


# ──────────────────────────────────────────────
# CHECK 1 — Extra Whitespace
# ──────────────────────────────────────────────

def check_extra_whitespace(
    web_ready: str,
    web_sections: list[dict],
) -> list[dict]:
    """
    Scan web text for 2+ consecutive spaces between words.
    Severity: minor.
    """
    issues: list[dict] = []

    for match in re.finditer(r'[ \t]{2,}', web_ready):
        start = match.start()
        context_start = max(0, start - 40)
        context_end = min(len(web_ready), match.end() + 40)
        context = web_ready[context_start:context_end]
        space_count = len(match.group())

        section = _find_section(start, web_ready, web_sections)

        issues.append({
            "type": "extra_whitespace",
            "severity": "minor",
            "title": "Extra space found between words",
            "explanation": (
                f"The website has {space_count} spaces here — "
                f"the PDF has one."
            ),
            "pdf_snippet": re.sub(r'[ \t]{2,}', ' ', context),
            "web_snippet": context,
            "pdf_location": {},
            "web_location": section,
            "space_count": space_count,
            "context_before": web_ready[context_start:match.start()],
            "context_after": web_ready[match.end():context_end],
        })

    logger.info("Check 1 (extra whitespace): %d issues", len(issues))
    return issues


# ──────────────────────────────────────────────
# CHECK 2 — Currency Mismatch
# ──────────────────────────────────────────────

# Currency prefix pattern: Rs. Rs ₹ INR H (H glyph from ITFRupee font)
#
# Rules applied to prevent false positives on ordinary words:
#
#   Rule 1 — Word boundary (\b): every letter-based prefix is anchored so it
#     cannot match mid-word. "shareholde\brs" has no boundary before the 'r'
#     (preceded by 'e', a word char) → \bRs will not fire inside that word.
#
#   Rule 2 — Digit-only lookahead on H with minimum 2 digits: H must be
#     followed immediately by at least 2 digits. The old (?=[\d\s,]) allowed
#     a trailing space, which let the 'h' glyph in ordinary words match
#     (e.g., "cash 40" — 'h' + space + digit). (?=\d{2,}) requires two
#     digits with no intervening space, matching only real rupee amounts.
#
#   Rule 3 — No re.IGNORECASE: H (ITFRupee rupee glyph) is always uppercase
#     in PyMuPDF output. Lowercase 'h' in words like "shareholders", "the",
#     "each" must never match. Rs is always capital-R in currency context;
#     lowercase 'rs' mid-word (e.g., "partners", "directors") must not match.
_CURRENCY_PATTERN = re.compile(
    r'('
    r'\bRs\.?\s*'       # Rule 1: \b blocks "shareholdERS" mid-word match
    r'|₹\s*'            # ₹ is a unique symbol — cannot appear mid-word naturally
    r'|\bINR\s*'        # Rule 1: \b blocks mid-word "inr" sequences
    r'|\bH(?=\d)'      # Rule 1+2: uppercase H, word-boundary, next char must be a digit
    r')'
    r'([\d,]+(?:\.\d+)?)'
    r'(\s*(?:Crores?|Lakhs?|cr\.?|L)?)',
    # Rule 3: no re.IGNORECASE — H and Rs are case-sensitive by design
)


def _extract_figures(text: str) -> list[dict]:
    """Extract currency figures with their prefixes."""
    figures = []
    for m in _CURRENCY_PATTERN.finditer(text):
        # Belt-and-suspenders mid-word guard: even if the regex boundary
        # fires on an unexpected edge case, reject any match where the
        # character immediately before the prefix is a letter.
        # This handles residual cases not caught by \b (e.g. Unicode edge cases).
        start = m.start()
        if start > 0 and text[start - 1].isalpha():
            continue  # prefix is mid-word — not a currency symbol; skip
        prefix = m.group(1).strip()
        number = m.group(2).replace(',', '')
        unit = m.group(3).strip()
        # Rule 4 — Minimum number length: a single-digit "figure" (H5, Rs.3)
        # is almost certainly a false positive. Real currency figures have ≥2
        # digits in the numeric portion. Enforce after comma-stripping.
        digits_only = number.split('.')[0]  # integer part only
        if len(digits_only) < 2:
            continue
        figures.append({
            "prefix": prefix,
            "number": number,
            "unit": unit,
            "original": m.group(0),
            "position": m.start(),
        })
    return figures


def check_currency_mismatch(
    pdf_ready: str,
    web_ready: str,
    web_sections: list[dict],
) -> list[dict]:
    """
    Compare currency prefixes between PDF and web for same numeric values.
    Severity: must_fix.
    """
    pdf_figures = _extract_figures(pdf_ready)
    web_figures = _extract_figures(web_ready)

    # Index web figures by numeric value
    web_by_value: dict[str, dict] = {}
    for f in web_figures:
        web_by_value[f["number"]] = f

    issues: list[dict] = []

    for pdf_fig in pdf_figures:
        web_fig = web_by_value.get(pdf_fig["number"])
        if web_fig and web_fig["prefix"] != pdf_fig["prefix"]:
            fig_end = web_fig["position"] + len(web_fig["original"])
            issues.append({
                "type": "currency_mismatch",
                "severity": "must_fix",
                "title": "Wrong currency symbol used",
                "explanation": (
                    f'The PDF uses "{pdf_fig["prefix"]}" '
                    f'but the website uses "{web_fig["prefix"]}" '
                    f'— they must match exactly.'
                ),
                "pdf_snippet": pdf_fig["original"],
                "web_snippet": web_fig["original"],
                "pdf_location": {},
                "web_location": _find_section(
                    web_fig["position"], web_ready, web_sections,
                ),
                "pdf_symbol": pdf_fig["prefix"].strip(),
                "web_symbol": web_fig["prefix"].strip(),
                "numeric_value": pdf_fig["number"],
                "unit": pdf_fig["unit"].strip(),
                "context_before": web_ready[max(0, web_fig["position"] - 60):web_fig["position"]],
                "context_after": web_ready[fig_end:min(len(web_ready), fig_end + 60)],
            })

    logger.info("Check 2 (currency mismatch): %d issues", len(issues))
    return issues


# ──────────────────────────────────────────────
# CHECK 3 — Missing Words (helpers)
# ──────────────────────────────────────────────

def split_into_sentences(text: str) -> list[str]:
    """
    Splits text into sentences for sentence-aligned comparison.

    Rules:
      Split on . ? ! followed by whitespace and uppercase
      Do not split on decimal numbers  1.5  165.3
      Do not split on abbreviations    Dr.  Mr.  Ltd.
      Do not split on currency figures H1630.58  Rs.9000
      Minimum sentence length: 6 words
      Discard fragments shorter than 6 words
    """

    # Protect decimal numbers from splitting
    text = re.sub(r'(\d)\.(\d)', r'\1__DECIMAL__\2', text)

    # Protect known abbreviations
    ABBREVS = [
        'Dr', 'Mr', 'Mrs', 'Ms', 'Prof', 'Sr', 'Jr',
        'Ltd', 'Inc', 'Corp', 'Co', 'vs', 'etc', r'i\.e',
        r'e\.g', 'Fig', 'No', 'Vol', 'Jan', 'Feb', 'Mar',
        'Apr', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov',
        'Dec', 'Rs', 'INR'
    ]
    for abbrev in ABBREVS:
        text = re.sub(
            rf'\b({abbrev})\.',
            r'\1__ABBREV__',
            text
        )

    # Split on sentence boundaries
    raw = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)

    # Restore protected patterns
    sentences = []
    for s in raw:
        s = s.replace('__DECIMAL__', '.')
        s = s.replace('__ABBREV__', '.')
        s = s.strip()
        if len(s.split()) >= 6:
            sentences.append(s)

    return sentences


def find_best_window(
    pdf_sentence: str,
    web_text:     str
) -> tuple[str, int]:
    """
    Finds the substring of web_text that best matches
    pdf_sentence using a sliding window approach.

    Window size: 1.5x the word count of the PDF sentence.
    This gives enough context to catch insertions while
    staying focused enough to avoid false alignment.

    Returns: (best_matching_window, best_score)
    """
    pdf_words    = pdf_sentence.split()
    web_words    = web_text.split()
    window_size  = max(len(pdf_words), int(len(pdf_words) * 1.5))

    best_window = ""
    best_score  = 0

    for i in range(len(web_words) - window_size + 1):
        window = ' '.join(web_words[i:i + window_size])
        score  = fuzz.partial_ratio(pdf_sentence, window)

        if score > best_score:
            best_score  = score
            best_window = window

        # Early exit — perfect match found
        if best_score == 100:
            break

    return best_window, best_score


# ──────────────────────────────────────────────
# CHECK 3 — Missing Words
# ──────────────────────────────────────────────

def check_missing_words(
    pdf_ready: str,
    web_ready: str,
) -> list[dict]:
    """
    Detects words present in PDF but absent from website.

    Architecture: sentence-aligned local difflib.
      1. Split PDF into sentences
      2. Find each sentence's best match anywhere in web text
         (order invariant — handles section reordering)
      3. Run difflib.ndiff locally on aligned sentence pair
         (word precise — catches single missing words)
      4. Report missing tokens with surrounding context

    Replaces: difflib.ndiff on full document
    Reason:   full-document ndiff breaks on section reordering
    """
    issues   = []
    sentences = split_into_sentences(pdf_ready)

    for sentence in sentences:

        # Align — find where this sentence lives in web text
        # This step is ORDER INVARIANT
        best_window, score = find_best_window(
            sentence, web_ready
        )

        # Score 100 — perfect match — no issues
        if score == 100:
            continue

        # Score below 70 — sentence not found at all
        # This is a missing paragraph — handled by Check 4
        # Do NOT raise as a missing word issue
        if score < 70:
            continue

        # Score 70-99 — sentence found but imperfectly
        # Run local diff to find exactly what is missing
        pdf_words = sentence.split()
        web_words = best_window.split()

        diff = list(difflib.ndiff(pdf_words, web_words))

        # Collect consecutive missing tokens
        i = 0
        while i < len(diff):
            if not diff[i].startswith('- '):
                i += 1
                continue

            # Collect consecutive missing tokens
            missing_group = []
            while i < len(diff) and diff[i].startswith('- '):
                missing_group.append(diff[i][2:])
                i += 1

            if not missing_group:
                continue

            # Get surrounding context from diff
            context_tokens = [
                t[2:] for t in diff
                if not t.startswith('?')
            ]
            try:
                before_idx = context_tokens.index(missing_group[0])
                context_before = ' '.join(
                    context_tokens[max(0, before_idx - 5):before_idx]
                )
                after_idx = context_tokens.index(missing_group[-1])
                context_after = ' '.join(
                    context_tokens[after_idx + 1:after_idx + 6]
                )
            except ValueError:
                context_before = ''
                context_after  = ''

            issues.append({
                "type":            "missing_word",
                "severity":        "must_fix",
                "title":           "Words missing from website",
                "explanation":     (
                    f'The word(s) "{" ".join(missing_group)}" '
                    f'are in the PDF but were not found on '
                    f'the website.'
                ),
                "missing_tokens":  missing_group,
                "context_before":  context_before,
                "context_after":   context_after,
                "match_score":     score,
                "pdf_location":    {},
                "web_location":    {
                    "section": "Search the website for "
                               "the surrounding context",
                    "selector": ""
                }
            })

    logger.info("Check 3 (missing words): %d issues", len(issues))
    return issues


# ──────────────────────────────────────────────
# CHECK 4 — Missing Paragraphs
# ──────────────────────────────────────────────

def check_missing_paragraphs(
    pdf_ready: str,
    web_ready: str,
    pdf_paragraphs: list[dict],
) -> list[dict]:
    """
    Each PDF paragraph must exist somewhere on the website.
    Uses fuzzy matching — below 80% = paragraph is missing.
    Severity: must_fix.
    """
    issues: list[dict] = []

    for para_meta in pdf_paragraphs:
        para_text = para_meta["text"]
        if len(para_text.strip()) < 60:
            continue  # skip short fragments

        score = fuzz.partial_ratio(para_text, web_ready)

        if score < MISSING_PARA_THRESHOLD:
            issues.append({
                "type": "missing_paragraph",
                "severity": "must_fix",
                "title": "Entire section missing from website",
                "explanation": (
                    "This full paragraph is in the PDF "
                    "but was not found anywhere on the website."
                ),
                "pdf_snippet": para_text,
                "web_snippet": "",
                "pdf_location": {
                    "page": para_meta["page"],
                    "paragraph": para_meta["para_index"],
                    "column": para_meta["column"],
                },
                "web_location": {
                    "section": "Search the website for the first few words of this text.",
                    "selector": "body",
                },
                "paragraph_text": para_text,
            })

    logger.info("Check 4 (missing paragraphs): %d issues", len(issues))
    return issues
