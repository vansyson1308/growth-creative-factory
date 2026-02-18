"""Tests for selector module."""
import pytest
import pandas as pd
from gcf.selector import select_underperforming
from gcf.config import SelectorConfig


def _make_df(rows):
    df = pd.DataFrame(rows)
    df["ctr"] = df["clicks"] / df["impressions"].replace(0, float("nan"))
    df["cpa"] = df["cost"] / df["conversions"].replace(0, float("nan"))
    df["roas"] = df["revenue"] / df["cost"].replace(0, float("nan"))
    return df


class TestSelector:
    def test_selects_low_ctr(self):
        df = _make_df([{
            "ad_id": "1", "campaign": "C1", "ad_group": "AG1",
            "headline": "H", "description": "D",
            "impressions": 5000, "clicks": 10, "cost": 100, "conversions": 5, "revenue": 500,
        }])
        cfg = SelectorConfig(min_impressions=1000, max_ctr=0.02, max_cpa=50, min_roas=2.0)
        selected, reasons = select_underperforming(df, cfg)
        assert len(selected) == 1
        assert "CTR" in reasons[0]["reasons"]

    def test_skips_low_impressions(self):
        df = _make_df([{
            "ad_id": "1", "campaign": "C1", "ad_group": "AG1",
            "headline": "H", "description": "D",
            "impressions": 500, "clicks": 1, "cost": 100, "conversions": 1, "revenue": 50,
        }])
        cfg = SelectorConfig(min_impressions=1000, max_ctr=0.02, max_cpa=50, min_roas=2.0)
        selected, reasons = select_underperforming(df, cfg)
        assert len(selected) == 0

    def test_selects_high_cpa(self):
        df = _make_df([{
            "ad_id": "2", "campaign": "C1", "ad_group": "AG1",
            "headline": "H", "description": "D",
            "impressions": 5000, "clicks": 200, "cost": 1000, "conversions": 10, "revenue": 500,
        }])
        cfg = SelectorConfig(min_impressions=1000, max_ctr=0.05, max_cpa=50, min_roas=0.1)
        selected, _ = select_underperforming(df, cfg)
        assert len(selected) == 1

    def test_good_ad_not_selected(self):
        df = _make_df([{
            "ad_id": "3", "campaign": "C1", "ad_group": "AG1",
            "headline": "H", "description": "D",
            "impressions": 5000, "clicks": 250, "cost": 200, "conversions": 20, "revenue": 2000,
        }])
        cfg = SelectorConfig(min_impressions=1000, max_ctr=0.02, max_cpa=50, min_roas=2.0)
        selected, _ = select_underperforming(df, cfg)
        assert len(selected) == 0
