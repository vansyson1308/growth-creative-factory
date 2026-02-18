"""Tests for unified schema mapping."""
from __future__ import annotations

import pandas as pd

from gcf.mappers import map_dataframe_to_adsrows, adsrows_to_dataframe


def test_map_csv_to_adsrow_recomputes_metrics():
    df = pd.DataFrame([
        {
            "campaign": "C1",
            "ad_group": "G1",
            "ad_id": "A1",
            "platform": "google",
            "headline": "H",
            "description": "D",
            "impressions": "1000",
            "clicks": "20",
            "cost": "50",
            "conversions": "5",
            "revenue": "200",
            "unknown_col": "x",
        }
    ])
    rows = map_dataframe_to_adsrows(df)
    assert len(rows) == 1
    row = rows[0]
    assert row.platform == "google_ads"
    assert row.ctr == 0.02
    assert row.cpa == 10.0
    assert row.roas == 4.0
    assert row.extra["unknown_col"] == "x"


def test_adsrows_to_dataframe_has_internal_columns():
    df = pd.DataFrame([
        {
            "campaign": "C1", "ad_group": "G1", "ad_id": "A1",
            "headline": "H", "description": "D"
        }
    ])
    out = adsrows_to_dataframe(map_dataframe_to_adsrows(df))
    assert {"campaign", "ad_group", "ad_id", "spend", "ctr", "extra"}.issubset(set(out.columns))
