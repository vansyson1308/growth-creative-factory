"""Select underperforming ads and generate LLM-powered improvement strategies."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from jinja2 import Template

from gcf.config import AppConfig, SelectorConfig

_STRATEGY_PROMPT_PATH = Path(__file__).parent / "prompts" / "selector_prompt.txt"


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based selection (unchanged)
# ─────────────────────────────────────────────────────────────────────────────


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
        reasons.append(
            {
                "ad_id": row["ad_id"],
                "campaign": row.get("campaign", ""),
                "ad_group": row.get("ad_group", ""),
                "reasons": "; ".join(r),
            }
        )

    return selected, reasons


# ─────────────────────────────────────────────────────────────────────────────
# LLM-powered strategy generation (new)
# ─────────────────────────────────────────────────────────────────────────────


def _load_strategy_template() -> Template:
    return Template(_STRATEGY_PROMPT_PATH.read_text(encoding="utf-8"))


def _parse_strategy_json(raw: str, ad_id: str) -> Dict:
    """Extract strategy dict from LLM response. Returns safe fallback on error."""
    text = raw.strip()

    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    try:
        data = json.loads(text)
        if "strategy" in data:
            return data
    except (json.JSONDecodeError, AttributeError):
        pass

    # Safe fallback so pipeline never crashes on bad LLM output
    return {
        "ad_id": ad_id,
        "analysis": "Analysis unavailable.",
        "strategy": f"Improve engagement for ad {ad_id}",
    }


def generate_strategy(
    provider,
    ad_row: Dict,
    issues: str,
    cfg: AppConfig,
) -> Dict:
    """Call the selector LLM prompt to get a root-cause analysis and strategy.

    Parameters
    ----------
    provider:
        The active LLM (or mock) provider.
    ad_row:
        A single ad row dict (keys: ad_id, campaign, ad_group, headline,
        description, ctr, cpa, roas, impressions, ...).
    issues:
        Human-readable issues string, e.g. "CTR 0.01 < 0.02; ROAS 0.4 < 2.0".
    cfg:
        Full application config.

    Returns
    -------
    dict with keys: ad_id, analysis, strategy
    """
    ad_id = ad_row.get("ad_id", "")
    tmpl = _load_strategy_template()
    prompt = tmpl.render(
        ad_id=ad_id,
        campaign=ad_row.get("campaign", ""),
        ad_group=ad_row.get("ad_group", ""),
        headline=ad_row.get("headline", ""),
        description=ad_row.get("description", ""),
        impressions=ad_row.get("impressions", ""),
        ctr=ad_row.get("ctr", ""),
        cpa=ad_row.get("cpa", ""),
        roas=ad_row.get("roas", ""),
        issues=issues,
    )

    raw = provider.generate(
        prompt,
        system="You are an expert performance marketing analyst. Return ONLY valid JSON.",
    )
    return _parse_strategy_json(raw, ad_id)
