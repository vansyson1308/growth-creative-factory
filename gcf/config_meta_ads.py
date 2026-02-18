"""Configuration loader/validator for Meta Ads connector (BYO creds)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


class MetaAdsConfigError(ValueError):
    pass


@dataclass
class MetaAdsConfig:
    access_token: str
    ad_account_id: str
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    action_priority: List[str] = field(
        default_factory=lambda: ["purchase", "lead", "complete_registration"]
    )


def _clean(v) -> str:
    return str(v or "").strip()


def load_meta_ads_config(action_priority: Optional[List[str]] = None) -> MetaAdsConfig:
    token = _clean(os.environ.get("META_ACCESS_TOKEN"))
    account = _clean(os.environ.get("META_AD_ACCOUNT_ID"))
    app_id = _clean(os.environ.get("META_APP_ID")) or None
    app_secret = _clean(os.environ.get("META_APP_SECRET")) or None

    if not token:
        raise MetaAdsConfigError(
            "META_ACCESS_TOKEN is missing. Set it in environment. See docs/CONNECT_META_ADS.md"
        )
    if not account:
        raise MetaAdsConfigError(
            "META_AD_ACCOUNT_ID is missing. Expected format: act_<id>. See docs/CONNECT_META_ADS.md"
        )
    if not account.startswith("act_"):
        raise MetaAdsConfigError("META_AD_ACCOUNT_ID must be in format act_<id>.")

    prio = action_priority
    if prio is None:
        raw = _clean(os.environ.get("META_ACTION_PRIORITY"))
        if raw:
            prio = [x.strip() for x in raw.split(",") if x.strip()]
        else:
            prio = ["purchase", "lead", "complete_registration"]

    return MetaAdsConfig(
        access_token=token,
        ad_account_id=account,
        app_id=app_id,
        app_secret=app_secret,
        action_priority=prio,
    )
