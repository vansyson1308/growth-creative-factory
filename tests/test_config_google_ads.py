"""Tests for Google Ads config validation."""

from __future__ import annotations

import pytest

from gcf.config_google_ads import GoogleAdsConfigError, load_google_ads_config


def test_load_from_yaml(tmp_path):
    p = tmp_path / "google-ads.yaml"
    p.write_text(
        "developer_token: d\n"
        "client_id: cid\n"
        "client_secret: sec\n"
        "refresh_token: rt\n"
        "customer_id: 123\n",
        encoding="utf-8",
    )
    cfg = load_google_ads_config(yaml_path=str(p))
    assert cfg.customer_id == "123"
    assert cfg.developer_token == "d"


def test_missing_required_raises(tmp_path):
    p = tmp_path / "google-ads.yaml"
    p.write_text("developer_token: d\n", encoding="utf-8")
    with pytest.raises(GoogleAdsConfigError):
        load_google_ads_config(yaml_path=str(p))
