"""Validate ad copy against character limits and policy rules."""
from __future__ import annotations

import re
from typing import List

from gcf.config import PolicyConfig


def char_count(text: str) -> int:
    """Return the Unicode-safe character count, spaces included.

    Counts every Unicode code-point (including Vietnamese/CJK characters)
    as exactly 1, matching Google Ads / Meta Ads counting behaviour.

    Examples::

        char_count("Hello")           # → 5
        char_count("Tiết kiệm ngay")  # → 14
    """
    return len(text)


def check_char_limit(text: str, max_chars: int) -> bool:
    """Unicode-safe character count check (including spaces)."""
    return char_count(text) <= max_chars


def check_not_all_caps(text: str) -> bool:
    """Reject if the entire text is uppercase."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return True
    return not all(c.isupper() for c in alpha)


def check_policy(text: str, blocked_patterns: List[str]) -> bool:
    """Return True if text is clean (no blocked patterns found)."""
    for pat in blocked_patterns:
        if re.search(pat, text):
            return False
    return True


def validate_headline(
    text: str,
    max_chars: int = 30,
    policy_cfg: PolicyConfig | None = None,
) -> dict:
    """Return {'valid': bool, 'errors': [...]}."""
    errors: List[str] = []
    if not check_char_limit(text, max_chars):
        errors.append(f"Exceeds {max_chars} chars (has {len(text)})")
    if not check_not_all_caps(text):
        errors.append("All caps not allowed")
    if policy_cfg and not check_policy(text, policy_cfg.blocked_patterns):
        errors.append("Policy violation")
    return {"valid": len(errors) == 0, "errors": errors}


def validate_description(
    text: str,
    max_chars: int = 90,
    policy_cfg: PolicyConfig | None = None,
) -> dict:
    errors: List[str] = []
    if not check_char_limit(text, max_chars):
        errors.append(f"Exceeds {max_chars} chars (has {char_count(text)})")
    if policy_cfg and not check_policy(text, policy_cfg.blocked_patterns):
        errors.append("Policy violation")
    return {"valid": len(errors) == 0, "errors": errors}


def validate_limits(
    h1: str,
    desc: str,
    max_h1: int = 30,
    max_desc: int = 90,
    policy_cfg: PolicyConfig | None = None,
) -> dict:
    """Validate both H1 and DESC in a single call.

    Returns a dict with keys:
    - ``valid``       : True only when *both* fields pass all checks.
    - ``h1_errors``   : list of error strings for the headline (empty = OK).
    - ``desc_errors`` : list of error strings for the description (empty = OK).

    Character limits are Unicode-safe (spaces count).  Pass ``policy_cfg``
    to also apply blocked-pattern checks.

    Example::

        result = validate_limits("Sale ngay!", "Giảm 50% hôm nay.")
        assert result["valid"] is True
    """
    h1_result = validate_headline(h1, max_h1, policy_cfg)
    desc_result = validate_description(desc, max_desc, policy_cfg)
    return {
        "valid": h1_result["valid"] and desc_result["valid"],
        "h1_errors": h1_result["errors"],
        "desc_errors": desc_result["errors"],
    }
