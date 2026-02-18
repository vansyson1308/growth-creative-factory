"""Checker agent — final compliance pass on generated copy.

Calls the LLM with checker_prompt.txt and removes any flagged items from the
headline and description lists.  This is the last step in the pipeline before
cross-product combination, ensuring no policy-violating copy ships.

Usage::

    from gcf.checker import check_copy

    headlines, descriptions, violations = check_copy(
        provider, headlines, descriptions, cfg
    )
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from jinja2 import Template

from gcf.config import AppConfig
from gcf.providers.base import BaseProvider

_PROMPT_PATH = Path(__file__).parent / "prompts" / "checker_prompt.txt"


# ─────────────────────────────────────────────────────────────────────────────
# Template loader
# ─────────────────────────────────────────────────────────────────────────────

def _load_template() -> Template:
    return Template(_PROMPT_PATH.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# JSON parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json_violations(raw: str) -> List[Dict]:
    """Extract the violations list from a checker JSON response.

    Handles three common LLM formats:
    1. Plain JSON object: ``{"violations": [...]}``
    2. JSON inside a markdown code-block: ``\`\`\`json\\n{...}\\n\`\`\```
    3. JSON embedded inside prose — extracted with regex
    """
    text = raw.strip()

    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        return data.get("violations", [])
    except (json.JSONDecodeError, AttributeError):
        pass

    # Fallback: extract first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return data.get("violations", [])
        except (json.JSONDecodeError, AttributeError):
            pass

    return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def check_copy(
    provider: BaseProvider,
    headlines: List[str],
    descriptions: List[str],
    cfg: AppConfig,
) -> Tuple[List[str], List[str], List[Dict]]:
    """Run the LLM compliance checker on the generated copy.

    Parameters
    ----------
    provider:
        The active LLM (or mock) provider.
    headlines:
        All generated headlines for a single ad.
    descriptions:
        All generated descriptions for a single ad.
    cfg:
        Application configuration (used for char limits).

    Returns
    -------
    (clean_headlines, clean_descriptions, violations)
        *clean_headlines* and *clean_descriptions* have all flagged items
        removed.  *violations* is the raw list of violation dicts for
        reporting / logging.
    """
    if not headlines and not descriptions:
        return [], [], []

    tmpl = _load_template()
    prompt = tmpl.render(
        headlines=headlines,
        descriptions=descriptions,
        max_headline_chars=cfg.generation.max_headline_chars,
        max_description_chars=cfg.generation.max_description_chars,
    )

    raw = provider.generate(
        prompt,
        system=(
            "You are a strict compliance reviewer for advertising copy. "
            "Return ONLY valid JSON."
        ),
    )

    violations = _parse_json_violations(raw)

    # Build index sets of flagged items
    bad_headline_idx: set[int] = set()
    bad_description_idx: set[int] = set()
    for v in violations:
        t = str(v.get("type", "")).upper()
        idx = v.get("index")
        if idx is None:
            continue
        if t == "HEADLINE":
            bad_headline_idx.add(int(idx))
        elif t == "DESCRIPTION":
            bad_description_idx.add(int(idx))

    clean_headlines = [h for i, h in enumerate(headlines) if i not in bad_headline_idx]
    clean_descriptions = [d for i, d in enumerate(descriptions) if i not in bad_description_idx]

    return clean_headlines, clean_descriptions, violations
