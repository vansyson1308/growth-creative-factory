"""Main pipeline — orchestrates selector → headline → description → checker → output."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

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
from gcf.providers.base import BaseProvider, BudgetExceededError
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
    """Return a CacheStore if caching is enabled (live mode only), else None.

    Dry runs are free and deterministic, so caching them would only hide
    changes to the offline copywriter or config.
    """
    if not cfg.cache.enabled or mode != "live":
        return None
    try:
        from gcf.cache import CacheStore

        return CacheStore(cfg.cache.path)
    except Exception:
        return None


def _combine(headlines: List[str], descriptions: List[str], cap: int) -> List[tuple]:
    """Pair headlines × descriptions so early combos already use every headline.

    Round r pairs headline i with description (i + r) — the full cross-product
    is covered, but a capped prefix stays diverse instead of repeating the
    first headline with every description.
    """
    if not headlines or not descriptions:
        return []
    combos = []
    for r in range(len(descriptions)):
        for i, h in enumerate(headlines):
            combos.append((h, descriptions[(i + r) % len(descriptions)]))
    return combos[: max(0, cap)]


def _safe_id(value: object) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value)).strip("-")
    return s or "AD"


def generate_variants(
    selected,
    reasons: List[Dict],
    cfg: AppConfig,
    provider: BaseProvider,
    mode: str = "dry",
    cache_store=None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> Dict:
    """Run the agent chain for every selected ad and build variant rows.

    Returns ``{"new_ads_rows", "figma_rows", "details", "pass", "fail",
    "violations", "compliance_failures", "stopped_reason"}``. Shared by the CLI
    and the UI. If the provider's call budget runs out, processing stops cleanly
    and everything produced so far is returned (``stopped_reason`` explains).
    """
    new_ads_rows: List[Dict] = []
    figma_rows: List[Dict] = []
    total_pass = 0
    total_fail = 0
    total_violations = 0
    total_compliance_failures = 0
    report_details: List[Dict] = []
    remaining = max(0, int(cfg.generation.max_variants_per_run))
    n_ads = len(selected)
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    stopped_reason = ""
    for idx, (_, row) in enumerate(selected.iterrows()):
        ad = row.to_dict()
        if progress:
            progress(idx, n_ads, str(ad.get("ad_id", "")))
        try:
            ad_result = _process_ad(
                idx,
                ad,
                reasons,
                cfg,
                provider,
                mode,
                cache_store,
                run_stamp,
                remaining,
                n_ads,
            )
        except BudgetExceededError as exc:
            # Keep everything produced so far instead of losing the whole run.
            stopped_reason = (
                f"Stopped after {idx} of {n_ads} ads: call budget reached ({exc}). "
                "Raise budget.max_calls_per_run to process the rest."
            )
            break
        remaining = max(0, remaining - len(ad_result["rows"]))
        new_ads_rows.extend(ad_result["rows"])
        figma_rows.extend(ad_result["figma"])
        report_details.append(ad_result["detail"])
        total_pass += ad_result["pass"]
        total_fail += ad_result["fail"]
        total_violations += ad_result["violations"]
        total_compliance_failures += ad_result["compliance_failures"]

    if progress:
        progress(n_ads, n_ads, "")

    return {
        "new_ads_rows": new_ads_rows,
        "figma_rows": figma_rows,
        "details": report_details,
        "pass": total_pass,
        "fail": total_fail,
        "violations": total_violations,
        "compliance_failures": total_compliance_failures,
        "stopped_reason": stopped_reason,
    }


def _process_ad(
    idx: int,
    ad: Dict,
    reasons: List[Dict],
    cfg: AppConfig,
    provider: BaseProvider,
    mode: str,
    cache_store,
    run_stamp: str,
    remaining: int,
    n_ads: int,
) -> Dict:
    """Agent chain for one ad → rows, figma rows, report detail and counters."""
    reason_info = reasons[idx] if idx < len(reasons) else {}
    ad["_issue"] = reason_info.get("reasons", "") or ad.get("_issue", "")

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
    ad_violations = len(violations)

    # Retry only the failing agent(s) with concise checker feedback.
    # check_copy already removed flagged items; *violations* indexes refer
    # to the pre-removal lists, so we track failures by text.
    for _ in range(cfg.generation.max_retries_validation):
        if not violations:
            break

        headline_failures = [
            {
                "text": v.get("text", ""),
                "reason": v.get("issue", "checker violation"),
            }
            for v in violations
            if str(v.get("type", "")).upper() == "HEADLINE"
        ]
        description_failures = [
            {
                "text": v.get("text", ""),
                "reason": v.get("issue", "checker violation"),
            }
            for v in violations
            if str(v.get("type", "")).upper() == "DESCRIPTION"
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
            headlines = headlines + [h for h in replacements if h not in headlines]

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

        headlines, descriptions, violations = check_copy(
            provider, headlines, descriptions, cfg
        )
        ad_violations += len(violations)

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
                headlines = headlines + [h for h in replacements if h not in headlines]

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
        else:
            # Final sweep so no risky claim survives exhausted retries.
            headlines, descriptions, leftover = filter_risky_claims(
                headlines, descriptions
            )
            ad_compliance_failures += len(leftover)

    h_count = len(headlines)
    d_count = len(descriptions)

    # Create variant set (unique per ad within the run)
    ad_key = _safe_id(ad.get("ad_id", "") or f"AD{idx + 1:03d}")
    variant_set_id = f"vs_{run_stamp}_{idx:03d}"

    # Cross-product, with the per-run cap shared fairly across ads
    ads_left = n_ads - idx
    allowance = max(1, remaining // ads_left) if remaining else 0
    combos = _combine(headlines, descriptions, allowance)

    ad_rows: List[Dict] = []
    ad_figma: List[Dict] = []
    for ci, (h, d) in enumerate(combos):
        tag = f"{ad_key}-V{ci + 1:02d}"
        ad_rows.append(
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
        ad_figma.append({"H1": h, "DESC": d, "TAG": tag})

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

    detail = {
        "ad_id": ad.get("ad_id", ""),
        "campaign": ad.get("campaign", ""),
        "issue": ad["_issue"],
        "analysis": analysis,
        "strategy": strategy,
        "headlines_generated": h_count,
        "descriptions_generated": d_count,
        "checker_violations": ad_violations,
        "compliance_failures": ad_compliance_failures,
        "combos": len(combos),
        "variant_set_id": variant_set_id,
    }

    return {
        "rows": ad_rows,
        "figma": ad_figma,
        "detail": detail,
        "pass": h_count + d_count,
        "fail": h_fail + d_fail,
        "violations": ad_violations,
        "compliance_failures": ad_compliance_failures,
    }


def run_pipeline(
    input_path,
    output_dir,
    cfg: AppConfig,
    provider: BaseProvider,
    mode: str = "dry",
    render: Optional[bool] = None,
    progress: Optional[Callable[[str, int, int], None]] = None,
) -> Dict:
    """Execute the full pipeline. Returns summary dict.

    Call order (enforced):
    1. select_underperforming  — rule-based pandas filter
    2. generate_strategy       — LLM: root-cause analysis + creative angle
    3. generate_headlines      — LLM: headline variants (cache-aware, targeted retry)
    4. generate_descriptions   — LLM: description variants (cache-aware, targeted retry)
    5. check_copy              — LLM: compliance review, removes violating items
    6. (live) brand/compliance  — brand_voice_agent + compliance_agent filters
    7. (optional) render        — on-brand images for every format + gallery

    ``render`` overrides ``cfg.render.enabled`` when not ``None``.
    ``progress(stage, done, total)`` is called with stage ``"generate"`` or
    ``"render"``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    do_render = cfg.render.enabled if render is None else bool(render)

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
            "creatives_rendered": 0,
            "message": "No underperforming ads found with current thresholds.",
            "provider_stats": {},
            "cache_stats": {},
            "render": {},
        }
        write_report(_format_report(summary, []), output_dir / "report.md")
        return summary

    # 3. Generate variations for each selected ad
    gen_progress = (lambda i, n, _ad: progress("generate", i, n)) if progress else None
    result = generate_variants(
        selected, reasons, cfg, provider, mode, cache_store, gen_progress
    )
    new_ads_rows = result["new_ads_rows"]

    # 4. Write outputs
    write_new_ads_csv(new_ads_rows, output_dir / "new_ads.csv")
    write_figma_tsv(result["figma_rows"], output_dir / "figma_variations.tsv")
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

    # 5. Render creatives (images + gallery)
    render_info: Dict = {}
    if do_render and new_ads_rows:
        from gcf.studio import creatives_from_variants, render_outputs

        creatives = creatives_from_variants(new_ads_rows, cfg.render.max_creatives)
        rs = render_outputs(
            creatives,
            output_dir,
            cfg.render,
            title="Growth Creative Factory — run",
            progress=(lambda d, t: progress("render", d, t)) if progress else None,
        )
        render_info = rs.to_dict()

    # 6. Collect runtime stats
    provider_stats = provider.stats() if hasattr(provider, "stats") else {}
    cache_stats = cache_store.stats() if cache_store is not None else {}

    summary = {
        "total_ads": len(df),
        "selected": len(selected),
        "variants_generated": len(new_ads_rows),
        "pass_count": result["pass"],
        "fail_count": result["fail"],
        "checker_violations": result["violations"],
        "compliance_failures": result["compliance_failures"],
        "creatives_rendered": render_info.get("rendered", 0),
        "message": result["stopped_reason"] or "Pipeline completed successfully.",
        "stopped_reason": result["stopped_reason"],
        "provider_stats": provider_stats,
        "cache_stats": cache_stats,
        "render": render_info,
    }
    write_report(_format_report(summary, result["details"]), output_dir / "report.md")

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
        f"- Creative images rendered: {summary.get('creatives_rendered', 0)}",
        "",
    ]
    if summary.get("stopped_reason"):
        lines += [f"> ⚠️ {summary['stopped_reason']}", ""]

    rinfo = summary.get("render") or {}
    if rinfo.get("rendered"):
        lines += ["## Creatives", f"- Images: `{rinfo.get('creatives_dir', '')}`"]
        if rinfo.get("gallery"):
            lines.append(f"- Review gallery: `{rinfo['gallery']}`")
        if rinfo.get("contact_sheet"):
            lines.append(f"- Contact sheet: `{rinfo['contact_sheet']}`")
        lines.append("")

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
