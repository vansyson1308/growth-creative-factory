"""Load and validate config.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

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
    retry_limit: int = 3
    max_variants_per_run: int = 100


@dataclass
class DedupeConfig:
    similarity_threshold: int = 85


@dataclass
class PolicyConfig:
    blocked_patterns: List[str] = field(default_factory=lambda: [
        r"(?i)cam kết", r"(?i)tuyệt đối", r"(?i)\bno\.?\s*1\b",
        r"(?i)\bbest\b", r"(?i)\bguarantee[d]?\b", r"(?i)\b#1\b", r"(?i)100%",
    ])


@dataclass
class ProviderConfig:
    name: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    temperature: float = 0.8
    max_tokens: int = 2048


@dataclass
class MemoryConfig:
    path: str = "memory/memory.jsonl"


@dataclass
class AppConfig:
    selector: SelectorConfig = field(default_factory=SelectorConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML file, falling back to defaults."""
    p = Path(path)
    raw: dict = {}
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

    return AppConfig(
        selector=SelectorConfig(**raw.get("selector", {})),
        generation=GenerationConfig(**raw.get("generation", {})),
        dedupe=DedupeConfig(**raw.get("dedupe", {})),
        policy=PolicyConfig(**raw.get("policy", {})),
        provider=ProviderConfig(**raw.get("provider", {})),
        memory=MemoryConfig(**raw.get("memory", {})),
    )
