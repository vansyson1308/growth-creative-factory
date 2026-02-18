"""Memory log — stores hypothesis / variant / result across runs.

JSONL schema (one JSON object per line)::

    {
      "date":           "2026-02-18T05:00:00+00:00",  # ISO-8601 UTC
      "campaign":       "Summer_Sale",
      "ad_group":       "Group_A",
      "ad_id":          "AD001",
      "hypothesis":     "Improve CTR for AD001 — CTR 0.01 < 0.02",
      "angle":          "urgency",      # creative-angle label (free text)
      "tag":            "",             # optional run tag / label
      "variant_set_id": "vs_20260218_000",
      "generated": {                    # copy produced in this run
        "headlines":    ["Ship nhanh 24h", ...],
        "descriptions": ["Trải nghiệm ...", ...]
      },
      "notes": "mode=dry",
      "results": {                      # optional; filled by ingest-results
        "ctr":   0.025,
        "cpa":   42.5,
        "roas":  3.8,
        "impr":  12000,
        "clicks": 300,
        "conv":  7
      }
    }

Old entries (schema before this version) used ``inputs`` / ``outputs`` keys.
:func:`load_memory` normalises them transparently on load.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def _normalize(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate old-schema entries to the current schema (in-place).

    Old schema used ``inputs`` / ``outputs`` keys.  New schema uses top-level
    ``ad_id`` / ``ad_group`` plus ``generated`` and optional ``results``.
    All required keys are guaranteed to be present after this call.
    """
    # ── Promote inputs.ad_id → top level ─────────────────────────────────────
    if "inputs" in entry and "ad_id" not in entry:
        entry["ad_id"] = entry["inputs"].get("ad_id", "")

    # ── Ensure flat fields ────────────────────────────────────────────────────
    for field in ("ad_group", "angle", "tag"):
        if field not in entry:
            entry[field] = ""

    # ── Rename outputs → generated ────────────────────────────────────────────
    if "outputs" in entry and "generated" not in entry:
        out = entry["outputs"]
        if "headlines" in out or "descriptions" in out:
            # Old generation entry
            entry["generated"] = {
                "headlines":    out.get("headlines", []),
                "descriptions": out.get("descriptions", []),
            }
        elif any(k in out for k in ("ctr", "cpa", "roas")):
            # Old performance-ingest entry — move metrics to results
            entry["generated"] = {"headlines": [], "descriptions": []}
            if "results" not in entry:
                entry["results"] = out
        else:
            entry["generated"] = {"headlines": [], "descriptions": []}

    # ── Ensure generated always exists ────────────────────────────────────────
    if "generated" not in entry:
        entry["generated"] = {"headlines": [], "descriptions": []}

    # ── Ensure results always exists (None = not yet measured) ───────────────
    if "results" not in entry:
        entry["results"] = None

    return entry


