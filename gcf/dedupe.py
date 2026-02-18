"""Deduplicate near-identical ad copy and enforce angle diversity."""
from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re
from typing import Dict, List, Sequence, Tuple

try:
    from rapidfuzz import fuzz as _rfuzz

    def _ratio(a: str, b: str) -> float:
        return _rfuzz.ratio(a, b)
except ImportError:
    def _ratio(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100


ANGLE_BUCKETS: List[str] = [
    "benefit",
    "urgency",
    "social_proof",
    "problem_solution",
    "curiosity",
]

_ANGLE_PATTERNS = {
    "urgency": [r"\b(now|today|limited|ending|deadline|hurry|ngay|hom nay|co han)\b"],
    "social_proof": [r"\b(\d+k|\d+\+|customers|users|trusted|review|đánh giá|khach hang)\b"],
    "problem_solution": [r"\b(problem|pain|issue|fix|solve|solution|giai phap|khac phuc)\b"],
    "curiosity": [r"\b(discover|secret|why|what if|bi mat|kham pha|tai sao)\b"],
    "benefit": [r"\b(save|better|easy|faster|value|benefit|tiet kiem|de dang|hieu qua)\b"],
}


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


def detect_angle_bucket(text: str) -> str:
    """Classify text into one creative-angle bucket."""
    t = text.lower().strip()
    if not t:
        return "benefit"

    for bucket in ["urgency", "social_proof", "problem_solution", "curiosity", "benefit"]:
        for pat in _ANGLE_PATTERNS.get(bucket, []):
            if re.search(pat, t):
                return bucket
    return "benefit"


def angle_distribution(texts: Sequence[str]) -> Dict[str, int]:
    """Return counts per angle bucket for the given texts."""
    c = Counter(detect_angle_bucket(t) for t in texts if str(t).strip())
    return {k: c.get(k, 0) for k in ANGLE_BUCKETS}


def enforce_diversity(
    texts: List[str],
    similarity_threshold: int = 85,
    min_distinct_angles: int = 3,
    target_count: int = 5,
    angle_buckets: Sequence[str] | None = None,
) -> Tuple[List[str], List[str], Dict[str, int]]:
    """Dedupe + enforce diverse angle coverage.

    Returns:
        (selected_texts, missing_angles, distribution)
    """
    buckets = list(angle_buckets) if angle_buckets else list(ANGLE_BUCKETS)
    min_distinct_angles = max(1, min(min_distinct_angles, len(buckets)))

    deduped = dedupe_texts(texts, threshold=similarity_threshold)
    if not deduped:
        return [], buckets[:min_distinct_angles], {b: 0 for b in buckets}

    selected: List[str] = []
    used_angles = set()

    # First pass: maximize angle coverage.
    for t in deduped:
        bucket = detect_angle_bucket(t)
        if bucket in buckets and bucket not in used_angles:
            selected.append(t)
            used_angles.add(bucket)
            if len(used_angles) >= min_distinct_angles:
                break

    # Second pass: fill to target_count while respecting dedupe threshold.
    for t in deduped:
        if len(selected) >= target_count:
            break
        if t in selected:
            continue
        is_dup = False
        for s in selected:
            if _ratio(t.lower(), s.lower()) >= similarity_threshold:
                is_dup = True
                break
        if not is_dup:
            selected.append(t)
            used_angles.add(detect_angle_bucket(t))

    dist_counter = Counter(detect_angle_bucket(t) for t in selected)
    distribution = {b: dist_counter.get(b, 0) for b in buckets}
    present = [b for b, n in distribution.items() if n > 0]

    if len(present) >= min_distinct_angles:
        missing: List[str] = []
    else:
        missing = [b for b in buckets if distribution.get(b, 0) == 0][: (min_distinct_angles - len(present))]

    return selected, missing, distribution


def dedupe(texts: List[str], threshold: int = 85) -> List[str]:
    """Convenience alias for :func:`dedupe_texts`."""
    return dedupe_texts(texts, threshold)
