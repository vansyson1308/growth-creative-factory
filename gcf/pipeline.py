"""Main pipeline — orchestrates selector → headline → description → checker → output."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import product as itertools_product
from pathlib import Path
from typing import Dict, List

from gcf.brand_voice_agent import generate_brand_voice_guideline
from gcf.checker import check_copy
from gcf.compliance_agent import filter_risky_claims
from gcf.config import AppConfig
from gcf.generator_description import (
    generate_description_replacements,
    generate_descriptions,
)
from gcf.generator_headline import generate_headline_replacements, generate_headlines
from gcf.io_csv import (
    read_ads_csv,
    write_figma_tsv,
    write_handoff_csv,
    write_new_ads_csv,
    write_report,
)
from gcf.memory import append_entry, load_memory
from gcf.providers.base import BaseProvider
from gcf.selector import generate_strategy, select_underperforming


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


def _make_cache_store(cfg: AppConfig, mode: str):
    """Return a CacheStore if caching is enabled, else None."""
    if not cfg.cache.enabled:
        return None
    try:
        from gcf.cache import CacheStore

        return CacheStore(cfg.cache.path)
    except Exception:
        return None


def run_pipeline(
    input_path,
    output_dir,
    cfg: AppConfig,
    provider: BaseProvider,
    mode: str = "dry",
) -> Dict:
    """Execute the full pipeline. Returns summary dict.

    Call order (enforced):
    1. select_underperforming  — rule-based pandas filter
    2. generate_strategy       — LLM: root-cause analysis + creative angle
    3. generate_headlines      — LLM: headline variants (cache-aware, targeted retry)
    4. generate_descriptions   — LLM: description variants (cache-aware, targeted retry)
    5. check_copy              — LLM: compliance review, removes violating items
    6. (live) brand/compliance  — brand_voice_agent + compliance_agent filters
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Cache ─────────────────────────────────────────────────────────────────
    cache_store = _make_cache_store(cfg, mode)

    # 1. Read input
    df = read_ads_csv(input_path)

    # 2. Select underperforming (rule-based, no LLM)
    selected, reasons = select_underperforming(df, cfg.selector)

    if selected.empty:
        summary = {
            "total_ads": len(df),
            "selected": 0,
            "variants_generated": 0,
            "pass_count": 0,
            "fail_count": 0,
            "checker_violations": 0,
            "compliance_failures": 0,
            "message": "No underperforming ads found with current thresholds.",
            "provider_stats": {},
            "cache_stats": {},
        }
        write_report(_format_report(summary, []), output_dir / "report.md")
        return summary

    # 3. Generate variations for each selected ad
    new_ads_rows: List[Dict] = []
    figma_rows: List[Dict] = []
    total_pass = 0
    total_fail = 0
    total_violations = 0
    total_compliance_failures = 0
    report_details: List[Dict] = []

    for idx, (_, row) in enumerate(selected.iterrows()):
        ad = row.to_dict()
        reason_info = reasons[idx] if idx < len(reasons) else {}
        ad["_issue"] = reason_info.get("reasons", "")

        # ── Step 2: generate_strategy (LLM — selector_prompt.txt) ────────────
        strategy_result = generate_strategy(provider, ad, ad["_issue"], cfg)
        strategy = strategy_result.get(
            "strategy",
            f"Improve engagement for ad {ad.get('ad_id', '')} — issues: {ad['_issue']}",
        )
        analysis = strategy_result.get("analysis", "")

        memory_ctx = _build_memory_context(cfg, ad.get("campaign", ""))

        brand_voice_guideline = ""
        if mode == "live":
            brand_voice_guideline = generate_brand_voice_guideline(
                provider, cfg, ad.get("campaign", ""), ad.get("ad_group", "")
            )

        # ── Step 3: generate_headlines (LLM — headline_prompt.txt) ───────────
        headlines, h_fail = generate_headlines(
            provider, ad, strategy, cfg, memory_ctx, brand_voice_guideline, cache_store
        )

        # ── Step 4: generate_descriptions (LLM — description_prompt.txt) ─────
        descriptions, d_fail = generate_descriptions(
            provider, ad, strategy, cfg, memory_ctx, brand_voice_guideline, cache_store
        )

        # ── Step 5: check_copy (LLM — checker_prompt.txt) ─────────────────────
        headlines, descriptions, violations = check_copy(
            provider, headlines, descriptions, cfg
        )

        # Retry only the failing agent(s) with concise checker feedback.
        for _ in range(cfg.generation.max_retries_validation):
            if not violations:
                break

            headline_failures = []
            description_failures = []
            for v in violations:
                vtype = str(v.get("type", "")).upper()
                idx = v.get("index")
                issue = v.get("issue", "checker violation")
                if not isinstance(idx, int):
                    continue
                if vtype == "HEADLINE" and 0 <= idx < len(headlines):
                    headline_failures.append({"text": headlines[idx], "reason": issue})
                elif vtype == "DESCRIPTION" and 0 <= idx < len(descriptions):
                    description_failures.append(
                        {"text": descriptions[idx], "reason": issue}
                    )

            if headline_failures:
                bad_texts = {f["text"] for f in headline_failures}
                headlines = [h for h in headlines if h not in bad_texts]
                replacements = generate_headline_replacements(
                    provider,
                    ad,
                    strategy,
                    cfg,
                    headline_failures,
                    len(headline_failures),
                )
                headlines = headlines + [h for h in replacements if h not in headlines]

            if description_failures:
                bad_texts = {f["text"] for f in description_failures}
                descriptions = [d for d in descriptions if d not in bad_texts]
                replacements = generate_description_replacements(
                    provider,
                    ad,
                    strategy,
                    cfg,
                    description_failures,
                    len(description_failures),
                )
                descriptions = descriptions + [
                    d for d in replacements if d not in descriptions
                ]

            headlines, descriptions, violations = check_copy(
                provider, headlines, descriptions, cfg
            )

        total_violations += len(violations)

        compliance_failures: List[Dict] = []
        ad_compliance_failures = 0
        if mode == "live":
            for _ in range(cfg.generation.max_retries_validation):
                headlines, descriptions, compliance_failures = filter_risky_claims(
                    headlines, descriptions
                )
                ad_compliance_failures += len(compliance_failures)
                if not compliance_failures:
                    break

                headline_failures = [
                    {"text": f["text"], "reason": f.get("reason", "risky claim")}
                    for f in compliance_failures
                    if f.get("type") == "HEADLINE"
                ]
                description_failures = [
                    {"text": f["text"], "reason": f.get("reason", "risky claim")}
                    for f in compliance_failures
                    if f.get("type") == "DESCRIPTION"
                ]

                if headline_failures:
                    replacements = generate_headline_replacements(
                        provider,
                        ad,
                        strategy,
                        cfg,
                        headline_failures,
                        len(headline_failures),
                    )
                    headlines = headlines + [
                        h for h in replacements if h not in headlines
                    ]

                if description_failures:
                    replacements = generate_description_replacements(
                        provider,
                        ad,
                        strategy,
                        cfg,
                        description_failures,
                        len(description_failures),
                    )
                    descriptions = descriptions + [
                        d for d in replacements if d not in descriptions
                    ]

            total_compliance_failures += ad_compliance_failures

        h_count = len(headlines)
        d_count = len(descriptions)
        total_pass += h_count + d_count
        total_fail += h_fail + d_fail

        # Create variant set
        variant_set_id = (
            f"vs_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{idx:03d}"
        )

        # Cross-product (capped)
        combos = list(itertools_product(headlines, descriptions))
        max_v = cfg.generation.max_variants_per_run
        combos = combos[:max_v]

        for ci, (h, d) in enumerate(combos):
            tag = f"V{ci+1:03d}"
            new_ads_rows.append(
                {
                    "campaign": ad.get("campaign", ""),
                    "ad_group": ad.get("ad_group", ""),
                    "ad_id": ad.get("ad_id", ""),
                    "original_headline": ad.get("headline", ""),
                    "original_description": ad.get("description", ""),
                    "variant_headline": h,
                    "variant_description": d,
                    "variant_set_id": variant_set_id,
                    "tag": tag,
                }
            )
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

        report_details.append(
            {
                "ad_id": ad.get("ad_id", ""),
                "campaign": ad.get("campaign", ""),
                "issue": ad["_issue"],
                "analysis": analysis,
                "strategy": strategy,
                "headlines_generated": h_count,
                "descriptions_generated": d_count,
                "checker_violations": len(violations),
                "compliance_failures": ad_compliance_failures,
                "combos": len(combos),
                "variant_set_id": variant_set_id,
            }
        )

    # 4. Write outputs
    write_new_ads_csv(new_ads_rows, output_dir / "new_ads.csv")
    write_figma_tsv(figma_rows, output_dir / "figma_variations.tsv")
    handoff_rows = [
        {
            "variant_set_id": r.get("variant_set_id", ""),
            "TAG": r.get("tag", ""),
            "H1": r.get("variant_headline", ""),
            "DESC": r.get("variant_description", ""),
            "status": "",
            "notes": "",
        }
        for r in new_ads_rows
    ]
    write_handoff_csv(handoff_rows, output_dir / "handoff.csv")

    # 5. Collect runtime stats
    provider_stats = provider.stats() if hasattr(provider, "stats") else {}
    cache_stats = cache_store.stats() if cache_store is not None else {}

    summary = {
        "total_ads": len(df),
        "selected": len(selected),
        "variants_generated": len(new_ads_rows),
        "pass_count": total_pass,
        "fail_count": total_fail,
        "checker_violations": total_violations,
        "compliance_failures": total_compliance_failures,
        "message": "Pipeline completed successfully.",
        "provider_stats": provider_stats,
        "cache_stats": cache_stats,
    }
    write_report(_format_report(summary, report_details), output_dir / "report.md")

    return summary


