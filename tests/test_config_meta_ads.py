"""Tests for Meta Ads config validation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gcf.config_meta_ads import load_meta_ads_config, MetaAdsConfigError


def test_load_meta_ads_config_success():
    env = {
        "META_ACCESS_TOKEN": "tok",
        "META_AD_ACCOUNT_ID": "act_123",
    }
    with patch.dict("os.environ", env, clear=True):
        cfg = load_meta_ads_config()
    assert cfg.ad_account_id == "act_123"
    assert cfg.access_token == "tok"


def test_invalid_account_format_raises():
    env = {
        "META_ACCESS_TOKEN": "tok",
        "META_AD_ACCOUNT_ID": "123",
    }
    with patch.dict("os.environ", env, clear=True):
        with pytest.raises(MetaAdsConfigError):
            load_meta_ads_config()
