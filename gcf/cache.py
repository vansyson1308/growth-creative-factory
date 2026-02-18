"""SQLite-backed LLM response cache.

Cache entries are keyed by a SHA-256 hash of three stable identifiers:
    ad_id  +  config_fingerprint  +  hypothesis (strategy string)

This ensures identical requests skip the LLM entirely.

Usage::

    from gcf.cache import CacheStore, make_cache_key, config_fingerprint

    store = CacheStore("cache/llm_cache.db")
    key = make_cache_key(ad_id, config_fingerprint(cfg), strategy)

    cached = store.get(key + ":headlines")
    if cached:
        headlines = json.loads(cached)
    else:
        # ... call LLM ...
        store.set(key + ":headlines", json.dumps(headlines))
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Cache store
# ─────────────────────────────────────────────────────────────────────────────

class CacheStore:
    """Persistent LLM response cache backed by SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0
        self._init_db()

    # ── DB setup ──────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_cache (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[str]:
        """Return cached value or None on miss."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM llm_cache WHERE key = ?", (key,)
            ).fetchone()
        if row:
            self._hits += 1
            return row[0]
        self._misses += 1
        return None

    def set(self, key: str, value: str) -> None:
        """Store (or overwrite) a cache entry."""
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO llm_cache (key, value) VALUES (?, ?)",
                (key, value),
            )
            conn.commit()

    def clear(self) -> int:
        """Delete all entries; returns number of rows removed."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM llm_cache")
            conn.commit()
        return cur.rowcount

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def hits(self) -> int:
        return self._hits

    @property
    def misses(self) -> int:
        return self._misses

    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return round(self._hits / total, 4) if total else 0.0

    def stats(self) -> dict:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Key helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_cache_key(ad_id: str, cfg_fingerprint: str, hypothesis: str) -> str:
    """Return a SHA-256 hex digest for the (ad_id, config, hypothesis) triple.

    The digest is deterministic and collision-resistant.  Callers append a
    namespace suffix before using as a DB key, e.g.::

        key = make_cache_key(ad_id, fp, strategy)
        store.get(key + ":headlines")
        store.get(key + ":descriptions")
    """
    raw = json.dumps(
        {"ad_id": ad_id, "cfg": cfg_fingerprint, "hyp": hypothesis},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def config_fingerprint(cfg) -> str:
    """Stable JSON string of the generation + provider settings that affect output.

    Changing any of these fields will produce a different fingerprint, causing
    a cache miss (correct behaviour — the prompt/output space changed).
    """
    gen = cfg.generation
    prov = cfg.provider
    parts = {
        "num_headlines":        gen.num_headlines,
        "num_descriptions":     gen.num_descriptions,
        "max_headline_chars":   gen.max_headline_chars,
        "max_description_chars": gen.max_description_chars,
        "model":                prov.model,
        "temperature":          prov.temperature,
    }
    return json.dumps(parts, sort_keys=True)
