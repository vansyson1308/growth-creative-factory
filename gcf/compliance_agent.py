"""Compliance subagent: rule-based risky claim filter + revision suggestions.

This agent is intended for live mode only and can be skipped in dry-run.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

_RISK_PATTERNS = [
    (r"(?i)\bguarantee(?:d)?\b", "Absolute guarantee claim"),
    (r"(?i)\bbest\b", "Unsubstantiated superlative ('best')"),
    (r"(?i)\bno\.?\s*1\b", "Ranking claim ('No.1')"),
    (r"(?i)(?<!\w)#1\b", "Ranking claim ('#1')"),
    (r"(?i)100%", "Absolute certainty claim ('100%')"),
    (r"(?i)\bcam\s*k[eế]t\b", "Absolute promise claim"),
    (r"(?i)\btuy[eệ]t\s*[dđ][oố]i\b", "Absolute promise claim"),
    (r"(?i)\bcure\b", "Health cure claim"),
    (r"(?i)\bheal(?:s|ing)?\b", "Health treatment claim"),
    (r"(?i)\binvest(?:ment)?\s+return\b", "Financial return claim"),
    (r"(?i)\bprofit\s+guarantee\b", "Financial guarantee claim"),
]


def _suggest_revision(text: str) -> str:
    suggestion = text
    replacements = {
        r"(?i)\bguarantee(?:d)?\b": "help",
        r"(?i)\bbest\b": "high-quality",
        r"(?i)\bno\.?\s*1\b": "top-rated",
        r"(?i)(?<!\w)#1\b": "top-rated",
        r"(?i)100%": "high",
        r"(?i)\bcam\s*k[eế]t\b": "ưu tiên",
        r"(?i)\btuy[eệ]t\s*[dđ][oố]i\b": "đáng tin cậy",
        r"(?i)\bcure\b": "support",
        r"(?i)\bheal(?:s|ing)?\b": "help improve",
        r"(?i)\binvest(?:ment)?\s+return\b": "value",
        r"(?i)\bprofit\s+guarantee\b": "growth support",
    }
    for pat, repl in replacements.items():
        suggestion = re.sub(pat, repl, suggestion)
    return suggestion


def _scan_items(items: List[str], item_type: str) -> Tuple[List[str], List[Dict]]:
    clean: List[str] = []
    failures: List[Dict] = []

    for idx, text in enumerate(items):
        hit_reasons = [
            reason for pattern, reason in _RISK_PATTERNS if re.search(pattern, text)
        ]
        if hit_reasons:
            failures.append(
                {
                    "type": item_type,
                    "index": idx,
                    "text": text,
                    "reason": "; ".join(hit_reasons),
                    "suggestion": _suggest_revision(text),
                }
            )
        else:
            clean.append(text)

    return clean, failures


def filter_risky_claims(headlines: List[str], descriptions: List[str]):
    """Return cleaned lists + failures for risky claims.

    Returns:
        (clean_headlines, clean_descriptions, failures)
    """
    clean_headlines, h_fail = _scan_items(headlines, "HEADLINE")
    clean_descriptions, d_fail = _scan_items(descriptions, "DESCRIPTION")
    failures = h_fail + d_fail
    return clean_headlines, clean_descriptions, failures
