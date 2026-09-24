"""Load and validate config.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, List, Optional

import yaml


@dataclass
class SelectorConfig:
    min_impressions: int = 1000
    max_ctr: float = 0.02
    max_cpa: float = 50.0
    min_roas: float = 2.0


@dataclass
class GenerationConfig:
    num_headlines: int = 10
    num_descriptions: int = 6
    max_headline_chars: int = 30
    max_description_chars: int = 90
    retry_limit: int = 3  # kept for backward compat
    max_variants_per_run: int = 100
    max_variants_headline: int = 5  # cap on headlines returned to pipeline
    max_variants_desc: int = 3  # cap on descriptions returned to pipeline
    max_retries_validation: int = 2  # validation-retry loops in generator


@dataclass
class DedupeConfig:
    similarity_threshold: int = 85
    min_distinct_angles: int = 3
    angle_buckets: List[str] = field(
        default_factory=lambda: [
            "benefit",
            "urgency",
            "social_proof",
            "problem_solution",
            "curiosity",
        ]
    )


@dataclass
class PolicyConfig:
    blocked_patterns: List[str] = field(
        default_factory=lambda: [
            r"(?i)cam\s*k[eế]t",
            r"(?i)tuy[eệ]t\s*[dđ][oố]i",
            r"(?i)\bno\.?\s*1\b",
            r"(?i)\bbest\b",
            r"(?i)\bguarantee[d]?\b",
            r"(?i)(?<!\w)#1\b",
            r"(?i)100%",
        ]
    )


@dataclass
class BrandVoiceConfig:
    tone: str = "clear, credible, and action-oriented"
    audience: str = "prospects comparing options"
    forbidden_words: List[str] = field(
        default_factory=lambda: [
            "guarantee",
            "best",
            "no.1",
            "#1",
            "100%",
        ]
    )


@dataclass
class ProviderConfig:
    name: str = "anthropic"
    model: str = "claude-opus-5"
    # Current Claude models reject sampling params; set only for older models.
    temperature: Optional[float] = None
    max_tokens: int = 2048
    effort: Optional[str] = "low"  # output_config.effort: low|medium|high|xhigh|max
    fallbacks: Optional[str] = "default"  # server-side refusal fallbacks; null = off


@dataclass
class MemoryConfig:
    path: str = "memory/memory.jsonl"


@dataclass
class BudgetConfig:
    """Hard caps to control live API spending."""

    max_calls_per_run: int = 50  # total generate() calls; 0 = unlimited
    daily_budget_tokens: int = 100_000  # informational (not enforced automatically)


@dataclass
class RetryConfig:
    """Exponential-backoff settings for live API calls."""

    max_api_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0


@dataclass
class CacheConfig:
    """SQLite-backed LLM response cache."""

    enabled: bool = True
    path: str = "cache/llm_cache.db"


@dataclass
class RenderConfig:
    """Creative rendering (turn copy into on-brand images)."""

    enabled: bool = False  # config.yaml ships with this switched on
    formats: List[str] = field(default_factory=lambda: ["square", "portrait", "story"])
    templates: List[str] = field(default_factory=list)  # empty = rotate through all
    brand: Any = "aurora"  # preset name, path to brand YAML, or inline mapping
    max_creatives: int = 24  # distinct copy variants rendered per run (0 = all)
    image_format: str = "png"  # png | jpg
    workers: int = 0  # 0 = auto
    executor: str = "auto"  # auto | process | thread
    gallery: bool = True  # write output/gallery.html
    contact_sheet: bool = True  # write output/contact_sheet.png


@dataclass
class AppConfig:
    selector: SelectorConfig = field(default_factory=SelectorConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    brand_voice: BrandVoiceConfig = field(default_factory=BrandVoiceConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    retry_api: RetryConfig = field(default_factory=RetryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    render: RenderConfig = field(default_factory=RenderConfig)


def _section(raw: dict, key: str, cls):
    """Build a config section, rejecting unknown keys with a helpful message."""
    data = raw.get(key) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config section '{key}' must be a mapping")
    allowed = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(
            f"Unknown key(s) in config section '{key}': {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
    return cls(**data)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML file, falling back to defaults."""
    p = Path(path)
    raw: dict = {}
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    return AppConfig(
        selector=_section(raw, "selector", SelectorConfig),
        generation=_section(raw, "generation", GenerationConfig),
        dedupe=_section(raw, "dedupe", DedupeConfig),
        policy=_section(raw, "policy", PolicyConfig),
        provider=_section(raw, "provider", ProviderConfig),
        brand_voice=_section(raw, "brand_voice", BrandVoiceConfig),
        memory=_section(raw, "memory", MemoryConfig),
        budget=_section(raw, "budget", BudgetConfig),
        retry_api=_section(raw, "retry_api", RetryConfig),
        cache=_section(raw, "cache", CacheConfig),
        render=_section(raw, "render", RenderConfig),
    )
