"""Tests for brand voice + compliance subagents."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gcf.compliance_agent import filter_risky_claims
from gcf.brand_voice_agent import _parse_brand_voice_json


class TestComplianceAgent:
    def test_filters_risky_claims(self):
        h = ["Best deal guarantee", "Great value today"]
        d = ["Get 100% guaranteed returns", "Shop now for new arrivals"]
        ch, cd, failures = filter_risky_claims(h, d)

        assert ch == ["Great value today"]
        assert cd == ["Shop now for new arrivals"]
        assert len(failures) == 2
        assert all("suggestion" in f for f in failures)

    def test_keeps_compliant_copy(self):
        h = ["Smart savings this week"]
        d = ["Try it today and save more"]
        ch, cd, failures = filter_risky_claims(h, d)
        assert ch == h
        assert cd == d
        assert failures == []


class TestBrandVoiceParser:
    def test_parses_brand_voice_json(self):
        raw = json.dumps(
            {
                "guideline": "Keep tone clear and practical.",
                "examples": ["Save time today.", "Try now for value."],
            }
        )
        out = _parse_brand_voice_json(raw)
        assert "Guideline:" in out
        assert "Examples:" in out

    def test_invalid_json_returns_empty(self):
        assert _parse_brand_voice_json("not json") == ""
