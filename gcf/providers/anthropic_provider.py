"""Anthropic (Claude) provider with retry/backoff and budget tracking."""

from __future__ import annotations

import os
import random
import time
from typing import Optional

import anthropic
from dotenv import load_dotenv

from gcf.config import BudgetConfig, RetryConfig
from gcf.providers.base import BaseProvider, BudgetExceededError

__all__ = ["AnthropicProvider", "BudgetExceededError"]


def _as_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# HTTP status codes that warrant an automatic retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}


def _response_text(message) -> str:
    """Join the text blocks of a Messages API response.

    Current models may return ``thinking`` blocks before the answer, so
    ``content[0]`` is not necessarily text.
    """
    blocks = list(getattr(message, "content", None) or [])
    texts = [
        getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text"
    ]
    if texts:
        return "".join(t for t in texts if isinstance(t, str))
    for b in blocks:  # SDK-less mocks / legacy shapes
        t = getattr(b, "text", None)
        if isinstance(t, str):
            return t
    return ""


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
        model: str = "claude-opus-5",
        temperature: Optional[float] = None,
        max_tokens: int = 2048,
        retry_cfg: Optional[RetryConfig] = None,
        budget_cfg: Optional[BudgetConfig] = None,
        effort: Optional[str] = None,
        fallbacks: Optional[str] = None,
    ):
        """
        ``temperature`` is only sent when set — current Claude models reject
        sampling parameters, older ones accept them. ``effort`` maps to
        ``output_config.effort`` (low | medium | high | xhigh | max).
        ``fallbacks="default"`` enables server-side refusal fallbacks (beta).
        """
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
        self.effort = effort or None
        self.fallbacks = fallbacks or None
        self.default_max_tokens = max_tokens
        self.refusal_count: int = 0

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
                message = self._create(sys_msg, prompt, mt)
                # Track tokens
                usage = getattr(message, "usage", None)
                if usage:
                    self.total_input_tokens += _as_int(
                        getattr(usage, "input_tokens", 0)
                    )
                    self.total_output_tokens += _as_int(
                        getattr(usage, "output_tokens", 0)
                    )

                if getattr(message, "stop_reason", None) == "refusal":
                    # Downstream parsers treat "" as "no candidates" and fall back.
                    self.refusal_count += 1
                    details = getattr(message, "stop_details", None)
                    self.last_error = f"refusal: {getattr(details, 'category', None)}"
                    return ""
                return _response_text(message)

            except anthropic.BadRequestError as exc:
                # Current models reject sampling params — drop and retry once.
                if self.temperature is not None and "temperature" in str(exc).lower():
                    self.temperature = None
                    self.call_count -= 1
                    return self.generate(prompt, system, max_tokens)
                self.last_error = f"HTTP 400: {getattr(exc, 'message', exc)}"
                raise

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

    def _create(self, system: str, prompt: str, max_tokens: int):
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        if self.fallbacks:
            return self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks=self.fallbacks,
                **kwargs,
            )
        return self.client.messages.create(**kwargs)

    def stats(self) -> dict:
        """Return a snapshot of runtime counters for reporting."""
        total_tokens = self.total_input_tokens + self.total_output_tokens
        return {
            "call_count": self.call_count,
            "retry_count": self.retry_count,
            "refusal_count": self.refusal_count,
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
        return min(base * (2**attempt) + jitter, cap)
