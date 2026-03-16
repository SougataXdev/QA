"""
normalizer.py — Text preparation and two-pass comparison filtering.

Two-pass strategy:

  Pass 1 — prepare_for_comparison():
    Applies NFKC normalisation + Unicode skeleton folding to both PDF and
    web text before any of the 5 checks run. Eliminates font encoding
    differences (ligatures, quote variants, cross-script homoglyphs) that
    are NEVER real content errors and would cause false positives.

    SOURCE: Unicode Technical Standard #39
    https://unicode.org/reports/tr39/

  Pass 2 — pass_two_filter():
    Re-checks any issue that survives Pass 1 using typographic_normalise().
    Safety net — after NFKC + skeleton most false positives are already
    eliminated before the checks run. pass_two_filter() catches any
    remaining edge cases.

Design principle:
  Only normalise automatically what a content editor would NEVER be asked
  to fix. Everything else goes to the reviewer.
"""

from __future__ import annotations

import re
import unicodedata
import logging

from pdf_engine.pipeline.skeleton_map import get_skeleton_map

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# PROTECTED CHARACTERS
#
# Characters that must survive prepare_for_comparison() unchanged even if
# NFKC or skeleton folding would normally transform them.
#
# Populate from the diagnostic in Phase 5. Run audit_nfkc_skeleton() on
# your real extracted PDF texts to find every character that would be
# changed, then add any characters here that should NOT be changed.
#
# Annual report considerations (check your diagnostic output — do not add
# anything here that you have not confirmed in a real PDF):
#
#   '\u2013'  # en dash — if clients care about dash vs hyphen style
#   '\u2014'  # em dash — if clients care about dash vs hyphen style
#   '\u00bd'  # ½ vulgar fraction — if used in financials (NFKC → 1⁄2)
#   '\u00b2'  # superscript 2 — if used as footnote marker (NFKC → 2)
#   '\u00b3'  # superscript 3 — if used as footnote marker (NFKC → 3)
#
# CAUTION: Do NOT add characters speculatively. Only add after confirming
# via diagnostic that (a) the character appears in real PDFs and (b) the
# normalised form would create a false positive or hide a real difference.
# ──────────────────────────────────────────────────────────────────────────────

PROTECTED_CHARS: frozenset[str] = frozenset({
    # EN DASH (U+2013): skeleton maps it to '-' (hyphen).
    # Some clients specify dash style in their brand guidelines. A content
    # editor may be asked to fix "en dash vs hyphen" differences.
    # Show it to the reviewer — do not fold automatically.
    '\u2013',

    # EM DASH (U+2014): skeleton maps it to U+30FC (KATAKANA-HIRAGANA
    # PROLONGED SOUND MARK — a horizontal CJK bar). This mapping is
    # technically a visual confusable but is semantically wrong for
    # English annual report text. The em dash must survive intact so
    # the reviewer can evaluate em dash vs hyphen style differences.
    '\u2014',
})


# ──────────────────────────────────────────────────────────────────────────────
# PASS 1 — PREPARATION
# ──────────────────────────────────────────────────────────────────────────────

