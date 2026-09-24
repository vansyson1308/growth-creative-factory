"""LLM provider package."""

from gcf.providers.base import BaseProvider
from gcf.providers.mock_provider import MockProvider

__all__ = ["BaseProvider", "MockProvider", "make_provider"]


def make_provider(cfg, mode: str = "dry") -> BaseProvider:
    """Build the provider for *mode* (``dry`` → offline, ``live`` → Claude)."""
    if mode != "live":
        return MockProvider()
    from gcf.providers.anthropic_provider import AnthropicProvider

    pcfg = cfg.provider
    return AnthropicProvider(
        model=pcfg.model,
        temperature=pcfg.temperature,
        max_tokens=pcfg.max_tokens,
        retry_cfg=cfg.retry_api,
        budget_cfg=cfg.budget,
        effort=pcfg.effort,
        fallbacks=pcfg.fallbacks,
    )
