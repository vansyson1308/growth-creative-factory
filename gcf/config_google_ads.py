"""Configuration loader/validator for Google Ads connector (BYO creds)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


class GoogleAdsConfigError(ValueError):
    pass


@dataclass
class GoogleAdsConfig:
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    customer_id: str
    login_customer_id: Optional[str] = None


def _clean(v) -> str:
    return str(v or "").strip()


def load_google_ads_config(customer_id: Optional[str] = None, yaml_path: Optional[str] = None) -> GoogleAdsConfig:
    """Load config from env and optional google-ads.yaml style file.

    Priority:
    1) explicit *yaml_path*
    2) env `GCF_GOOGLE_ADS_YAML`
    3) default `google-ads.yaml` in cwd
    4) env vars only
    """
    cfg_path = yaml_path or os.environ.get("GCF_GOOGLE_ADS_YAML") or "google-ads.yaml"
    raw = {}
    p = Path(cfg_path)
    if p.exists():
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    # Accept both canonical and uppercase env style keys
    dev = _clean(os.environ.get("GCF_GOOGLE_ADS_DEVELOPER_TOKEN") or raw.get("developer_token"))
    cid = _clean(os.environ.get("GCF_GOOGLE_ADS_CLIENT_ID") or raw.get("client_id"))
    csec = _clean(os.environ.get("GCF_GOOGLE_ADS_CLIENT_SECRET") or raw.get("client_secret"))
    rtok = _clean(os.environ.get("GCF_GOOGLE_ADS_REFRESH_TOKEN") or raw.get("refresh_token"))
    lcid = _clean(os.environ.get("GCF_GOOGLE_ADS_LOGIN_CUSTOMER_ID") or raw.get("login_customer_id")) or None

    cust = _clean(customer_id or os.environ.get("GCF_GOOGLE_ADS_CUSTOMER_ID") or raw.get("customer_id"))

    missing = [
        name for name, value in [
            ("developer_token", dev),
            ("client_id", cid),
            ("client_secret", csec),
            ("refresh_token", rtok),
            ("customer_id", cust),
        ] if not value
    ]
    if missing:
        raise GoogleAdsConfigError(
            "Missing Google Ads config: " + ", ".join(missing) + ". "
            "Set env vars or provide google-ads.yaml. See docs/CONNECT_GOOGLE_ADS.md"
        )

    return GoogleAdsConfig(
        developer_token=dev,
        client_id=cid,
        client_secret=csec,
        refresh_token=rtok,
        customer_id=cust,
        login_customer_id=lcid,
    )
