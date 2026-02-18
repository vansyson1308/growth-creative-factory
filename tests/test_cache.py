"""Tests for gcf/cache.py — CacheStore and key helpers."""

from __future__ import annotations

import json
from pathlib import Path

from gcf.cache import CacheStore, config_fingerprint, make_cache_key
from gcf.config import AppConfig

# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────


def _store(tmp: Path) -> CacheStore:
    return CacheStore(tmp / "test_cache.db")


# ─────────────────────────────────────────────────────────────────────────────
# CacheStore — basic get / set
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheGetSet:
    def test_miss_returns_none(self, tmp_path):
        assert _store(tmp_path).get("nonexistent_key") is None

    def test_set_then_get_round_trip(self, tmp_path):
        s = _store(tmp_path)
        s.set("k1", "hello world")
        assert s.get("k1") == "hello world"

    def test_set_overwrites_existing(self, tmp_path):
        s = _store(tmp_path)
        s.set("k1", "first")
        s.set("k1", "second")
        assert s.get("k1") == "second"

    def test_set_get_unicode(self, tmp_path):
        s = _store(tmp_path)
        val = json.dumps(["Sale ngay!", "Mua hang nhanh", "Tiet kiem 50%"])
        s.set("unicode_key", val)
        assert json.loads(s.get("unicode_key")) == [
            "Sale ngay!",
            "Mua hang nhanh",
            "Tiet kiem 50%",
        ]

    def test_multiple_independent_keys(self, tmp_path):
        s = _store(tmp_path)
        s.set("a", "alpha")
        s.set("b", "beta")
        assert s.get("a") == "alpha"
        assert s.get("b") == "beta"

    def test_empty_string_value(self, tmp_path):
        s = _store(tmp_path)
        s.set("empty", "")
        assert s.get("empty") == ""


# ─────────────────────────────────────────────────────────────────────────────
# CacheStore — stats
# ─────────────────────────────────────────────────────────────────────────────


class TestCacheStats:
    def test_initial_stats_zero(self, tmp_path):
        s = _store(tmp_path)
        assert s.stats() == {"hits": 0, "misses": 0, "hit_rate": 0.0}

    def test_miss_increments_misses(self, tmp_path):
        s = _store(tmp_path)
        s.get("nope")
        assert s.misses == 1
        assert s.hits == 0

    def test_hit_increments_hits(self, tmp_path):
        s = _store(tmp_path)
        s.set("k", "v")
        s.get("k")
        assert s.hits == 1
        assert s.misses == 0

    def test_hit_rate_calculation(self, tmp_path):
        s = _store(tmp_path)
        s.set("k1", "v1")
        s.get("k1")  # hit
        s.get("k1")  # hit
        s.get("miss")  # miss
        assert s.hits == 2
        assert s.misses == 1
        assert abs(s.hit_rate() - 2 / 3) < 0.001

    def test_hit_rate_zero_when_no_calls(self, tmp_path):
        assert _store(tmp_path).hit_rate() == 0.0

    def test_hit_rate_one_when_all_hits(self, tmp_path):
        s = _store(tmp_path)
        s.set("k", "v")
        s.get("k")
        s.get("k")
        assert s.hit_rate() == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# CacheStore — persistence
# ─────────────────────────────────────────────────────────────────────────────


class TestCachePersistence:
    def test_survives_reopen(self, tmp_path):
        db = tmp_path / "persist.db"
        CacheStore(db).set("key", "persistent_value")
        assert CacheStore(db).get("key") == "persistent_value"

    def test_clear_removes_all_rows(self, tmp_path):
        s = _store(tmp_path)
        s.set("a", "1")
        s.set("b", "2")
        removed = s.clear()
        assert removed == 2
        assert s.get("a") is None
        assert s.get("b") is None

    def test_parent_dir_created(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "cache.db"
        CacheStore(nested).set("x", "y")
        assert nested.exists()


# ─────────────────────────────────────────────────────────────────────────────
# make_cache_key
# ─────────────────────────────────────────────────────────────────────────────


class TestMakeCacheKey:
    def test_returns_64_char_hex(self):
        key = make_cache_key("AD001", '{"model":"claude"}', "improve CTR")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_same_inputs_same_key(self):
        k1 = make_cache_key("AD001", "cfg", "hyp")
        k2 = make_cache_key("AD001", "cfg", "hyp")
        assert k1 == k2

    def test_different_ad_id_different_key(self):
        assert make_cache_key("AD001", "cfg", "h") != make_cache_key(
            "AD002", "cfg", "h"
        )

    def test_different_hypothesis_different_key(self):
        assert make_cache_key("AD001", "cfg", "CTR") != make_cache_key(
            "AD001", "cfg", "ROAS"
        )

    def test_different_config_different_key(self):
        k1 = make_cache_key("AD001", '{"model":"a"}', "h")
        k2 = make_cache_key("AD001", '{"model":"b"}', "h")
        assert k1 != k2

    def test_namespace_suffixes_are_distinct(self):
        base = make_cache_key("AD001", "cfg", "hyp")
        assert base + ":headlines" != base + ":descriptions"


# ─────────────────────────────────────────────────────────────────────────────
# config_fingerprint
# ─────────────────────────────────────────────────────────────────────────────


class TestConfigFingerprint:
    def test_returns_json_string(self):
        fp = config_fingerprint(AppConfig())
        parsed = json.loads(fp)
        assert "model" in parsed
        assert "num_headlines" in parsed

    def test_same_config_same_fingerprint(self):
        assert config_fingerprint(AppConfig()) == config_fingerprint(AppConfig())

    def test_different_model_different_fingerprint(self):
        cfg_a = AppConfig()
        cfg_b = AppConfig()
        cfg_b.provider.model = "different-model"
        assert config_fingerprint(cfg_a) != config_fingerprint(cfg_b)

    def test_different_num_headlines_different_fingerprint(self):
        cfg_a = AppConfig()
        cfg_b = AppConfig()
        cfg_b.generation.num_headlines = 99
        assert config_fingerprint(cfg_a) != config_fingerprint(cfg_b)

    def test_different_temperature_different_fingerprint(self):
        cfg_a = AppConfig()
        cfg_b = AppConfig()
        cfg_b.provider.temperature = 0.1
        assert config_fingerprint(cfg_a) != config_fingerprint(cfg_b)
