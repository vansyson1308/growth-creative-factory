"""Tests for Google Ads connector mapping/metrics with mocked client."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from gcf.connectors.google_ads import map_google_ads_row, pull_google_ads_rows


def _mock_row():
    return SimpleNamespace(
        campaign=SimpleNamespace(name="Camp"),
        ad_group=SimpleNamespace(name="Group"),
        ad_group_ad=SimpleNamespace(ad=SimpleNamespace(id=12345)),
        metrics=SimpleNamespace(
            impressions=1000,
            clicks=20,
            cost_micros=50000000,
            conversions=5,
            conversions_value=200.0,
        ),
        segments=SimpleNamespace(date="2026-01-01"),
    )


def test_map_google_ads_row_computes_metrics():
    row = map_google_ads_row(_mock_row())
    assert row.platform == "google_ads"
    assert row.spend == 50.0
    assert row.ctr == 0.02
    assert row.cpa == 10.0
    assert row.roas == 4.0


def test_pull_google_ads_rows_with_mock_client(tmp_path):
    out = tmp_path / "ads.csv"
    batch = SimpleNamespace(results=[_mock_row()])
    service = SimpleNamespace(search_stream=lambda customer_id, query: [batch])
    client = SimpleNamespace(get_service=lambda name: service)

    with patch("gcf.connectors.google_ads.load_google_ads_config") as mock_cfg:
        mock_cfg.return_value = SimpleNamespace(
            developer_token="d", client_id="id", client_secret="sec",
            refresh_token="rt", customer_id="123", login_customer_id=None,
        )
        rows = pull_google_ads_rows(
            customer_id="123",
            out_path=str(out),
            client=client,
        )

    assert len(rows) == 1
    assert out.exists()