def _rewrite(path: Path, entries: List[Dict]) -> None:
    """Overwrite the entire JSONL file from *entries*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def append_entry(
    memory_path: str | Path,
    *,
    campaign: str,
    ad_group: str = "",
    ad_id: str = "",
    hypothesis: str,
    angle: str = "",
    tag: str = "",
    variant_set_id: str,
    generated: Dict[str, List[str]],
    notes: str = "",
    results: Optional[Dict[str, Any]] = None,
) -> None:
    """Append one JSONL line to the memory log (current schema).

    Parameters
    ----------
    generated:
        Dict with ``headlines`` and ``descriptions`` lists.
    results:
        Optional performance metrics.  Keys: ctr, cpa, roas, impr, clicks, conv.
    """
    p = Path(memory_path)
    _ensure_file(p)
    entry = {
        "date":           datetime.now(timezone.utc).isoformat(),
        "campaign":       campaign,
        "ad_group":       ad_group,
        "ad_id":          ad_id,
        "hypothesis":     hypothesis,
        "angle":          angle,
        "tag":            tag,
        "variant_set_id": variant_set_id,
        "generated":      generated,
        "notes":          notes,
        "results":        results,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_memory(memory_path: str | Path) -> List[Dict]:
    """Load all memory entries, normalising old-schema entries on the fly."""
    p = Path(memory_path)
    if not p.exists():
        return []
    entries: List[Dict] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(_normalize(json.loads(line)))
    return entries


def ingest_performance(
    memory_path: str | Path,
    performance_df: pd.DataFrame,
) -> tuple:
    """Match performance rows to memory entries by ``variant_set_id``.

    For each row in *performance_df*:

    - If a matching entry exists  → update its ``results`` (and any supplied
      metadata) **in place**, then rewrite the file.
    - If no match                 → append a new minimal entry that holds the
      results so the data is never lost.

    Parameters
    ----------
    performance_df:
        DataFrame with at least a ``variant_set_id`` column.
        Metric columns (all optional): ``ctr``, ``cpa``, ``roas``,
        ``impr``, ``clicks``, ``conv``.
        Metadata columns (all optional): ``campaign``, ``ad_group``,
        ``ad_id``, ``angle``, ``notes``.

    Returns
    -------
    tuple[int, int]
        ``(updated, appended)`` — number of existing entries updated
        and number of new entries appended.
    """
    p = Path(memory_path)
    _ensure_file(p)
    entries = load_memory(p)

    # Build index: variant_set_id → list of positions (last = most recent)
    vsid_index: Dict[str, List[int]] = {}
    for i, e in enumerate(entries):
        vsid = e.get("variant_set_id", "")
        vsid_index.setdefault(vsid, []).append(i)

    updated = 0
    appended = 0

    for _, row in performance_df.iterrows():
        vsid = str(row.get("variant_set_id", "")).strip()

        # ── Build results dict from available numeric columns ─────────────────
        results: Dict[str, float] = {}
        for metric in ("ctr", "cpa", "roas", "impr", "clicks", "conv"):
            val = row.get(metric, None)
            if val is None:
                continue
            str_val = str(val).strip()
            if str_val in ("", "nan", "NaN"):
                continue
            try:
                results[metric] = float(str_val)
            except (ValueError, TypeError):
                pass

        if vsid in vsid_index:
            # ── Update most-recent matching entry ─────────────────────────────
            idx = vsid_index[vsid][-1]
            entries[idx]["results"] = results
            # Also update any supplied metadata fields
            for field in ("campaign", "ad_group", "ad_id", "angle", "notes"):
                val = row.get(field, None)
                if val is None:
                    continue
                str_val = str(val).strip()
                if str_val and str_val not in ("nan", "NaN"):
                    entries[idx][field] = str_val
            updated += 1
        else:
            # ── Append new entry with just the results ─────────────────────────
            def _str(key: str) -> str:
                v = row.get(key, "")
                return "" if str(v).strip() in ("nan", "NaN") else str(v).strip()

            new_entry = _normalize({
                "date":           datetime.now(timezone.utc).isoformat(),
                "campaign":       _str("campaign"),
                "ad_group":       _str("ad_group"),
                "ad_id":          _str("ad_id"),
                "hypothesis":     "performance_ingest",
                "angle":          _str("angle"),
                "tag":            _str("tag"),
                "variant_set_id": vsid,
                "generated":      {"headlines": [], "descriptions": []},
                "notes":          _str("notes"),
                "results":        results if results else None,
            })
            entries.append(new_entry)
            appended += 1

    # Rewrite the entire file
    _rewrite(p, entries)
    return updated, appended


# ─────────────────────────────────────────────────────────────────────────────
# Analytics helpers (used by Learning Board)
# ─────────────────────────────────────────────────────────────────────────────

def get_top_angles(
    entries: List[Dict],
    metric: str = "roas",
    n: int = 10,
    ascending: bool = False,
) -> pd.DataFrame:
    """Return a DataFrame of top creative angles ranked by *metric*.

    Only entries that have ``results`` set (not None/empty) are included.

    Parameters
    ----------
    metric:    One of ``roas``, ``cpa``, ``ctr``.
    ascending: ``True`` for CPA (lower = better); ``False`` for ROAS/CTR.

    Returns
    -------
    DataFrame with columns: angle, count, mean_{metric}, best_{metric}.
    """
    rows = []
    for e in entries:
        r = e.get("results")
        if not r:
            continue
        val = r.get(metric)
        if val is None:
            continue
        rows.append({
            "angle":    e.get("angle") or "(no angle)",
            "campaign": e.get("campaign", ""),
            metric:     float(val),
        })

    if not rows:
        return pd.DataFrame(
            columns=["angle", "count", f"mean_{metric}", f"best_{metric}"]
        )

    df = pd.DataFrame(rows)
    best_fn = "min" if ascending else "max"
    grp = df.groupby("angle")[metric].agg(["count", "mean", best_fn]).reset_index()
    grp.columns = ["angle", "count", f"mean_{metric}", f"best_{metric}"]
    grp = grp.sort_values(f"mean_{metric}", ascending=ascending).head(n)
    return grp.reset_index(drop=True)


def get_recent_experiments(
    entries: List[Dict],
    n: int = 20,
) -> pd.DataFrame:
    """Return a summary DataFrame of the last *n* experiments, newest first."""
    recent = list(reversed(entries[-n:]))
    rows = []
    for e in recent:
        r = e.get("results") or {}
        gen = e.get("generated") or {}
        rows.append({
            "date":           (e.get("date") or "")[:10],
            "campaign":       e.get("campaign", ""),
            "ad_id":          e.get("ad_id", ""),
            "angle":          e.get("angle") or "—",
            "variant_set_id": e.get("variant_set_id", ""),
            "headlines#":     len(gen.get("headlines", [])),
            "descs#":         len(gen.get("descriptions", [])),
            "results":        "✅" if r else "—",
            "roas":           r.get("roas"),
            "ctr":            r.get("ctr"),
            "cpa":            r.get("cpa"),
        })
    return pd.DataFrame(rows)
