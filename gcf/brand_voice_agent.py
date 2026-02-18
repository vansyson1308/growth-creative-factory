"""Brand voice agent (live mode only).

Builds a short style guideline from brand rules and returns it for prompt injection.
In dry mode this agent should be skipped by the pipeline.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from jinja2 import Template

from gcf.config import AppConfig
from gcf.providers.base import BaseProvider

_PROMPT_PATH = Path(__file__).parent / "prompts" / "brand_voice_prompt.txt"


def _load_template() -> Template:
    return Template(_PROMPT_PATH.read_text(encoding="utf-8"))


def _parse_brand_voice_json(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return ""

    guideline = str(data.get("guideline", "")).strip()
    examples = data.get("examples", [])
    if isinstance(examples, list):
        rendered_examples = [str(x).strip() for x in examples if str(x).strip()]
    else:
        rendered_examples = []

    if not guideline and not rendered_examples:
        return ""

    out = [f"Guideline: {guideline}" if guideline else "Guideline:"]
    if rendered_examples:
        out.append("Examples:")
        out.extend(f"- {x}" for x in rendered_examples[:3])
    return "\n".join(out).strip()


def generate_brand_voice_guideline(
    provider: BaseProvider,
    cfg: AppConfig,
    campaign: str,
    ad_group: str,
) -> str:
    """Generate a concise brand voice guideline text block for prompt injection."""
    tone = getattr(cfg.brand_voice, "tone", "")
    audience = getattr(cfg.brand_voice, "audience", "")
    forbidden_words: List[str] = getattr(cfg.brand_voice, "forbidden_words", []) or []

    tmpl = _load_template()
    prompt = tmpl.render(
        tone=tone,
        audience=audience,
        forbidden_words=forbidden_words,
        campaign=campaign,
        ad_group=ad_group,
    )

    raw = provider.generate(
        prompt,
        system=(
            "You are a brand strategist for ad copy. "
            "Return ONLY valid JSON."
        ),
    )
    return _parse_brand_voice_json(raw)
