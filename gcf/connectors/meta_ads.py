"""Meta Ads connector: pull insights into unified AdsRow schema."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from gcf.config_meta_ads import MetaAdsConfigError, load_meta_ads_config
from gcf.mappers import adsrows_to_dataframe
from gcf.schema import AdsRow


class MetaAdsConnectorError(RuntimeError):
    pass


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 20.0
    jitter_seconds: float = 0.5


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _extract_actions(actions) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not actions:
        return out
    for a in actions:
        atype = str(a.get("action_type", "") or "").strip()
        val = _safe_float(a.get("value", 0.0), 0.0)
        if not atype:
            continue
        out[atype] = out.get(atype, 0.0) + val
    return out


def _pick_by_priority(values: Dict[str, float], priorities: List[str]) -> float:
    for p in priorities:
        if p in values:
            return values[p]
    return 0.0


def map_meta_insight_to_adsrow(insight: dict, action_priority: List[str]) -> AdsRow:
    impressions = _safe_int(insight.get("impressions", 0))
    clicks = _safe_int(insight.get("clicks", 0))
    spend = _safe_float(insight.get("spend", 0.0))

    action_counts = _extract_actions(insight.get("actions"))
    action_values = _extract_actions(insight.get("action_values"))

    conversions = _pick_by_priority(action_counts, action_priority)
    revenue = _pick_by_priority(action_values, action_priority)

    row = AdsRow(
        campaign=str(insight.get("campaign_name", "") or ""),
        ad_group=str(insight.get("adset_name", "") or ""),
        ad_id=str(insight.get("ad_id", "") or ""),
        platform="meta_ads",
        headline="",
        description="",
        final_url=None,
        impressions=impressions,
        clicks=clicks,
        spend=spend,
        conversions=conversions,
        revenue=revenue,
        date_start=str(insight.get("date_start", "") or "") or None,
        date_end=str(insight.get("date_stop", "") or "") or None,
        extra={
            "source": "meta_ads_api",
            "actions": action_counts,
            "action_values": action_values,
        },
    )
    row.recompute_metrics()
    return row


def _is_retryable_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(
        k in s
        for k in ["rate", "too many", "tempor", "limit", "429", "17", "32", "613"]
    )


def _fetch_with_retry(ad_account, fields, params, retry: RetryPolicy):
    attempt = 0
    while True:
        try:
            return ad_account.get_insights(fields=fields, params=params)
        except Exception as exc:
            if attempt >= retry.max_retries or not _is_retryable_error(exc):
                raise
            sleep_s = min(
                retry.backoff_base_seconds * (2**attempt), retry.backoff_max_seconds
            )
            sleep_s += random.uniform(0, retry.jitter_seconds)
            time.sleep(sleep_s)
            attempt += 1


def pull_meta_ads_rows(
    date_preset: str = "last_30d",
    out_path: Optional[str] = None,
    action_priority: Optional[List[str]] = None,
    retry_policy: Optional[RetryPolicy] = None,
    ad_account=None,
) -> List[AdsRow]:
    cfg = load_meta_ads_config(action_priority=action_priority)

    if ad_account is None:
        try:
            from facebook_business.api import FacebookAdsApi
            from facebook_business.adobjects.adaccount import AdAccount
        except Exception as exc:  # pragma: no cover
            raise MetaAdsConnectorError(
                "facebook_business SDK missing. Install `facebook-business` and retry."
            ) from exc

        try:
            FacebookAdsApi.init(
                access_token=cfg.access_token,
                app_id=cfg.app_id,
                app_secret=cfg.app_secret,
            )
            ad_account = AdAccount(cfg.ad_account_id)
        except Exception as exc:
            raise MetaAdsConnectorError(
                "Failed to initialize Meta Ads API. Verify token/account permissions. "
                "See docs/CONNECT_META_ADS.md"
            ) from exc

    fields = [
        "campaign_name",
        "adset_name",
        "ad_id",
        "impressions",
        "clicks",
        "spend",
        "actions",
        "action_values",
        "date_start",
        "date_stop",
    ]
    params = {
        "date_preset": date_preset,
        "level": "ad",
        "limit": 500,
    }

    retry = retry_policy or RetryPolicy()

    try:
        cursor = _fetch_with_retry(ad_account, fields, params, retry)
    except MetaAdsConfigError:
        raise
    except Exception as exc:
        msg = str(exc).lower()
        if any(k in msg for k in ["oauth", "permission", "token", "190", "200"]):
            raise MetaAdsConnectorError(
                "Meta Ads auth/permission error. Check META_ACCESS_TOKEN scopes and account access. "
                "See docs/CONNECT_META_ADS.md"
            ) from exc
        raise MetaAdsConnectorError(f"Meta Ads pull failed: {exc}") from exc

    rows: List[AdsRow] = []
    try:
        for insight in cursor:  # SDK cursor handles pagination internally
            rows.append(map_meta_insight_to_adsrow(dict(insight), cfg.action_priority))
    except Exception as exc:
        if _is_retryable_error(exc):
            # one more full retry pass on transient paging errors
            cursor = _fetch_with_retry(ad_account, fields, params, retry)
            rows = [
                map_meta_insight_to_adsrow(dict(i), cfg.action_priority) for i in cursor
            ]
        else:
            raise MetaAdsConnectorError(f"Meta Ads pagination failed: {exc}") from exc

    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        df = adsrows_to_dataframe(rows)
        df.to_csv(p, index=False, encoding="utf-8")

    return rows
