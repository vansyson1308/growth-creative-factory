"""Tests that verify the strict agent call order in the pipeline.

Uses a LoggingProvider that records which prompt type was sent to generate(),
then asserts the sequence: selector -> headline -> description -> checker.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# LoggingProvider — detects prompt type and records calls
# ─────────────────────────────────────────────────────────────────────────────

from gcf.providers.mock_provider import _detect_prompt_type, MockProvider


class LoggingProvider:
    """Records the type of every prompt sent to generate()."""

    def __init__(self):
        self.call_log: List[str] = []
        self._mock = MockProvider(seed=42)

    def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        ptype = _detect_prompt_type(prompt)
        self.call_log.append(ptype)
        # Delegate to MockProvider for realistic JSON responses
        return self._mock.generate(prompt, system, max_tokens)

    def stats(self) -> dict:
        return {
            "call_count": len(self.call_log),
            "call_log": list(self.call_log),
            "retry_count": 0,
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "last_error": None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_config(tmp_dir: str):
    """Build a minimal AppConfig that doesn't touch disk (no cache, no memory)."""
    from gcf.config import (
        AppConfig, SelectorConfig, GenerationConfig, DedupeConfig,
        PolicyConfig, ProviderConfig, MemoryConfig, BudgetConfig,
        RetryConfig, CacheConfig,
    )
    return AppConfig(
        selector=SelectorConfig(
            min_impressions=100,
            max_ctr=0.05,
            max_cpa=100.0,
            min_roas=1.0,
        ),
        generation=GenerationConfig(
            num_headlines=3,
            num_descriptions=2,
            max_headline_chars=30,
            max_description_chars=90,
            retry_limit=1,
            max_variants_per_run=10,
            max_variants_headline=3,
            max_variants_desc=2,
            max_retries_validation=1,
        ),
        dedupe=DedupeConfig(similarity_threshold=85),
        policy=PolicyConfig(blocked_patterns=[]),
        provider=ProviderConfig(
            name="mock",
            model="mock",
            temperature=0.0,
            max_tokens=256,
        ),
        memory=MemoryConfig(path=os.path.join(tmp_dir, "memory.jsonl")),
        budget=BudgetConfig(max_calls_per_run=0, daily_budget_tokens=999999),
        retry_api=RetryConfig(
            max_api_retries=0,
            backoff_base_seconds=0.0,
            backoff_max_seconds=0.0,
        ),
        cache=CacheConfig(enabled=False, path=""),
    )


