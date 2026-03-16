"""
skeleton_map.py — Unicode confusables map for cross-script homoglyph folding.

Source: Unicode Technical Standard #39 (Security Mechanisms)
Data:   https://unicode.org/Public/security/latest/confusables.txt

This file handles the class of false positives that NFKC alone cannot
catch: cross-script homoglyphs — characters that are visually identical
but from different Unicode scripts.

Examples handled:
  Cyrillic А (U+0410) → Latin A (U+0041)
  Greek Η (U+0397)    → Latin H (U+0048)
  Mathematical 𝐀      → Latin A

The Unicode Consortium maintains the confusables.txt database and updates
it with every Unicode version. Zero manual maintenance is required for new
brands or fonts — the map grows automatically when refreshed.

OFFLINE SAFETY:
  The pipeline must always work offline. The download happens once and is
  saved to a local cache file. On subsequent runs the cache is used.
  If the cache is older than 30 days a refresh is attempted, but failure
  does NOT crash the pipeline — the stale cache is used instead.
  If both the network and any cache are unavailable, an empty dict is
  returned. NFKC alone still handles the large majority of false positives.
"""

from __future__ import annotations

import json
import logging
import os
import time
import unicodedata
import urllib.request
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

CONFUSABLES_URL = "https://unicode.org/Public/security/latest/confusables.txt"

# Store cache next to this file so the pipeline works without a writable CWD.
CACHE_PATH = Path(__file__).parent / "confusables_cache.json"

# Refresh the cache after this many seconds (30 days).
CACHE_MAX_AGE = 30 * 24 * 3600

# Network timeout — short so a dead connection doesn't stall the pipeline.
DOWNLOAD_TIMEOUT = 10


def _parse_confusables(data: str) -> dict[str, str]:
    """
    Parse confusables.txt into a {source_char: target_str} dict.

    Format of each data line (comments and blanks stripped):
      <hex> ; <hex> [<hex> ...] ; <type> # ...

    We take the first `;`-separated field as source and the second as
    target (which may be multiple codepoints producing a multi-char string).
    """
    skeleton_map: dict[str, str] = {}

    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ";" not in line:
            continue

        # Strip inline comment before splitting
        line = line.split("#")[0].strip()
        parts = line.split(";")
        if len(parts) < 2:
            continue

        try:
            source = chr(int(parts[0].strip(), 16))
            target = "".join(
                chr(int(cp.strip(), 16))
                for cp in parts[1].strip().split()
                if cp.strip()
            )
            skeleton_map[source] = target
        except (ValueError, OverflowError):
            # Malformed line or codepoint out of range — skip silently.
            continue

    return skeleton_map


def _load_cache() -> dict[str, str] | None:
    """
    Load the skeleton map from the local cache file.
    Returns None if the file does not exist.
    """
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Could not read confusables cache: %s", exc)
        return None


def _save_cache(skeleton_map: dict[str, str]) -> None:
    """Persist the skeleton map to the local cache file."""
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(skeleton_map, f, ensure_ascii=False)
        logger.info("Confusables cache saved to %s", CACHE_PATH)
    except Exception as exc:
        logger.warning("Could not write confusables cache: %s", exc)


def _cache_age_seconds() -> float | None:
    """Return age of cache file in seconds, or None if it does not exist."""
    if not CACHE_PATH.exists():
        return None
    return time.time() - CACHE_PATH.stat().st_mtime


def download_confusables() -> dict[str, str]:
    """
    Download, parse, and cache the Unicode confusables map.

    Falls back to the local cache on network failure.
    Falls back to an empty dict if no cache exists.
    Never raises — always returns something the pipeline can use.
    """
    try:
        logger.info("Downloading Unicode confusables from %s", CONFUSABLES_URL)
        response = urllib.request.urlopen(CONFUSABLES_URL, timeout=DOWNLOAD_TIMEOUT)
        data = response.read().decode("utf-8")
        skeleton_map = _parse_confusables(data)
        logger.info(
            "Loaded %d confusable mappings from Unicode Consortium",
            len(skeleton_map),
        )
        _save_cache(skeleton_map)
        return skeleton_map

    except Exception as exc:
        logger.warning(
            "Could not download confusables.txt (%s). "
            "Falling back to local cache.",
            exc,
        )
        cached = _load_cache()
        if cached is not None:
            logger.info(
                "Using cached confusables map (%d entries)", len(cached)
            )
            return cached

        logger.warning(
            "No confusables cache available. "
            "Pipeline will continue with NFKC alone — "
            "cross-script homoglyphs will not be folded."
        )
        return {}


@lru_cache(maxsize=1)
def get_skeleton_map() -> dict[str, str]:
    """
    Return the Unicode skeleton map, loading from cache or network as needed.

    Caching policy:
      - Cache fresh (< 30 days old)  → use cache directly, no network call
      - Cache stale (≥ 30 days old)  → attempt re-download; on failure use
                                        stale cache rather than crashing
      - No cache                     → attempt download; on failure return {}

    The result is lru_cached for the process lifetime so this function is
    called at most once per worker process.
    """
    age = _cache_age_seconds()

    if age is not None and age < CACHE_MAX_AGE:
        # Cache is fresh — use it without any network call.
        cached = _load_cache()
        if cached is not None:
            logger.info(
                "Using fresh confusables cache (%.0f hours old, %d entries)",
                age / 3600,
                len(cached),
            )
            return cached

    # Cache is absent or stale — try to download a fresh copy.
    return download_confusables()
