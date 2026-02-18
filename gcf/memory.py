"""Memory log — stores hypothesis / variant / result across runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def _ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.touch()


def append_entry(
    memory_path: str | Path,
    campaign: str,
    hypothesis: str,
    variant_set_id: str,
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    notes: str = "",
) -> None:
    """Append one JSONL line to the memory log."""
    p = Path(memory_path)
    _ensure_file(p)
    entry = {
        "date": datetime.now(timezone.utc).isoformat(),
        "campaign": campaign,
        "hypothesis": hypothesis,
        "variant_set_id": variant_set_id,
        "inputs": inputs,
        "outputs": outputs,
        "notes": notes,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def ingest_performance(
    memory_path: str | Path,
    performance_df: pd.DataFrame,
) -> int:
    """Read performance.csv rows and append results to memory.

    Expected columns: variant_set_id, ctr, cpa, roas, notes (optional).
    Returns number of rows ingested.
    """
    p = Path(memory_path)
    _ensure_file(p)
    count = 0
    for _, row in performance_df.iterrows():
        entry = {
            "date": datetime.now(timezone.utc).isoformat(),
            "campaign": row.get("campaign", ""),
            "hypothesis": "performance_ingest",
            "variant_set_id": str(row.get("variant_set_id", "")),
            "inputs": {},
            "outputs": {
                "ctr": float(row.get("ctr", 0)),
                "cpa": float(row.get("cpa", 0)),
                "roas": float(row.get("roas", 0)),
            },
            "notes": str(row.get("notes", "")),
        }
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        count += 1
    return count


def load_memory(memory_path: str | Path) -> List[Dict]:
    """Load all memory entries as a list of dicts."""
    p = Path(memory_path)
    if not p.exists():
        return []
    entries = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries
