"""Headline generation sub-agent."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Template

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
) -> List[str]:
    """Generate, validate, dedupe headlines. Retries on failure."""
    tmpl = _load_template()
    gen_cfg = cfg.generation

    all_valid: List[str] = []

    for attempt in range(gen_cfg.retry_limit):
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
                all_valid.append(c)

        # Dedupe
        all_valid = dedupe_texts(all_valid, cfg.dedupe.similarity_threshold)

        if len(all_valid) >= gen_cfg.num_headlines:
            break

    return all_valid[: gen_cfg.num_headlines]
