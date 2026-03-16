#!/usr/bin/env python3
"""
CLI wrapper for web scraping.

Scrapes a microsite URL and writes the extracted text to ./crawloutput/.

Usage:
    python3 cli_crawl.py <url>

Example:
    python3 cli_crawl.py https://example.com/microsite
"""

import asyncio
import os
import re
import sys
from urllib.parse import urlparse


CRAWLOUTPUT_DIR = os.path.join(os.path.dirname(__file__), "crawloutput")


def _url_to_filename(url: str) -> str:
    """Derive a safe filename from a URL (no extension — we'll add .txt)."""
    parsed = urlparse(url)
    host = parsed.netloc.replace(":", "_")
    path = re.sub(r"[^\w\-]", "_", parsed.path.strip("/"))
    slug = f"{host}_{path}" if path else host
    # Collapse multiple underscores and trim to 120 chars
    slug = re.sub(r"_+", "_", slug).strip("_")[:120]
    return slug or "crawl"


async def _run(url: str) -> None:
    from pdf_engine.qa.web_scraper import scrape_microsite

    print(f"Scraping: {url}")
    web_ready, web_sections, web_paragraphs = await scrape_microsite(url)

    os.makedirs(CRAWLOUTPUT_DIR, exist_ok=True)

    filename = _url_to_filename(url) + ".txt"
    out_path = os.path.join(CRAWLOUTPUT_DIR, filename)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(web_ready)

    print(f"  → {out_path}")
    print(f"  {len(web_paragraphs)} paragraphs, {len(web_sections)} sections, {len(web_ready)} chars")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 cli_crawl.py <url>")
        sys.exit(1)

    url = sys.argv[1].strip()
    if not url.startswith(("http://", "https://")):
        print(f"✗ URL must start with http:// or https://  (got: {url!r})")
        sys.exit(1)

    asyncio.run(_run(url))


if __name__ == "__main__":
    main()
