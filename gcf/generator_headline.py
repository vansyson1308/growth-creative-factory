"""Headline generation sub-agent."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Template

from gcf.cache import CacheStore, make_cache_key, config_fingerprint
from gcf.config import AppConfig
from gcf.providers.base import BaseProvider
from gcf.validator import validate_headline
from gcf.dedupe import dedupe_texts

_PROMPT_PATH = Path(__file__).parent / "prompts" / "headline_prompt.txt"


def _load_template() -> Template:
    return Template(_PROMPT_PATH.read_text(encoding="utf-8"))


def _parse_lines(raw: str) -> List[str]:
    """Extract numbered list items from LLM response."""
    lines = []
    for line in raw.strip().splitlines():
        line = line.strip()
        # Match patterns like "1. headline" or "1) headline"
        m = re.match(r"^\d+[\.\)]\s*(.+)$", line)
        if m:
            lines.append(m.group(1).strip().strip('"').strip("'"))
    return lines


def generate_headlines(
    provider: BaseProvider,
    ad_row: Dict,
    strategy: str,
    cfg: AppConfig,
    memory_context: str = "",
    cache_store: Optional[CacheStore] = None,
) -> tuple[List[str], int]:
    """Generate, validate, dedupe headlines. Retries on failure.

    Checks *cache_store* before calling the LLM.  On a cache hit the stored
    list is returned immediately (fail_count = 0, no API call made).

    Returns:
        (valid_headlines, fail_count) — fail_count is the number of
        candidates that did not pass validation across all attempts.
    """
    gen_cfg = cfg.generation
    ad_id = ad_row.get("ad_id", "")
    cap = gen_cfg.max_variants_headline  # output cap (lower than num_headlines)

    # ── Cache check ───────────────────────────────────────────────────────────
    cache_key: Optional[str] = None
    if cache_store is not None:
        fp = config_fingerprint(cfg)
        cache_key = make_cache_key(ad_id, fp, strategy) + ":headlines"
        cached = cache_store.get(cache_key)
        if cached is not None:
            headlines = json.loads(cached)
            return headlines[:cap], 0

    # ── LLM generation with validation retries ────────────────────────────────
    tmpl = _load_template()
    fail_count = 0
    best_valid: List[str] = []
    max_attempts = gen_cfg.max_retries_validation

    for attempt in range(max_attempts):
        attempt_valid: List[str] = []

        prompt = tmpl.render(
            num_headlines=gen_cfg.num_headlines,
            campaign=ad_row.get("campaign", ""),
            ad_group=ad_row.get("ad_group", ""),
            original_headline=ad_row.get("headline", ""),
            original_description=ad_row.get("description", ""),
            issue=ad_row.get("_issue", ""),
            strategy=strategy,
            max_chars=gen_cfg.max_headline_chars,
            memory_context=memory_context,
        )

        raw = provider.generate(prompt, system="You are an expert ad copywriter.")
        candidates = _parse_lines(raw)

        for c in candidates:
            result = validate_headline(c, gen_cfg.max_headline_chars, cfg.policy)
            if result["valid"]:
                attempt_valid.append(c)
            else:
                fail_count += 1

        # Dedupe this attempt's results
        attempt_valid = dedupe_texts(attempt_valid, cfg.dedupe.similarity_threshold)

        # Keep the best set seen so far
        if len(attempt_valid) > len(best_valid):
            best_valid = attempt_valid

        if len(best_valid) >= gen_cfg.num_headlines:
            break

    result_list = best_valid[:cap]

    # ── Persist to cache ──────────────────────────────────────────────────────
    if cache_store is not None and cache_key is not None:
        cache_store.set(cache_key, json.dumps(result_list))

    return result_list, fail_count
