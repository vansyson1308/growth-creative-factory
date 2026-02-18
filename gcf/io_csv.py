"""CSV / TSV read-write helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd

from gcf.mappers import (
    REQUIRED_INPUT_COLUMNS,
    adsrows_to_dataframe,
    map_dataframe_to_adsrows,
)


class InputSchemaError(ValueError):
    """Raised when the input CSV is missing required columns."""


def _normalize_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = [
        "impressions",
        "clicks",
        "spend",
        "cost",
        "conversions",
        "revenue",
        "ctr",
        "cpa",
        "roas",
    ]
    out = df.copy()
    for col in numeric_cols:
        if col not in out.columns:
            out[col] = 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    # Standardize spend/cost aliases before schema mapping.
    if "spend" in out.columns and "cost" in out.columns:
        mask = (out["spend"] == 0) & (out["cost"] != 0)
        out.loc[mask, "spend"] = out.loc[mask, "cost"]
    elif "spend" not in out.columns and "cost" in out.columns:
        out["spend"] = out["cost"]
    elif "cost" not in out.columns and "spend" in out.columns:
        out["cost"] = out["spend"]

    out["impressions"] = out["impressions"].astype(int)
    out["clicks"] = out["clicks"].astype(int)
    return out


def _validate_required_columns(df: pd.DataFrame) -> None:
    missing = REQUIRED_INPUT_COLUMNS - set(df.columns)
    if not missing:
        return

    hints = {
        "campaign": "Add campaign name column from platform export.",
        "ad_group": "Add ad set / ad group column.",
        "ad_id": "Add unique ad identifier column.",
        "headline": "Map primary text/headline field to headline.",
        "description": "Map body/description field to description.",
    }
    missing_list = ", ".join(sorted(missing))
    detail = " | ".join(f"{m}: {hints.get(m, 'required')}" for m in sorted(missing))
    raise InputSchemaError(
        f"Input CSV is missing required column(s): {missing_list}. Suggestions: {detail}"
    )


def read_ads_csv(path: str | Path) -> pd.DataFrame:
    """Read + validate ads CSV and normalize it into internal AdsRow schema DataFrame."""
    df = pd.read_csv(path, dtype={"ad_id": str})
    _validate_required_columns(df)
    df = _normalize_numeric_columns(df)

    rows = map_dataframe_to_adsrows(df)
    normalized = adsrows_to_dataframe(rows)

    # Keep compatibility alias expected by selectors/tests
    if "spend" in normalized.columns and "cost" not in normalized.columns:
        normalized["cost"] = normalized["spend"]

    return normalized


def write_new_ads_csv(rows: List[Dict], path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(p, index=False, encoding="utf-8")
    return p


def write_figma_tsv(rows: List[Dict], path: str | Path) -> Path:
    """Write H1	DESC	TAG tab-separated file in UTF-8 (no BOM)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for col in ("H1", "DESC", "TAG"):
        if col not in df.columns:
            df[col] = ""
    df = df[["H1", "DESC", "TAG"]]
    df.to_csv(p, sep="	", index=False, encoding="utf-8")
    return p


def write_handoff_csv(rows: List[Dict], path: str | Path) -> Path:
    """Write the marketing handoff sheet as CSV."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for col in ("variant_set_id", "TAG", "H1", "DESC", "status", "notes"):
        if col not in df.columns:
            df[col] = ""
    df = df[["variant_set_id", "TAG", "H1", "DESC", "status", "notes"]]
    df.to_csv(p, index=False, encoding="utf-8")
    return p


def write_report(text: str, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def read_performance_csv(path: str | Path) -> pd.DataFrame:
    """Read a performance results CSV for memory ingestion."""
    return pd.read_csv(path, dtype={"variant_set_id": str})
