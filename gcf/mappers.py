"""Mapping utilities between external tabular data and internal AdsRow schema."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

import pandas as pd

from gcf.schema import AdsRow

REQUIRED_INPUT_COLUMNS = {"campaign", "ad_group", "ad_id", "headline", "description"}


def _to_int(v: Any) -> int:
    try:
        if pd.isna(v):
            return 0
    except Exception:
        pass
    try:
        return int(float(v))
    except Exception:
        return 0


def _to_float(v: Any) -> float:
    try:
        if pd.isna(v):
            return 0.0
    except Exception:
        pass
    try:
        return float(v)
    except Exception:
        return 0.0


def _normalize_platform(v: Any) -> str:
    s = str(v or "manual").strip().lower()
    if s in {"google_ads", "meta_ads", "manual"}:
        return s
    if s in {"google", "googleads", "google ads"}:
        return "google_ads"
    if s in {"meta", "facebook", "meta ads", "meta_ads"}:
        return "meta_ads"
    return "manual"


def map_record_to_adsrow(record: Dict[str, Any]) -> AdsRow:
    metric_map = {
        "spend": record.get("spend", record.get("cost", 0.0)),
    }
    row = AdsRow(
        campaign=str(record.get("campaign", "") or ""),
        ad_group=str(record.get("ad_group", "") or ""),
        ad_id=str(record.get("ad_id", "") or ""),
        platform=_normalize_platform(record.get("platform")),
        headline=str(record.get("headline", "") or ""),
        description=str(record.get("description", "") or ""),
        final_url=(str(record.get("final_url")).strip() if record.get("final_url") not in (None, "") else None),
        impressions=_to_int(record.get("impressions", 0)),
        clicks=_to_int(record.get("clicks", 0)),
        spend=_to_float(metric_map["spend"]),
        conversions=_to_float(record.get("conversions", 0)),
        revenue=_to_float(record.get("revenue", 0)),
        ctr=_to_float(record.get("ctr", 0)),
        cpa=_to_float(record.get("cpa", 0)),
        roas=_to_float(record.get("roas", 0)),
        date_start=(str(record.get("date_start")).strip() if record.get("date_start") not in (None, "") else None),
        date_end=(str(record.get("date_end")).strip() if record.get("date_end") not in (None, "") else None),
        extra={
            k: v
            for k, v in record.items()
            if k
            not in {
                "campaign", "ad_group", "ad_id", "platform", "headline", "description", "final_url",
                "impressions", "clicks", "spend", "cost", "conversions", "revenue", "ctr", "cpa", "roas",
                "date_start", "date_end",
            }
        },
    )

    # Recompute from primitive metrics for connector consistency.
    row.recompute_metrics()
    return row


def map_dataframe_to_adsrows(df: pd.DataFrame) -> List[AdsRow]:
    return [map_record_to_adsrow(r) for r in df.to_dict(orient="records")]


def adsrows_to_dataframe(rows: Iterable[AdsRow]) -> pd.DataFrame:
    data = [r.to_dict() for r in rows]
    return pd.DataFrame(data)
