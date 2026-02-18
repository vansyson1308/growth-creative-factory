"""Anthropic (Claude) provider with retry/backoff and budget tracking."""
from __future__ import annotations

import os
import random
import time
from typing import Optional

import anthropic
from dotenv import load_dotenv

from gcf.providers.base import BaseProvider
from gcf.config import RetryConfig, BudgetConfig


# HTTP status codes that warrant an automatic retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}


class BudgetExceededError(RuntimeError):
    """Raised when max_calls_per_run has been reached."""


class AnthropicProvider(BaseProvider):
    """Wraps the Anthropic Messages API with:

    - Exponential back-off + jitter on 429 / 529 / 5xx
    - Respect for the ``Retry-After`` response header
    - Per-run call budget (``max_calls_per_run``)
    - Token-usage tracking (``total_input_tokens``, ``total_output_tokens``)
    - Retry and error counters exposed via :meth:`stats`
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.8,
        max_tokens: int = 2048,
        retry_cfg: Optional[RetryConfig] = None,
        budget_cfg: Optional[BudgetConfig] = None,
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

        self._retry_cfg = retry_cfg or RetryConfig()
        self._budget_cfg = budget_cfg or BudgetConfig()

        # Runtime counters (reset per provider instance = per pipeline run)
        self.call_count: int = 0
        self.retry_count: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.last_error: Optional[str] = None

    # ── Public interface ──────────────────────────────────────────────────────

    def generate(self, prompt: str, system: str = "", max_tokens: int = 0) -> str:
        """Send *prompt* to Claude and return the text response.

        Raises
        ------
        BudgetExceededError
            If ``max_calls_per_run`` is > 0 and has been reached.
        anthropic.APIStatusError / anthropic.APIConnectionError
            If all retries are exhausted.
        """
        budget = self._budget_cfg.max_calls_per_run
        if budget and self.call_count >= budget:
            raise BudgetExceededError(
                f"max_calls_per_run={budget} reached "
                f"(total_tokens so far: {self.total_input_tokens + self.total_output_tokens})"
            )

        mt = max_tokens or self.default_max_tokens
        sys_msg = system if system else "You are an expert ad copywriter."

        last_exc: Optional[BaseException] = None
        max_retries = self._retry_cfg.max_api_retries

        for attempt in range(max_retries + 1):
            try:
                self.call_count += 1
                message = self.client.messages.create(
                    model=self.model,
                    max_tokens=mt,
                    temperature=self.temperature,
                    system=sys_msg,
                    messages=[{"role": "user", "content": prompt}],
                )
                # Track tokens
                usage = getattr(message, "usage", None)
                if usage:
                    self.total_input_tokens += getattr(usage, "input_tokens", 0)
                    self.total_output_tokens += getattr(usage, "output_tokens", 0)

                return message.content[0].text

            except anthropic.APIStatusError as exc:
                if exc.status_code not in _RETRYABLE_STATUS_CODES:
                    # Non-retryable (e.g. 400 Bad Request, 401 Unauthorized)
                    self.last_error = f"HTTP {exc.status_code}: {exc.message}"
                    raise

                last_exc = exc
                if attempt >= max_retries:
                    break

                wait = self._get_wait_seconds(exc, attempt)
                self.retry_count += 1
                self.call_count -= 1  # don't count failed attempt toward budget
                time.sleep(wait)

            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
                last_exc = exc
                if attempt >= max_retries:
                    break

                wait = self._backoff_secs(attempt)
                self.retry_count += 1
                self.call_count -= 1
                time.sleep(wait)

        # All retries exhausted
        self.last_error = str(last_exc)
        raise last_exc  # type: ignore[misc]

    def stats(self) -> dict:
        """Return a snapshot of runtime counters for reporting."""
        total_tokens = self.total_input_tokens + self.total_output_tokens
        return {
            "call_count": self.call_count,
            "retry_count": self.retry_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": total_tokens,
            "last_error": self.last_error,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_wait_seconds(self, exc: anthropic.APIStatusError, attempt: int) -> float:
        """Honour Retry-After if present, otherwise use exponential back-off."""
        try:
            retry_after = exc.response.headers.get("retry-after")
            if retry_after:
                return max(0.0, float(retry_after))
        except Exception:
            pass
        return self._backoff_secs(attempt)

    def _backoff_secs(self, attempt: int) -> float:
        """Exponential back-off with full jitter: min(base*2^attempt + jitter, cap)."""
        base = self._retry_cfg.backoff_base_seconds
        cap = self._retry_cfg.backoff_max_seconds
        jitter = random.uniform(0.0, 1.0)
        return min(base * (2 ** attempt) + jitter, cap)