def _write_sample_csv(path: str):
    """Write a CSV with one clearly underperforming ad."""
    df = pd.DataFrame([{
        "ad_id": "ad_001",
        "campaign": "CampaignA",
        "ad_group": "GroupA",
        "headline": "Sample Headline",
        "description": "Sample description text here.",
        "impressions": 5000,
        "ctr": 0.005,     # below max_ctr=0.05 → underperforming
        "cpa": 20.0,
        "roas": 3.0,
    }])
    df.to_csv(path, index=False)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineCallOrder:
    """Verifies that run_pipeline calls agents in the correct order."""

    def _run(self, tmp_path: str):
        from gcf.pipeline import run_pipeline
        cfg = _make_config(tmp_path)
        provider = LoggingProvider()
        csv_path = os.path.join(tmp_path, "ads.csv")
        out_dir = os.path.join(tmp_path, "output")
        _write_sample_csv(csv_path)
        summary = run_pipeline(csv_path, out_dir, cfg, provider, mode="dry")
        return summary, provider.call_log

    def test_call_order_selector_headline_description_checker(self):
        """Pipeline must call: selector → headline → description → checker."""
        with tempfile.TemporaryDirectory() as tmp:
            summary, log = self._run(tmp)

        assert summary["selected"] == 1, "Expected 1 underperforming ad"
        # Each underperforming ad triggers exactly 4 LLM calls in order
        assert len(log) == 4, f"Expected 4 LLM calls, got {len(log)}: {log}"
        assert log[0] == "selector",     f"First call must be selector, got {log[0]}"
        assert log[1] == "headline",     f"Second call must be headline, got {log[1]}"
        assert log[2] == "description",  f"Third call must be description, got {log[2]}"
        assert log[3] == "checker",      f"Fourth call must be checker, got {log[3]}"

    def test_summary_has_checker_violations_key(self):
        """Summary dict must include checker_violations count."""
        with tempfile.TemporaryDirectory() as tmp:
            summary, _ = self._run(tmp)
        assert "checker_violations" in summary

    def test_variants_are_generated(self):
        """Pipeline must produce at least some variant combinations."""
        with tempfile.TemporaryDirectory() as tmp:
            summary, _ = self._run(tmp)
        assert summary["variants_generated"] > 0

    def test_output_files_created(self):
        """new_ads.csv and figma_variations.tsv must be written."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _make_config(tmp)
            provider = LoggingProvider()
            csv_path = os.path.join(tmp, "ads.csv")
            out_dir = os.path.join(tmp, "output")
            _write_sample_csv(csv_path)
            from gcf.pipeline import run_pipeline
            run_pipeline(csv_path, out_dir, cfg, provider, mode="dry")
            assert os.path.exists(os.path.join(out_dir, "new_ads.csv"))
            assert os.path.exists(os.path.join(out_dir, "figma_variations.tsv"))
            assert os.path.exists(os.path.join(out_dir, "report.md"))

    def test_no_underperforming_skips_llm(self):
        """If no ads are underperforming, the LLM should never be called."""
        with tempfile.TemporaryDirectory() as tmp:
            from gcf.pipeline import run_pipeline
            cfg = _make_config(tmp)
            provider = LoggingProvider()
            csv_path = os.path.join(tmp, "ads.csv")
            out_dir = os.path.join(tmp, "output")
            # All-good ad: high CTR, low CPA, high ROAS
            df = pd.DataFrame([{
                "ad_id": "ad_ok",
                "campaign": "CampOK",
                "ad_group": "GrpOK",
                "headline": "Good ad",
                "description": "Perfect ad. Buy now!",
                "impressions": 9999,
                "ctr": 0.10,    # above max_ctr → not underperforming
                "cpa": 5.0,     # below max_cpa
                "roas": 8.0,    # above min_roas
            }])
            df.to_csv(csv_path, index=False)
            summary = run_pipeline(csv_path, out_dir, cfg, provider, mode="dry")
        assert summary["selected"] == 0
        assert provider.call_log == [], "LLM must not be called for all-good ads"

    def test_multiple_ads_maintain_order(self):
        """With 2 underperforming ads, pattern must repeat for each."""
        with tempfile.TemporaryDirectory() as tmp:
            from gcf.pipeline import run_pipeline
            cfg = _make_config(tmp)
            provider = LoggingProvider()
            csv_path = os.path.join(tmp, "ads.csv")
            out_dir = os.path.join(tmp, "output")
            df = pd.DataFrame([
                {
                    "ad_id": "ad_001", "campaign": "C1", "ad_group": "G1",
                    "headline": "H1", "description": "D1",
                    "impressions": 5000, "ctr": 0.001,
                    "cpa": 20.0, "roas": 3.0,
                },
                {
                    "ad_id": "ad_002", "campaign": "C2", "ad_group": "G2",
                    "headline": "H2", "description": "D2",
                    "impressions": 2000, "ctr": 0.002,
                    "cpa": 30.0, "roas": 1.5,
                },
            ])
            df.to_csv(csv_path, index=False)
            summary = run_pipeline(csv_path, out_dir, cfg, provider, mode="dry")

        assert summary["selected"] == 2
        assert len(provider.call_log) == 8, f"Expected 8 calls (4 per ad): {provider.call_log}"
        # Each block of 4 must follow the pattern
        for offset in (0, 4):
            block = provider.call_log[offset:offset + 4]
            assert block == ["selector", "headline", "description", "checker"], \
                f"Block at offset {offset} wrong: {block}"


class TestDetectPromptType:
    """Tests for the _detect_prompt_type helper used by LoggingProvider."""

    def test_detects_selector(self):
        prompt = (
            "You are an expert performance marketing analyst.\n"
            "Analyse the single underperforming ad below...\n"
            "Return ONLY valid JSON: {\"ad_id\": ...}"
        )
        assert _detect_prompt_type(prompt) == "selector"

    def test_detects_headline(self):
        prompt = (
            "TASK: Generate exactly 10 headline variations for the ad below.\n"
            "ORIGINAL AD: Campaign: X / Group: Y\n"
            'Return ONLY valid JSON: {"headlines": [...]}'
        )
        assert _detect_prompt_type(prompt) == "headline"

    def test_detects_description(self):
        prompt = (
            "TASK: Generate exactly 6 description variations for the ad below.\n"
            "ORIGINAL AD: Campaign: X / Group: Y\n"
            'Return ONLY valid JSON: {"descriptions": [...]}'
        )
        assert _detect_prompt_type(prompt) == "description"

    def test_detects_checker(self):
        prompt = (
            "You are a compliance reviewer for advertising copy.\n"
            "Review the headlines and descriptions below for rule violations.\n"
            'Return ONLY valid JSON: {"violations": [...]}'
        )
        assert _detect_prompt_type(prompt) == "checker"

    def test_detects_retry_headline(self):
        prompt = (
            "The following headlines failed validation:\n"
            "- 'BAD': too long\n"
            'Return ONLY valid JSON: {"headlines": ["replacement 1"]}'
        )
        assert _detect_prompt_type(prompt) == "headline"

    def test_detects_retry_description(self):
        prompt = (
            "The following descriptions failed validation:\n"
            "- 'BAD DESC': missing CTA\n"
            'Return ONLY valid JSON: {"descriptions": ["replacement 1"]}'
        )
        assert _detect_prompt_type(prompt) == "description"
