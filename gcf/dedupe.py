"""Deduplicate near-identical ad copy. Uses rapidfuzz if available, else fallback."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import List

try:
    from rapidfuzz import fuzz as _rfuzz

    def _ratio(a: str, b: str) -> float:
        return _rfuzz.ratio(a, b)
except ImportError:
    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100


def dedupe_texts(texts: List[str], threshold: int = 85) -> List[str]:
    """Return a list with near-duplicates removed.

    Keeps the first occurrence; removes later texts that have
    similarity ratio >= threshold with any already-kept text.
    """
    kept: List[str] = []
    for t in texts:
        t_stripped = t.strip()
        if not t_stripped:
            continue
        is_dup = False
        for k in kept:
            if _ratio(t_stripped.lower(), k.lower()) >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(t_stripped)
    return kept


def dedupe(texts: List[str], threshold: int = 85) -> List[str]:
    """Convenience alias for :func:`dedupe_texts`.

    Preferred name in tests and public documentation.

    Args:
        texts: Ad-copy strings to deduplicate.
        threshold: Similarity score (0–100) above which two strings are
            considered near-duplicates.  Default 85 works well for ad copy.

    Returns:
        Ordered list with near-duplicates removed (first occurrence kept).
    """
    return dedupe_texts(texts, threshold)
