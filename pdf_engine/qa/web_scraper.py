"""
web_scraper.py — Playwright-based web scraper for microsite QA.

Scrapes text from Vercel-hosted Next.js microsites.
Removes noise elements, targets content wrappers, tags sections.
Returns raw text with NFC normalization and strip only — no content alteration.
"""

from __future__ import annotations

import re
import unicodedata
import logging

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# DOM stability check
# ──────────────────────────────────────────────

async def _wait_for_dom_stability(
    page,
    interval_ms: int = 500,
    max_attempts: int = 10,
) -> None:
    """
    Wait until DOM text content stops changing.

    Takes two snapshots interval_ms apart.
    If identical — DOM is stable — return.
    If different — content still changing — retry.

    Deterministic alternative to fixed timeouts.
    Works for CSS animations, JS counters, and any
    other dynamic content pattern.
    """
    prev_text = None

    for attempt in range(max_attempts):
        curr_text = await page.evaluate(
            "document.body.innerText"
        )
        if curr_text == prev_text:
            logger.debug(
                "DOM stable after %d attempt(s)",
                attempt + 1
            )
            return
        prev_text = curr_text
        await page.wait_for_timeout(interval_ms)

    logger.warning(
        "DOM did not stabilise after %d attempts — "
        "proceeding with current state",
        max_attempts
    )


# ──────────────────────────────────────────────
# Section tagging
# ──────────────────────────────────────────────

async def _tag_sections(page) -> list[dict]:
    """
    Capture section headings with their text content before noise removal.
    Returns list of {"section": str, "text": str, "selector": str}.
    """
    sections = await page.evaluate("""
        () => {
            const results = [];
            const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
            headings.forEach((h, i) => {
                const parent = h.closest('section') || h.parentElement;
                const text = parent ? parent.innerText : h.innerText;
                const tag = h.tagName.toLowerCase();
                const idx = i;
                results.push({
                    section: h.innerText.trim().substring(0, 80),
                    text: text.trim().substring(0, 500),
                    selector: `${tag}:nth-of-type(${idx + 1})`
                });
            });
            return results;
        }
    """)
    return sections


# ──────────────────────────────────────────────
# Noise removal
# ──────────────────────────────────────────────

_NOISE_SELECTORS = [
    'nav',
    'header',
    'footer',
    'script',
    'style',
    'noscript',
    'iframe',
    'svg',
    'img',
    'button',
    'form',
    '[class*="cookie"]',
    '[class*="banner"]',
    '[class*="popup"]',
    '[class*="modal"]',
    '[class*="toast"]',
    '[class*="alert"]',
    '[class*="menu"]',
    '[class*="nav"]',
    '[class*="breadcrumb"]',
    '[aria-hidden="true"]',
]


async def _remove_noise(page) -> None:
    """Remove all noise elements from the DOM before text extraction."""
    selector_str = ", ".join(_NOISE_SELECTORS)
    await page.evaluate(
        f"""document.querySelectorAll('{selector_str}')"""
        """.forEach(el => el.remove())"""
    )


# ──────────────────────────────────────────────
# Content wrapper targeting
# ──────────────────────────────────────────────

_CONTENT_SELECTORS = [
    "main",
    "article",
    ".content",
    "#content",
    ".microsite",
    "#microsite",
    "[class*='content']",
]


async def _extract_content_text(page) -> str:
    """
    Extract text from the content wrapper, falling back to body.
    Tries selectors in priority order.
    """
    for selector in _CONTENT_SELECTORS:
        el = await page.query_selector(selector)
        if el:
            text = await el.inner_text()
            if text and text.strip():
                logger.info("Content extracted via selector: %s", selector)
                return text

    logger.warning("No content wrapper found, falling back to body")
    return await page.inner_text("body")


# ──────────────────────────────────────────────
# Post-extraction cleaning
# ──────────────────────────────────────────────

_CTA_PHRASES = [
    'back to top', 'read more', 'learn more', 'click here',
    'know more', 'view more', 'book now', 'contact us',
    'get in touch', 'follow us', 'subscribe', 'share this',
]


