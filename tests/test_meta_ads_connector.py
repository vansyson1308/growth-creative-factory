"""Tests for Meta Ads connector mapping and pull flow with mocking."""
from __future__ import annotations

from unittest.mock import patch

from gcf.connectors.meta_ads import map_meta_insight_to_adsrow, pull_meta_ads_rows


def _sample_insight():
    return {
        "campaign_name": "Camp",
        "adset_name": "Set A",
        "ad_id": "999",
        "impressions": "1000",
        "clicks": "50",
        "spend": "100.0",
        "actions": [
            {"action_type": "purchase", "value": "4"},
            {"action_type": "lead", "value": "7"},
        ],
        "action_values": [
            {"action_type": "purchase", "value": "300"},
        ],
        "date_start": "2026-01-01",
        "date_stop": "2026-01-30",
    }


def test_map_meta_insight_to_adsrow_metrics():
    row = map_meta_insight_to_adsrow(_sample_insight(), ["purchase", "lead"])
    assert row.platform == "meta_ads"
    assert row.conversions == 4
    assert row.revenue == 300
    assert row.ctr == 0.05
    assert row.cpa == 25.0
    assert row.roas == 3.0


def test_pull_meta_ads_rows_with_mock_account(tmp_path):
    out = tmp_path / "ads.csv"

    class MockAccount:
        def get_insights(self, fields=None, params=None):
            return [_sample_insight()]

    with patch("gcf.connectors.meta_ads.load_meta_ads_config") as mock_cfg:
        mock_cfg.return_value = type("Cfg", (), {
            "access_token": "tok",
            "ad_account_id": "act_1",
            "app_id": None,
            "app_secret": None,
            "action_priority": ["purchase", "lead"],
        })()
        rows = pull_meta_ads_rows(out_path=str(out), ad_account=MockAccount())

    assert len(rows) == 1
    assert out.exists()
