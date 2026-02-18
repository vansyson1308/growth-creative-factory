"""Internal unified schema for ads/performance rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional

Platform = Literal["google_ads", "meta_ads", "manual"]


@dataclass
class AdsRow:
    campaign: str
    ad_group: str
    ad_id: str
    platform: Platform = "manual"

    headline: str = ""
    description: str = ""
    final_url: Optional[str] = None

    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    conversions: float = 0.0
    revenue: float = 0.0

    ctr: float = 0.0
    cpa: float = 0.0
    roas: float = 0.0

    date_start: Optional[str] = None
    date_end: Optional[str] = None

    extra: Dict[str, Any] = field(default_factory=dict)

    def recompute_metrics(self) -> None:
        self.ctr = (self.clicks / self.impressions) if self.impressions > 0 else 0.0
        self.cpa = (self.spend / self.conversions) if self.conversions > 0 else 0.0
        self.roas = (self.revenue / self.spend) if self.spend > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "campaign": self.campaign,
            "ad_group": self.ad_group,
            "ad_id": self.ad_id,
            "platform": self.platform,
            "headline": self.headline,
            "description": self.description,
            "final_url": self.final_url,
            "impressions": self.impressions,
            "clicks": self.clicks,
            "spend": self.spend,
            "conversions": self.conversions,
            "revenue": self.revenue,
            "ctr": self.ctr,
            "cpa": self.cpa,
            "roas": self.roas,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "extra": self.extra,
        }
