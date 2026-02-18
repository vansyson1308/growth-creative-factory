"""Select underperforming ads based on configurable thresholds."""
from __future__ import annotations

from typing import List, Dict, Tuple

import pandas as pd

from gcf.config import SelectorConfig


def select_underperforming(
    df: pd.DataFrame,
    cfg: SelectorConfig,
) -> Tuple[pd.DataFrame, List[Dict]]:
    """Return (filtered_df, reasons_list).

    An ad is underperforming when it has >= min_impressions AND
    at least ONE of these holds:
      - CTR < max_ctr
      - CPA > max_cpa  (only if CPA is not NaN)
      - ROAS < min_roas (only if ROAS is not NaN)
    """
    mask_impr = df["impressions"] >= cfg.min_impressions

    mask_ctr = df["ctr"] < cfg.max_ctr
    mask_cpa = (df["cpa"] > cfg.max_cpa) & df["cpa"].notna()
    mask_roas = (df["roas"] < cfg.min_roas) & df["roas"].notna()

    mask_any = mask_ctr | mask_cpa | mask_roas
    mask = mask_impr & mask_any

    selected = df[mask].copy()

    reasons: List[Dict] = []
    for _, row in selected.iterrows():
        r: List[str] = []
        if row["ctr"] < cfg.max_ctr:
            r.append(f"CTR {row['ctr']:.4f} < {cfg.max_ctr}")
        if pd.notna(row["cpa"]) and row["cpa"] > cfg.max_cpa:
            r.append(f"CPA {row['cpa']:.2f} > {cfg.max_cpa}")
        if pd.notna(row["roas"]) and row["roas"] < cfg.min_roas:
            r.append(f"ROAS {row['roas']:.2f} < {cfg.min_roas}")
        reasons.append({
            "ad_id": row["ad_id"],
            "campaign": row.get("campaign", ""),
            "ad_group": row.get("ad_group", ""),
            "reasons": "; ".join(r),
        })

    return selected, reasons
