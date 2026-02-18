"""Tests for AnthropicProvider retry/backoff + budget logic.

Works without the real `anthropic` or `httpx` packages installed —
the stubs in run_tests.py provide compatible exception classes.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import anthropic  # provided by stub or real package

from gcf.config import RetryConfig, BudgetConfig
from gcf.providers.anthropic_provider import AnthropicProvider, BudgetExceededError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_status_error(status_code: int, retry_after: str = None):
    """Build an APIStatusError-compatible object for testing."""
    resp = MagicMock()
    resp.status_code = status_code
    if retry_after is not None:
        resp.headers = {"retry-after": retry_after}
    else:
        resp.headers = {}
    exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
    exc.status_code = status_code
    exc.response = resp
    exc.message = f"HTTP {status_code}"
    return exc


def _make_success(text: str = "1. Great headline"):
    msg = MagicMock()
    msg.content = [MagicMock()]
    msg.content[0].text = text
    msg.usage = MagicMock()
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    return msg


def _make_provider(max_retries: int = 2, max_calls: int = 10):
    """Build a provider with instant back-off and a patched client."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
        with patch("anthropic.Anthropic"):
            p = AnthropicProvider(
                retry_cfg=RetryConfig(
                    max_api_retries=max_retries,
                    backoff_base_seconds=0.0,
                    backoff_max_seconds=0.0,
                ),
                budget_cfg=BudgetConfig(max_calls_per_run=max_calls),
            )
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────

class TestSuccessPath:
    def test_success_returns_text(self):
        p = _make_provider()
        p.client.messages.create.return_value = _make_success("Hello!")
        assert p.generate("prompt") == "Hello!"

    def test_call_count_incremented(self):
        p = _make_provider()
        p.client.messages.create.return_value = _make_success()
        p.generate("p1")
        p.generate("p2")
        assert p.call_count == 2

    def test_token_tracking(self):
        p = _make_provider()
        p.client.messages.create.return_value = _make_success()
        p.generate("p")
        assert p.total_input_tokens == 100
        assert p.total_output_tokens == 50
        assert p.stats()["total_tokens"] == 150

    def test_custom_system_prompt(self):
        p = _make_provider()
        p.client.messages.create.return_value = _make_success()
        p.generate("prompt", system="Be a pirate.")
        _, kwargs = p.client.messages.create.call_args
        assert kwargs["system"] == "Be a pirate."

    def test_default_system_prompt_contains_copywriter(self):
        p = _make_provider()
        p.client.messages.create.return_value = _make_success()
        p.generate("prompt")
        _, kwargs = p.client.messages.create.call_args
        assert "copywriter" in kwargs["system"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Retry on rate-limit / server errors
# ─────────────────────────────────────────────────────────────────────────────

class TestRetryLogic:
    def test_retry_on_429_then_success(self):
        p = _make_provider()
        err = _make_status_error(429)
        ok = _make_success("Retry worked")
        p.client.messages.create.side_effect = [err, ok]
        with patch("time.sleep"):
            result = p.generate("p")
        assert result == "Retry worked"
        assert p.retry_count == 1

    def test_retry_on_529_then_success(self):
        p = _make_provider()
        err = _make_status_error(529)
        ok = _make_success("529 ok")
        p.client.messages.create.side_effect = [err, ok]
        with patch("time.sleep"):
            result = p.generate("p")
        assert result == "529 ok"
        assert p.retry_count == 1

    def test_retry_on_500_then_success(self):
        p = _make_provider()
        err = _make_status_error(500)
        ok = _make_success("500 ok")
        p.client.messages.create.side_effect = [err, ok]
        with patch("time.sleep"):
            result = p.generate("p")
        assert result == "500 ok"

    def test_exhausted_retries_raises(self):
        p = _make_provider(max_retries=2)
        err = _make_status_error(429)
        p.client.messages.create.side_effect = [err, err, err, err]
        with patch("time.sleep"):
            with pytest.raises(anthropic.APIStatusError):
                p.generate("p")
        assert p.retry_count == 2

    def test_non_retryable_400_raises_immediately(self):
        p = _make_provider()
        err = _make_status_error(400)
        p.client.messages.create.side_effect = err
        with pytest.raises(anthropic.APIStatusError):
            p.generate("p")
        assert p.retry_count == 0

    def test_retry_after_header_respected(self):
        p = _make_provider()
        err = _make_status_error(429, retry_after="5")
        ok = _make_success()
        p.client.messages.create.side_effect = [err, ok]
        with patch("time.sleep") as mock_sleep:
            p.generate("p")
        mock_sleep.assert_called_once_with(5.0)

    def test_last_error_set_on_failure(self):
        p = _make_provider(max_retries=1)
        err = _make_status_error(500)
        p.client.messages.create.side_effect = [err, err, err]
        with patch("time.sleep"):
            with pytest.raises(anthropic.APIStatusError):
                p.generate("p")
        assert p.last_error is not None

    def test_failed_retries_do_not_inflate_call_count(self):
        """Retried attempts should not consume the budget."""
        p = _make_provider()
        err = _make_status_error(429)
        ok = _make_success()
        p.client.messages.create.side_effect = [err, ok]
        with patch("time.sleep"):
            p.generate("p")
        assert p.call_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Budget enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestBudget:
    def test_budget_exceeded_raises(self):
        p = _make_provider(max_calls=3)
        p.client.messages.create.return_value = _make_success()
        for _ in range(3):
            p.generate("p")
        with pytest.raises(BudgetExceededError):
            p.generate("one too many")

    def test_budget_zero_means_unlimited(self):
        p = _make_provider(max_calls=0)
        p.client.messages.create.return_value = _make_success()
        for _ in range(20):
            p.generate("p")
        assert p.call_count == 20

    def test_budget_error_message_contains_limit(self):
        p = _make_provider(max_calls=1)
        p.client.messages.create.return_value = _make_success()
        p.generate("first")
        try:
            p.generate("second")
            assert False, "Expected BudgetExceededError"
        except BudgetExceededError as e:
            assert "max_calls_per_run=1" in str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Stats snapshot
# ─────────────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_keys_present(self):
        p = _make_provider()
        p.client.messages.create.return_value = _make_success()
        p.generate("p")
        s = p.stats()
        expected = {"call_count", "retry_count", "total_input_tokens",
                    "total_output_tokens", "total_tokens", "last_error"}
        assert set(s.keys()) == expected

    def test_stats_initial_zeros(self):
        p = _make_provider()
        s = p.stats()
        assert s["call_count"] == 0
        assert s["retry_count"] == 0
        assert s["total_tokens"] == 0
        assert s["last_error"] is None

    def test_stats_accumulate_across_calls(self):
        p = _make_provider()
        p.client.messages.create.return_value = _make_success()
        p.generate("p1")
        p.generate("p2")
        s = p.stats()
        assert s["call_count"] == 2
        assert s["total_input_tokens"] == 200
        assert s["total_output_tokens"] == 100
