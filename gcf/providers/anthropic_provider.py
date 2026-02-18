"""Anthropic (Claude) provider using the official SDK."""
from __future__ import annotations

import os

import anthropic
from dotenv import load_dotenv

from gcf.providers.base import BaseProvider


class AnthropicProvider(BaseProvider):
    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.8,
        max_tokens: int = 2048,
    ):
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not found. "
                "Copy .env.example → .env and add your key."
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.default_max_tokens = max_tokens

    def generate(self, prompt: str, system: str = "", max_tokens: int = 0) -> str:
        mt = max_tokens or self.default_max_tokens
        message = self.client.messages.create(
            model=self.model,
            max_tokens=mt,
            temperature=self.temperature,
            system=system if system else "You are an expert ad copywriter.",
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
