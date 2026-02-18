"""Headline generation sub-agent — strict JSON output, targeted retry."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Template and JSON parsing
# ─────────────────────────────────────────────────────────────────────────────

def _load_template() -> Template:
    return Template(_PROMPT_PATH.read_text(encoding="utf-8"))


def _parse_json_headlines(raw: str) -> List[str]:
    """Extract headline list from strict JSON response.

    Handles:
    1. Plain JSON:  ``{"headlines": [...]}``
    2. Markdown-fenced JSON:  ``\`\`\`json\\n{...}\\n\`\`\```
    3. JSON embedded in prose (regex fallback)
    4. Legacy numbered-list fallback for backward-compat (e.g. mock provider)
    """
    text = raw.strip()

    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct JSON parse
    try:
        data = json.loads(text)
        items = data.get("headlines", [])
        if isinstance(items, list):
            return [str(s).strip().strip('"\'') for s in items if str(s).strip()]
    except (json.JSONDecodeError, AttributeError):
        pass

    # Regex fallback: find first {...} block
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            items = data.get("headlines", [])
            if isinstance(items, list):
                return [str(s).strip().strip('"\'') for s in items if str(s).strip()]
        except (json.JSONDecodeError, AttributeError):
            pass

    # Legacy numbered-list fallback
    lines = []
    for line in text.splitlines():
        m = re.match(r"^\d+[\.\)]\s*(.+)$", line.strip())
        if m:
            lines.append(m.group(1).strip().strip('"\''))
    return lines


# ─────────────────────────────────────────────────────────────────────────────
# Targeted retry helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_retry_prompt(
    failures: List[Dict],
    needed: int,
    campaign: str,
    ad_group: str,
    strategy: str,
    max_chars: int,
) -> str:
    """Short focused prompt for replacement headlines only.

    Only sent when specific items failed — avoids re-generating the full set.
    """
    failure_lines = "\n".join(
        f"- '{f['text']}': {f['reason']}" for f in failures[:5]
    )
    return (
        f"The following headlines failed validation:\n{failure_lines}\n\n"
        f"Please provide {needed} replacement headline(s) with:\n"
        f"- Campaign: {campaign} / {ad_group}\n"
        f"- Strategy angle: {strategy}\n"
        f"- Rules: each <= {max_chars} characters, no ALL-CAPS words, "
        f"no absolute claims\n\n"
        f'Return ONLY valid JSON: {{"headlines": ["replacement 1", ...]}}'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def generate_headlines(
    provider: BaseProvider,
    ad_row: Dict,
    strategy: str,
    cfg: AppConfig,
    memory_context: str = "",
    cache_store: Optional[CacheStore] = None,
) -> tuple[List[str], int]:
    """Generate, validate, and deduplicate headlines.

    1. Check cache — return immediately on hit.
    2. First LLM call — full prompt, parse JSON, validate all items.
    3. If some items fail and we still need more — targeted retry with
       feedback for ONLY the failed items (not a full regeneration).
    4. Persist successful result to cache.

    Returns
    -------
    (valid_headlines, fail_count)
        *fail_count* is the total number of candidates that did not pass
        validation across all attempts.
    """
    gen_cfg = cfg.generation
    ad_id = ad_row.get("ad_id", "")
    cap = gen_cfg.max_variants_headline

    # ── Cache check ───────────────────────────────────────────────────────────
    cache_key: Optional[str] = None
    if cache_store is not None:
        fp = config_fingerprint(cfg)
        cache_key = make_cache_key(ad_id, fp, strategy) + ":headlines"
        cached = cache_store.get(cache_key)
        if cached is not None:
            return json.loads(cached)[:cap], 0

    # ── Generation setup ──────────────────────────────────────────────────────
    tmpl = _load_template()
    fail_count = 0
    valid: List[str] = []
    max_attempts = gen_cfg.max_retries_validation

    campaign = ad_row.get("campaign", "")
    ad_group = ad_row.get("ad_group", "")

    for attempt in range(max_attempts):
        if attempt == 0:
            # Full prompt on the first attempt
            prompt = tmpl.render(
                num_headlines=gen_cfg.num_headlines,
                campaign=campaign,
                ad_group=ad_group,
                original_headline=ad_row.get("headline", ""),
                original_description=ad_row.get("description", ""),
                issue=ad_row.get("_issue", ""),
                strategy=strategy,
                max_chars=gen_cfg.max_headline_chars,
                memory_context=memory_context,
            )
        else:
            # Targeted retry: only ask for the items still needed
            needed = gen_cfg.num_headlines - len(valid)
            if not failures or needed <= 0:
                break
            prompt = _build_retry_prompt(
                failures, needed, campaign, ad_group, strategy,
                gen_cfg.max_headline_chars,
            )

        raw = provider.generate(prompt, system="You are an expert ad copywriter.")
        candidates = _parse_json_headlines(raw)

        failures: List[Dict] = []
        attempt_valid: List[str] = []

        for c in candidates:
            result = validate_headline(c, gen_cfg.max_headline_chars, cfg.policy)
            if result["valid"]:
                attempt_valid.append(c)
            else:
                fail_count += 1
                failures.append({
                    "text": c,
                    "reason": "; ".join(result.get("errors", ["invalid"])),
                })

        # Dedupe this batch and merge with previously accepted items
        attempt_valid = dedupe_texts(attempt_valid, cfg.dedupe.similarity_threshold)
        for h in attempt_valid:
            if h not in valid:
                valid.append(h)

        if len(valid) >= gen_cfg.num_headlines:
            break

    result_list = valid[:cap]

    # ── Persist to cache ──────────────────────────────────────────────────────
    if cache_store is not None and cache_key is not None and result_list:
        cache_store.set(cache_key, json.dumps(result_list))

    return result_list, fail_count