def prepare_for_comparison(text: str) -> str:
    """
    Prepare text for Pass 1 comparison using NFKC normalisation + Unicode
    skeleton folding restricted to non-ASCII characters.

    SOURCE: Unicode Technical Standard #39
    https://unicode.org/reports/tr39/

    ELIMINATES (font encoding differences — never real content errors):
      Ligature variants      ﬁ ﬂ ﬀ ﬃ ﬄ → fi fl ff ffi ffl  (NFKC)
      Quote variants         ' ' → '   " " → "               (skeleton)
      Space variants         U+00A0 U+2009 U+202F → space     (NFKC)
      Cross-script glyphs    Cyrillic A → Latin A             (skeleton)
      Mathematical variants  bold-A → A                       (skeleton)
      Full-width Latin       A B → A B                        (NFKC)
      Superscript digits     superscript-2 → 2                (NFKC)
      Hyphen line-break      "Patient- Centric" → "Patient-Centric" (Step 4)

    PRESERVES (real content differences — always detectable):
      Multiple spaces        double space survives — Check 1 depends on it
      Apostrophe presence    India's vs Indias detectable
      Currency symbols       H Rs. INR and rupee sign survive intact
      All word differences   every real missing word caught
      En/Em dash             in PROTECTED_CHARS — show to reviewer

    WHY NON-ASCII ONLY FOR SKELETON:
      confusables.txt maps many ASCII characters to each other because they
      are visually alike in some fonts (1 vs l, 0 vs O, I vs l). Applying
      these mappings to prose text would corrupt numbers and ordinary words.
      Restricting skeleton folding to codepoints above U+007F eliminates
      cross-script homoglyphs (Cyrillic, Greek, mathematical variants, curly
      quotes) while leaving all basic Latin, digits, and punctuation untouched.

    STEPS:
      1. NFKC — handles ligatures, spaces, full-width, superscripts.
      2. Skeleton fold (non-ASCII only, skip PROTECTED_CHARS).
      3. NFKC again — normalises any new decomposables from substitutions.
      4. Hyphen line-break collapse — removes spurious space in "word- Word".
    """
    # Step 1 — NFKC
    # Handles ligatures, non-breaking spaces, full-width chars, superscripts.
    # Does NOT collapse multiple spaces.
    # Does NOT remove apostrophes.
    # Does NOT change currency symbols.
    text = unicodedata.normalize("NFKC", text)

    # Step 2 — Skeleton folding (non-ASCII and non-protected characters only)
    #
    # Restriction rationale:
    #   ord(c) < 0x80  → ASCII: skip unconditionally. The skeleton map
    #                    remaps ASCII confusables (1↔l, 0↔O, I↔l) which
    #                    would corrupt digits, Latin words, and currency symbols.
    #   c in PROTECTED_CHARS → skip dashes; reviewer should evaluate these.
    #
    # This still handles curly quotes (U+2018/2019 → '),
    # Cyrillic homoglyphs (U+0410 → A), mathematical letters, etc.
    #
    # get_skeleton_map() returns {} on network+cache failure — pipeline safe.
    skeleton_map = get_skeleton_map()
    if skeleton_map:
        text = "".join(
            c if (ord(c) < 0x80 or c in PROTECTED_CHARS)
            else skeleton_map.get(c, c)
            for c in text
        )
        # Step 3 — NFKC again after substitutions.
        text = unicodedata.normalize("NFKC", text)

    # Step 4 — Collapse PDF hyphen line-break artifacts.
    #
    # _join_lines_into_paragraph() in extract.py keeps the hyphen and adds
    # a space when the next line starts with an uppercase letter, producing:
    #   "Patient- Centric" instead of "Patient-Centric"
    #
    # The pattern letter-hyphen-spaces-letter NEVER occurs in normal prose.
    # It is always a PDF extraction artifact from a word split across lines.
    # Removing the spurious space normalises to the form on the website.
    #
    # Applied to both PDF and web text — safe because web text never contains
    # this pattern from natural writing or CMS output.
    text = re.sub(r'([A-Za-z])-\s+([A-Za-z])', r'\1-\2', text)

    return text.strip()


# ──────────────────────────────────────────────────────────────────────────────
# PASS 2 — TYPOGRAPHIC NORMALISATION
# Safety net — after NFKC + skeleton most false positives are already gone.
# Used ONLY inside pass_two_filter(). Never called before Pass 1.
# Never called on text entering the 5 QA checks.
# ──────────────────────────────────────────────────────────────────────────────

def typographic_normalise(text: str) -> str:
    """
    Apply typographic normalisation for Pass 2 re-checking.

    After NFKC + skeleton in Pass 1, most encoding differences are already
    eliminated. This function is a safety net for any residual variants that
    survive Pass 1. It flattens character variants that are purely
    font-encoding artefacts and that no content editor would ever be asked
    to correct.

    Flattens:
      - All single-quote / apostrophe variants → straight apostrophe (')
      - All double-quote variants → straight double quote (")
      - All remaining Unicode space-category characters → regular space

    Deliberately NOT flattened:
      Dashes (em/en)   — may be a real style error; show to reviewer
      Ellipsis U+2026  — may be intentional; show to reviewer
      Currency symbols — always a real error; never normalise
      Whitespace       — double space is Check 1; must not be collapsed
    """
    result = []
    for char in text:
        name = unicodedata.name(char, '')

        # All single-quote / apostrophe variants → straight apostrophe
        if any(keyword in name for keyword in [
            'APOSTROPHE',
            'SINGLE QUOTATION',
            'GRAVE ACCENT',
            'ACUTE ACCENT',
            'MODIFIER LETTER APOSTROPHE',
        ]):
            result.append("'")
            continue

        # All double-quote variants → straight double quote
        if 'DOUBLE QUOTATION' in name:
            result.append('"')
            continue

        # All remaining Unicode space-category characters → regular space
        if unicodedata.category(char) == 'Zs':
            result.append(' ')
            continue

        result.append(char)

    return ''.join(result)


# ──────────────────────────────────────────────────────────────────────────────
# DIAGNOSTIC UTILITY
# Run on real extracted PDF text to audit every character NFKC + skeleton
# would change. Use results to populate PROTECTED_CHARS above.
# ──────────────────────────────────────────────────────────────────────────────

