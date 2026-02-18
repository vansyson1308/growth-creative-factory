"""Tests for gcf/checker.py."""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Minimal stubs
# ─────────────────────────────────────────────────────────────────────────────

class _FakePolicy:
    blocked_patterns: list = []

class _FakeGenCfg:
    max_headline_chars = 30
    max_description_chars = 90

class _FakeCfg:
    generation = _FakeGenCfg()
    policy = _FakePolicy()


def _make_provider(response: str):
    """Return a mock provider that always returns *response*."""
    p = MagicMock()
    p.generate.return_value = response
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Import the module under test
# ─────────────────────────────────────────────────────────────────────────────

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gcf.checker import _parse_json_violations, check_copy


# ─────────────────────────────────────────────────────────────────────────────
# _parse_json_violations
# ─────────────────────────────────────────────────────────────────────────────

class TestParseJsonViolations:
    """Tests for _parse_json_violations."""

    def test_plain_empty_violations(self):
        raw = json.dumps({"violations": []})
        assert _parse_json_violations(raw) == []

    def test_plain_with_violations(self):
        data = {"violations": [
            {"type": "HEADLINE", "index": 0, "text": "BUY NOW", "issue": "ALL-CAPS word"},
        ]}
        result = _parse_json_violations(json.dumps(data))
        assert len(result) == 1
        assert result[0]["type"] == "HEADLINE"
        assert result[0]["index"] == 0

    def test_markdown_fenced_json(self):
        inner = json.dumps({"violations": [
            {"type": "DESCRIPTION", "index": 1, "text": "bad", "issue": "no CTA"},
        ]})
        raw = f"```json\n{inner}\n```"
        result = _parse_json_violations(raw)
        assert len(result) == 1
        assert result[0]["type"] == "DESCRIPTION"

    def test_prose_with_embedded_json_returns_empty(self):
        inner = json.dumps({"violations": [
            {"type": "HEADLINE", "index": 2, "text": "x", "issue": "too long"},
        ]})
        raw = f"Here is my review: {inner} — done."
        result = _parse_json_violations(raw)
        assert result == []

    def test_malformed_returns_empty(self):
        result = _parse_json_violations("not valid json at all")
        assert result == []

    def test_empty_string_returns_empty(self):
        result = _parse_json_violations("")
        assert result == []

    def test_multiple_violations(self):
        data = {"violations": [
            {"type": "HEADLINE", "index": 0, "text": "H1", "issue": "too long"},
            {"type": "DESCRIPTION", "index": 0, "text": "D1", "issue": "no CTA"},
            {"type": "HEADLINE", "index": 1, "text": "H2", "issue": "ALL-CAPS"},
        ]}
        result = _parse_json_violations(json.dumps(data))
        assert len(result) == 3


# ─────────────────────────────────────────────────────────────────────────────
# check_copy
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckCopy:
    """Tests for check_copy."""

    def test_empty_inputs_returns_empty(self):
        provider = _make_provider("{}")
        cfg = _FakeCfg()
        ch, de, viol = check_copy(provider, [], [], cfg)
        assert ch == []
        assert de == []
        assert viol == []
        # provider should NOT be called if both lists are empty
        provider.generate.assert_not_called()

    def test_all_pass_returns_unchanged(self):
        response = json.dumps({"violations": []})
        provider = _make_provider(response)
        cfg = _FakeCfg()
        h = ["Headline One", "Headline Two"]
        d = ["Desc one. Mua ngay!", "Desc two. Liên hệ ngay!"]
        ch, de, viol = check_copy(provider, h, d, cfg)
        assert ch == h
        assert de == d
        assert viol == []

    def test_removes_flagged_headline_by_index(self):
        viol_data = {"violations": [
            {"type": "HEADLINE", "index": 1, "text": "BAD HEAD", "issue": "ALL-CAPS"},
        ]}
        provider = _make_provider(json.dumps(viol_data))
        cfg = _FakeCfg()
        h = ["Good headline", "BAD HEAD", "Another good one"]
        d = ["Desc. Mua ngay!"]
        ch, de, viol = check_copy(provider, h, d, cfg)
        assert "BAD HEAD" not in ch
        assert "Good headline" in ch
        assert "Another good one" in ch
        assert len(ch) == 2
        assert len(viol) == 1

    def test_removes_flagged_description_by_index(self):
        viol_data = {"violations": [
            {"type": "DESCRIPTION", "index": 0, "text": "No CTA here", "issue": "missing CTA"},
        ]}
        provider = _make_provider(json.dumps(viol_data))
        cfg = _FakeCfg()
        h = ["Good headline"]
        d = ["No CTA here", "Good desc. Mua ngay!"]
        ch, de, viol = check_copy(provider, h, d, cfg)
        assert "No CTA here" not in de
        assert "Good desc. Mua ngay!" in de
        assert len(de) == 1

    def test_removes_multiple_violations(self):
        viol_data = {"violations": [
            {"type": "HEADLINE", "index": 0, "text": "BAD", "issue": "ALL-CAPS"},
            {"type": "HEADLINE", "index": 2, "text": "ALSO BAD", "issue": "ALL-CAPS"},
            {"type": "DESCRIPTION", "index": 1, "text": "bad desc", "issue": "no CTA"},
        ]}
        provider = _make_provider(json.dumps(viol_data))
        cfg = _FakeCfg()
        h = ["BAD", "Keep this", "ALSO BAD", "Keep too"]
        d = ["Keep desc. Mua ngay!", "bad desc", "Another keep. Liên hệ!"]
        ch, de, viol = check_copy(provider, h, d, cfg)
        assert ch == ["Keep this", "Keep too"]
        assert de == ["Keep desc. Mua ngay!", "Another keep. Liên hệ!"]
        assert len(viol) == 3

    def test_malformed_response_keeps_all(self):
        """If checker returns garbage, all copy is kept (safe fallback)."""
        provider = _make_provider("not valid json")
        cfg = _FakeCfg()
        h = ["Headline"]
        d = ["Desc. Mua ngay!"]
        ch, de, viol = check_copy(provider, h, d, cfg)
        assert ch == h
        assert de == d
        assert viol == []

    def test_provider_called_once(self):
        provider = _make_provider(json.dumps({"violations": []}))
        cfg = _FakeCfg()
        check_copy(provider, ["H1"], ["D1. Mua ngay!"], cfg)
        assert provider.generate.call_count == 1

    def test_violation_with_unknown_type_ignored(self):
        """Violations with unrecognised type should not crash."""
        viol_data = {"violations": [
            {"type": "UNKNOWN", "index": 0, "text": "x", "issue": "foo"},
        ]}
        provider = _make_provider(json.dumps(viol_data))
        cfg = _FakeCfg()
        h = ["Headline"]
        d = ["Desc. Mua ngay!"]
        ch, de, viol = check_copy(provider, h, d, cfg)
        # Nothing removed (unrecognised type)
        assert ch == h
        assert de == d
        assert len(viol) == 1

    def test_violation_without_index_ignored(self):
        """Violations missing 'index' key should be silently skipped."""
        viol_data = {"violations": [
            {"type": "HEADLINE", "text": "BAD", "issue": "no index"},
        ]}
        provider = _make_provider(json.dumps(viol_data))
        cfg = _FakeCfg()
        h = ["BAD", "Good"]
        d = ["Desc. Mua ngay!"]
        ch, de, viol = check_copy(provider, h, d, cfg)
        # Index-less violation → nothing removed
        assert "BAD" in ch
        assert len(ch) == 2
