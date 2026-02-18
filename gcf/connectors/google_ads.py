"""Google Ads connector: pull performance rows into unified AdsRow schema."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from gcf.config_google_ads import (
    GoogleAdsConfig,
    GoogleAdsConfigError,
    load_google_ads_config,
)
from gcf.mappers import adsrows_to_dataframe
from gcf.schema import AdsRow


class GoogleAdsConnectorError(RuntimeError):
    pass


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 15.0
    jitter_seconds: float = 0.5


def _build_client(cfg: GoogleAdsConfig):
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except Exception as exc:  # pragma: no cover
        raise GoogleAdsConnectorError(
            "google-ads SDK missing. Install dependency `google-ads` and retry."
        ) from exc

    payload = {
        "developer_token": cfg.developer_token,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "refresh_token": cfg.refresh_token,
        "use_proto_plus": True,
    }
    if cfg.login_customer_id:
        payload["login_customer_id"] = cfg.login_customer_id

    return GoogleAdsClient.load_from_dict(payload)


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def map_google_ads_row(row) -> AdsRow:
    campaign = getattr(getattr(row, "campaign", None), "name", "") or ""
    ad_group = getattr(getattr(row, "ad_group", None), "name", "") or ""
    ad_id = str(
        getattr(getattr(getattr(row, "ad_group_ad", None), "ad", None), "id", "") or ""
    )

    metrics = getattr(row, "metrics", None)
    segments = getattr(row, "segments", None)

    impressions = _safe_int(getattr(metrics, "impressions", 0))
    clicks = _safe_int(getattr(metrics, "clicks", 0))
    cost_micros = _safe_float(getattr(metrics, "cost_micros", 0))
    conversions = _safe_float(getattr(metrics, "conversions", 0.0))
    conversions_value = _safe_float(getattr(metrics, "conversions_value", 0.0))

    spend = cost_micros / 1_000_000.0
    revenue = conversions_value

    date_value = str(getattr(segments, "date", "") or "")
    date_start = date_value or None
    date_end = date_value or None

    ads_row = AdsRow(
        campaign=str(campaign),
        ad_group=str(ad_group),
        ad_id=ad_id,
        platform="google_ads",
        headline="",
        description="",
        final_url=None,
        impressions=impressions,
        clicks=clicks,
        spend=spend,
        conversions=conversions,
        revenue=revenue,
        date_start=date_start,
        date_end=date_end,
        extra={
            "source": "google_ads_api",
        },
    )
    ads_row.recompute_metrics()
    return ads_row


def _query(level: str, date_range: str) -> str:
    if level != "ad":
        raise GoogleAdsConnectorError("Only --level ad is currently supported.")

    return f"""
SELECT
  campaign.name,
  ad_group.name,
  ad_group_ad.ad.id,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_value,
  segments.date
FROM ad_group_ad
WHERE segments.date DURING {date_range}
""".strip()


def _is_retryable_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return any(
        k in s
        for k in ["rate", "quota", "resource exhausted", "429", "too many requests"]
    )


def _search_with_retry(service, customer_id: str, query: str, retry: RetryPolicy):
    attempt = 0
    while True:
        try:
            return service.search_stream(customer_id=customer_id, query=query)
        except Exception as exc:
            if attempt >= retry.max_retries or not _is_retryable_error(exc):
                raise
            sleep_s = min(
                retry.backoff_base_seconds * (2**attempt), retry.backoff_max_seconds
            )
            sleep_s += random.uniform(0, retry.jitter_seconds)
            time.sleep(sleep_s)
            attempt += 1


def pull_google_ads_rows(
    customer_id: str,
    date_range: str = "LAST_30_DAYS",
    level: str = "ad",
    out_path: Optional[str] = None,
    config_path: Optional[str] = None,
    retry_policy: Optional[RetryPolicy] = None,
    client=None,
) -> List[AdsRow]:
    """Pull rows from Google Ads and optionally write normalized CSV."""
    cfg = load_google_ads_config(customer_id=customer_id, yaml_path=config_path)
    client = client or _build_client(cfg)

    service = client.get_service("GoogleAdsService")
    q = _query(level, date_range)
    retry = retry_policy or RetryPolicy()

    try:
        stream = _search_with_retry(service, cfg.customer_id, q, retry)
    except GoogleAdsConfigError:
        raise
    except Exception as exc:
        msg = str(exc)
        if any(
            k in msg.lower() for k in ["permission", "unauthorized", "authentication"]
        ):
            raise GoogleAdsConnectorError(
                "Google Ads authentication/permission error. Verify developer token, OAuth creds, "
                "refresh token, and account access. See docs/CONNECT_GOOGLE_ADS.md"
            ) from exc
        raise GoogleAdsConnectorError(f"Google Ads pull failed: {exc}") from exc

    rows: List[AdsRow] = []
    for batch in stream:
        for r in getattr(batch, "results", []):
            rows.append(map_google_ads_row(r))

    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        df = adsrows_to_dataframe(rows)
        df.to_csv(p, index=False, encoding="utf-8")

    return rows