def clean_web_text(text: str) -> str:
    """
    Remove non-content lines from scraped text.
    Preserves exact wording, spacing, and punctuation of real content.
    """
    # Phone numbers
    text = re.sub(r'\+?[\d\s\-\(\)]{10,}', '', text)
    # Email addresses
    text = re.sub(r'[\w\.\-]+@[\w\.\-]+\.\w+', '', text)
    # URLs
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    # Copyright lines
    text = re.sub(r'©.*', '', text)
    text = re.sub(r'copyright.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'all rights reserved.*', '', text, flags=re.IGNORECASE)
    # Social media handles
    text = re.sub(r'@\w+', '', text)
    # Standalone page numbers (1-2 digits only — 3+ digit standalone numbers
    # are almost certainly content stats, not pagination artifacts)
    text = re.sub(r'^\d{1,2}$', '', text, flags=re.MULTILINE)
    # CTA phrases
    for phrase in _CTA_PHRASES:
        text = re.sub(rf'\b{phrase}\b', '', text, flags=re.IGNORECASE)
    # Next/image alt text injections
    text = re.sub(r'\[image:.*?\]', '', text, flags=re.IGNORECASE)
    # Collapse 3+ blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove lines that are only whitespace
    lines = [line for line in text.split('\n') if line.strip()]
    return '\n'.join(lines).strip()


# ──────────────────────────────────────────────
# Preparation (NFC + strip only — no normalisation)
# ──────────────────────────────────────────────

def prepare(text: str) -> str:
    """
    Prepare text for comparison.
    Only NFC normalization and strip — nothing else.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.strip()
    return text


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

async def scrape_microsite(url: str) -> tuple[str, list[dict], list[dict]]:
    """
    Scrape a microsite and return prepared text with section metadata.

    Args:
        url: The microsite URL to scrape.

    Returns:
        Tuple of (web_ready_text, web_sections, web_paragraphs).
        web_paragraphs: list of {"text", "section"} dicts.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Layer 1 — prefers-reduced-motion: tells the page to skip or
        # instant-complete animations. CountUp.js, GSAP, and Framer Motion
        # all check this media query. Set at context level so it applies
        # for the entire page lifecycle, including JS-driven counters.
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            reduced_motion="reduce",
        )
        page = await context.new_page()

        try:
            # Step 1 — Navigate and wait for full render
            logger.info("Navigating to %s", url)
            await page.goto(url, wait_until="networkidle")

            # Layer 2 — Incremental scroll to trigger IntersectionObserver
            # callbacks. Counter animations start when the element enters
            # the viewport. A single jump may scroll past elements too fast.
            # Scrolling in 10 steps ensures every element triggers its
            # IntersectionObserver callback before extraction.
            total_height = await page.evaluate(
                "document.body.scrollHeight"
            )
            for step in range(10):
                target = int(total_height * (step + 1) / 10)
                await page.evaluate(f"window.scrollTo(0, {target})")
                await page.wait_for_timeout(200)

            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(300)

            # Step 3 — Expand all accordions
            collapsed = await page.query_selector_all("[aria-expanded='false']")
            for el in collapsed:
                try:
                    await el.click()
                    await page.wait_for_timeout(300)
                except Exception:
                    pass

            # Layer 3 — DOM stability check: poll until text content stops
            # changing. Deterministic — works for CSS animations, JS counters,
            # and any other dynamic content pattern.
            await _wait_for_dom_stability(page)

            # Phase 4 fallback — targeted wait for data-target counter elements.
            # Activates only if the page uses counter libraries that store the
            # final value in a data-target/data-count/etc. attribute.
            # Resolves immediately if no such elements exist.
            try:
                await page.wait_for_function(
                    """
                    () => {
                        const counters = document.querySelectorAll(
                            '[data-target], [data-count], '
                            '[data-countup-end], [data-number]'
                        )
                        for (const el of counters) {
                            const target =
                                el.getAttribute('data-target') ||
                                el.getAttribute('data-count') ||
                                el.getAttribute('data-countup-end') ||
                                el.getAttribute('data-number')
                            if (target && parseInt(target) > 0) {
                                const current = parseInt(
                                    el.textContent.replace(/[^0-9]/g, '')
                                )
                                if (current < parseInt(target) * 0.9) {
                                    return false
                                }
                            }
                        }
                        return true
                    }
                    """,
                    timeout=5000
                )
            except Exception:
                # No data-target counters found or timed out.
                # Proceed — DOM stability check already handled it.
                pass

            # Step 4 — Tag sections BEFORE removing elements
            web_sections = await _tag_sections(page)
            logger.info("Tagged %d sections", len(web_sections))

            # Step 5 — Remove noise elements
            await _remove_noise(page)

            # Step 6 — Extract text from content wrapper
            raw_text = await _extract_content_text(page)

            # Step 7 — Clean non-content lines
            cleaned = clean_web_text(raw_text)

            # Step 8 — Prepare (NFC + strip only)
            web_ready = prepare(cleaned)

            # Step 9 — Split into paragraphs for check 5
            raw_paragraphs = web_ready.split('\n\n')
            web_paragraphs = []
            for i, para in enumerate(raw_paragraphs):
                para = para.strip()
                if not para:
                    continue
                # Find which section this paragraph belongs to
                section_info = _find_section_for_text(para, web_sections)
                web_paragraphs.append({
                    "text": para,
                    "para_index": i + 1,
                    "section": section_info,
                })

            logger.info(
                "Scraped %d chars, %d paragraphs from %s",
                len(web_ready), len(web_paragraphs), url,
            )

            return web_ready, web_sections, web_paragraphs

        finally:
            await browser.close()


def _find_section_for_text(text: str, sections: list[dict]) -> dict:
    """
    Find which section a piece of text belongs to by checking
    if the text appears in any section's captured content.
    """
    text_preview = text[:60].lower()
    for sec in reversed(sections):
        if text_preview in sec.get("text", "").lower():
            return {
                "section": sec["section"],
                "selector": sec["selector"],
            }
    return {
        "section": "Unknown section",
        "selector": "body",
    }
