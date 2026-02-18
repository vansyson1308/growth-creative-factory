"""CSV / TSV read-write helpers."""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict

import pandas as pd


_REQUIRED_COLUMNS = {"campaign", "ad_group", "ad_id", "headline", "description"}
_METRIC_COLUMNS = ("impressions", "clicks", "cost", "conversions", "revenue")


class InputSchemaError(ValueError):
    """Raised when the input CSV is missing required columns."""


def read_ads_csv(path: str | Path) -> pd.DataFrame:
    """Read an ads CSV. Expected columns: campaign, ad_group, ad_id,
    headline, description, impressions, clicks, cost, conversions, revenue.

    Raises ``InputSchemaError`` if any required column is missing.
    Missing *metric* columns are filled with 0.
    """
    df = pd.read_csv(path, dtype={"ad_id": str})
    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise InputSchemaError(
            f"Input CSV is missing required column(s): {', '.join(sorted(missing))}. "
            f"Expected: {', '.join(sorted(_REQUIRED_COLUMNS))}"
        )
    for col in _METRIC_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    # Derived metrics
    df["ctr"] = df["clicks"] / df["impressions"].replace(0, float("nan"))
    df["cpa"] = df["cost"] / df["conversions"].replace(0, float("nan"))
    df["roas"] = df["revenue"] / df["cost"].replace(0, float("nan"))
    return df


def write_new_ads_csv(rows: List[Dict], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(p, index=False, encoding="utf-8")
    return p


def write_figma_tsv(rows: List[Dict], path: str | Path) -> Path:
    """Write H1\\tDESC\\tTAG tab-separated file.

    Encoding: **UTF-8 without BOM** (``utf-8``, *not* ``utf-8-sig``).
    Figma's plugin and most spreadsheet importers expect a clean UTF-8 file
    with no byte-order mark.  Required columns: H1, DESC, TAG.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    # Ensure required columns exist and appear in the correct order
    for col in ("H1", "DESC", "TAG"):
        if col not in df.columns:
            df[col] = ""
    df = df[["H1", "DESC", "TAG"]]
    # encoding="utf-8" → UTF-8, NO BOM (utf-8-sig would add a BOM)
    df.to_csv(p, sep="\t", index=False, encoding="utf-8")
    return p


def write_report(text: str, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def read_performance_csv(path: str | Path) -> pd.DataFrame:
    """Read a performance results CSV for memory ingestion."""
    return pd.read_csv(path, dtype={"variant_set_id": str})