def _format_report(summary: Dict, details: List[Dict]) -> str:
    pstats = summary.get("provider_stats", {})
    cstats = summary.get("cache_stats", {})

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
        f"- Checker violations removed: {summary.get('checker_violations', 0)}",
        f"- Compliance risky claims filtered: {summary.get('compliance_failures', 0)}",
        "",
    ]

    # ── LLM / API stats ───────────────────────────────────────────────────────
    if pstats:
        lines += [
            "## LLM API Stats",
            f"- API calls made: {pstats.get('call_count', 0)}",
            f"- Retries (backoff): {pstats.get('retry_count', 0)}",
            f"- Input tokens: {pstats.get('total_input_tokens', 0):,}",
            f"- Output tokens: {pstats.get('total_output_tokens', 0):,}",
            f"- Total tokens: {pstats.get('total_tokens', 0):,}",
        ]
        if pstats.get("last_error"):
            lines.append(f"- Last error: `{pstats['last_error']}`")
        lines.append("")

    # ── Cache stats ───────────────────────────────────────────────────────────
    if cstats:
        hit_pct = f"{cstats.get('hit_rate', 0) * 100:.1f}%"
        lines += [
            "## Cache Stats",
            f"- Cache hits: {cstats.get('hits', 0)}",
            f"- Cache misses: {cstats.get('misses', 0)}",
            f"- Hit rate: {hit_pct}",
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
        if d.get("analysis"):
            lines.append(f"- **Analysis:** {d['analysis']}")
        lines.append(f"- **Strategy:** {d['strategy']}")
        lines.append(f"- **Headlines generated:** {d['headlines_generated']}")
        lines.append(f"- **Descriptions generated:** {d['descriptions_generated']}")
        lines.append(f"- **Checker violations removed:** {d['checker_violations']}")
        lines.append(
            f"- **Compliance failures filtered:** {d.get('compliance_failures', 0)}"
        )
        lines.append(f"- **Combinations:** {d['combos']}")
        lines.append(f"- **Variant set ID:** `{d['variant_set_id']}`")
        lines.append("")

    return "\n".join(lines)
