"""Main pipeline — orchestrates selector → headline → description → output."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from itertools import product as itertools_product
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from gcf.config import AppConfig
from gcf.io_csv import (
    read_ads_csv,
    write_figma_tsv,
    write_new_ads_csv,
    write_report,
)
from gcf.selector import select_underperforming
from gcf.generator_headline import generate_headlines
from gcf.generator_description import generate_descriptions
from gcf.memory import append_entry, load_memory
from gcf.providers.base import BaseProvider


def _build_memory_context(cfg: AppConfig, campaign: str) -> str:
    """Pull relevant memory entries for a campaign."""
    entries = load_memory(cfg.memory.path)
    relevant = [e for e in entries if e.get("campaign", "") == campaign]
    if not relevant:
        return ""
    lines = []
    for e in relevant[-5:]:  # last 5 entries
        lines.append(
            f"- [{e.get('date','')}] hypothesis={e.get('hypothesis','')}, "
            f"outputs={e.get('outputs',{})}, notes={e.get('notes','')}"
        )
    return "\n".join(lines)


def run_pipeline(
    input_path: str | Path,
    output_dir: str | Path,
    cfg: AppConfig,
    provider: BaseProvider,
    mode: str = "dry",
) -> Dict:
    """Execute the full pipeline. Returns summary dict."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read input
    df = read_ads_csv(input_path)

    # 2. Select underperforming
    selected, reasons = select_underperforming(df, cfg.selector)

    if selected.empty:
        summary = {
            "total_ads": len(df),
            "selected": 0,
            "variants_generated": 0,
            "pass_count": 0,
            "fail_count": 0,
            "message": "No underperforming ads found with current thresholds.",
        }
        write_report(_format_report(summary, []), output_dir / "report.md")
        return summary

    # 3. Generate variations for each selected ad
    new_ads_rows: List[Dict] = []
    figma_rows: List[Dict] = []
    total_pass = 0
    total_fail = 0
    report_details: List[Dict] = []

    for idx, (_, row) in enumerate(selected.iterrows()):
        ad = row.to_dict()
        reason_info = reasons[idx] if idx < len(reasons) else {}
        ad["_issue"] = reason_info.get("reasons", "")
        strategy = f"Improve engagement for ad {ad.get('ad_id', '')} — issues: {ad['_issue']}"

        memory_ctx = _build_memory_context(cfg, ad.get("campaign", ""))

        # Generate
        headlines, h_fail = generate_headlines(provider, ad, strategy, cfg, memory_ctx)
        descriptions, d_fail = generate_descriptions(provider, ad, strategy, cfg, memory_ctx)

        h_count = len(headlines)
        d_count = len(descriptions)
        total_pass += h_count + d_count
        total_fail += h_fail + d_fail

        # Create variant set
        variant_set_id = f"vs_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{idx:03d}"

        # Cross-product (capped)
        combos = list(itertools_product(headlines, descriptions))
        max_v = cfg.generation.max_variants_per_run
        combos = combos[:max_v]

        for ci, (h, d) in enumerate(combos):
            tag = f"V{ci+1:03d}"
            new_ads_rows.append({
                "campaign": ad.get("campaign", ""),
                "ad_group": ad.get("ad_group", ""),
                "ad_id": ad.get("ad_id", ""),
                "original_headline": ad.get("headline", ""),
                "original_description": ad.get("description", ""),
                "variant_headline": h,
                "variant_description": d,
                "variant_set_id": variant_set_id,
                "tag": tag,
            })
            figma_rows.append({"H1": h, "DESC": d, "TAG": tag})

        # Memory log
        append_entry(
            memory_path=cfg.memory.path,
            campaign=ad.get("campaign", ""),
            ad_group=ad.get("ad_group", ""),
            ad_id=ad.get("ad_id", ""),
            hypothesis=strategy,
            variant_set_id=variant_set_id,
            generated={"headlines": headlines, "descriptions": descriptions},
            notes=f"mode={mode}",
        )

        report_details.append({
            "ad_id": ad.get("ad_id", ""),
            "campaign": ad.get("campaign", ""),
            "issue": ad["_issue"],
            "strategy": strategy,
            "headlines_generated": h_count,
            "descriptions_generated": d_count,
            "combos": len(combos),
            "variant_set_id": variant_set_id,
        })

    # 4. Write outputs
    write_new_ads_csv(new_ads_rows, output_dir / "new_ads.csv")
    write_figma_tsv(figma_rows, output_dir / "figma_variations.tsv")

    summary = {
        "total_ads": len(df),
        "selected": len(selected),
        "variants_generated": len(new_ads_rows),
        "pass_count": total_pass,
        "fail_count": total_fail,
        "message": "Pipeline completed successfully.",
    }
    write_report(_format_report(summary, report_details), output_dir / "report.md")

    return summary


def _format_report(summary: Dict, details: List[Dict]) -> str:
    lines = [
        "# Growth Creative Factory — Run Report",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        f"- Total ads in input: {summary['total_ads']}",
        f"- Ads selected (underperforming): {summary['selected']}",
        f"- Total variant combinations generated: {summary['variants_generated']}",
        f"- Copy pieces passed validation: {summary['pass_count']}",
        f"- Copy pieces failed validation: {summary['fail_count']}",
        "",
    ]
    if not details:
        lines.append(summary.get("message", ""))
        return "\n".join(lines)

    lines.append("## Details per Ad")
    lines.append("")
    for d in details:
        lines.append(f"### Ad `{d['ad_id']}` (campaign: {d['campaign']})")
        lines.append(f"- **Issue:** {d['issue']}")
        lines.append(f"- **Strategy:** {d['strategy']}")
        lines.append(f"- **Headlines generated:** {d['headlines_generated']}")
        lines.append(f"- **Descriptions generated:** {d['descriptions_generated']}")
        lines.append(f"- **Combinations:** {d['combos']}")
        lines.append(f"- **Variant set ID:** `{d['variant_set_id']}`")
        lines.append("")

    return "\n".join(lines)
