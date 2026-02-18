"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Interface that all LLM providers must implement."""

    @abstractmethod
    def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        """Send a prompt and return the raw text response."""
        ...