def audit_nfkc_skeleton(text: str) -> list[dict]:
    """
    Find every character in text that NFKC + skeleton folding would change.

    Returns a list of dicts — one per unique affected character — with:
      original      — the original character
      codepoint     — U+XXXX hex notation
      name          — Unicode character name
      result        — what it becomes after full pipeline
      changed_by    — "NFKC" or "skeleton"
      sample_context — 30 chars before/after for editorial review

    Use this on your real extracted PDF texts before populating
    PROTECTED_CHARS. Only add characters here that you confirm should not
    be normalised in your specific PDFs.
    """
    skeleton_map = get_skeleton_map()
    affected: list[dict] = []
    seen: set[str] = set()

    for i, char in enumerate(text):
        if char in seen:
            continue

        # What NFKC does to this char
        nfkc_char = unicodedata.normalize("NFKC", char)

        # What skeleton does after NFKC
        after_skeleton = skeleton_map.get(nfkc_char, nfkc_char)
        final = unicodedata.normalize("NFKC", after_skeleton)

        if final != char:
            seen.add(char)
            affected.append({
                "original":       char,
                "codepoint":      f"U+{ord(char):04X}",
                "name":           unicodedata.name(char, "UNKNOWN"),
                "result":         final,
                "changed_by":     "NFKC" if nfkc_char != char else "skeleton",
                "sample_context": text[max(0, i - 30): i + 30],
            })

    return affected


# ──────────────────────────────────────────────────────────────────────────────
# PASS 2 — ISSUE TEXT EXTRACTOR
# ──────────────────────────────────────────────────────────────────────────────

def get_find_text(issue: dict) -> str | None:
    """
    Extract the text to re-check from a Pass 1 issue.

    Returns None for issue types that must NEVER be filtered by Pass 2:
      - currency_mismatch: always a real content error regardless of encoding
      - extra_whitespace:  always a real content error regardless of encoding
    """
    issue_type = issue.get("type")

    if issue_type == "missing_word":
        tokens = issue.get("missing_tokens", [])
        before = issue.get("context_before", "")
        return (before + " " + " ".join(tokens)).strip()

    elif issue_type == "currency_mismatch":
        return None  # NEVER re-check currency in Pass 2

    elif issue_type == "extra_whitespace":
        return None  # NEVER re-check whitespace in Pass 2

    elif issue_type == "missing_paragraph":
        para = issue.get("paragraph_text", "")
        sentences = para.split(".")
        return sentences[0].strip() if sentences else para[:100]

    return None


# ──────────────────────────────────────────────────────────────────────────────
# PASS 2 — FILTER
# ──────────────────────────────────────────────────────────────────────────────

def pass_two_filter(
    issue: dict,
    pdf_text: str,
    web_text: str,
    logger,
) -> dict | None:
    """
    Re-check a single Pass 1 issue to catch any encoding differences that
    survived prepare_for_comparison().

    Returns the issue unchanged if it is a confirmed real error.
    Returns None if it is a residual typographic / encoding difference.

    Logic:
      1. Extract the text fragment to re-check (get_find_text).
         If get_find_text() returns None (currency, whitespace) → keep always.
      2. Apply typographic_normalise() to both find_text and web_text.
      3. If normalised find_text is NOT in normalised web_text → real error.
      4. If normalised find_text IS found, check character-count delta.
         delta > 2  → word structure changed → real error → keep.
         delta ≤ 2  → confirmed encoding difference → drop.

    Every dropped issue is logged with full audit detail. The caller builds
    the dropped_by_pass_two report entry from the None return value.
    """
    find_text = get_find_text(issue)

    if find_text is None:
        return issue  # currency or whitespace — never filter

    if not find_text.strip():
        return issue  # cannot re-check empty text — keep to be safe

    find_norm = typographic_normalise(find_text)
    web_norm  = typographic_normalise(web_text)

    if find_norm not in web_norm:
        return issue  # genuinely absent — real error

    original_chars   = len(find_text.replace(' ', ''))
    normalised_chars = len(find_norm.replace(' ', ''))
    char_delta       = abs(original_chars - normalised_chars)

    if char_delta > 2:
        return issue  # word structure changed — real error

    # Confirmed encoding difference — drop and log.
    logger.info(
        "Pass 2 dropped issue %s: '%s' is a typographic variant of content "
        "found in web text. Normalised form: '%s'. Char delta: %d. "
        "Not a real content error.",
        issue.get('id', 'unknown'),
        find_text,
        find_norm,
        char_delta,
    )
    return None
