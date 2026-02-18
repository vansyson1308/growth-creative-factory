"""Streamlit app — Growth Creative Factory.

Two top-level tabs:
  🧙 Wizard      — 4-step flow: Upload → Select → Generate → Export
  📊 Learning Board — top angles, blacklist phrases, recent experiments
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone
from itertools import product as itertools_product
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from gcf.config import AppConfig, load_config
from gcf.connectors.google_ads import GoogleAdsConnectorError, pull_google_ads_rows
from gcf.connectors.google_sheets import GoogleSheetsConfigError, push_tabular_file
from gcf.connectors.meta_ads import MetaAdsConnectorError, pull_meta_ads_rows
from gcf.generator_description import generate_descriptions
from gcf.generator_headline import generate_headlines
from gcf.io_csv import InputSchemaError, read_ads_csv
from gcf.memory import (
    append_entry,
    get_recent_experiments,
    get_top_angles,
    load_memory,
)
from gcf.pipeline import _format_report
from gcf.providers.mock_provider import MockProvider
from gcf.selector import select_underperforming

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

STEP_LABELS: List[str] = [
    "1 · Upload & Config",
    "2 · Select Ads",
    "3 · Generate",
    "4 · Export",
]
MAX_PREVIEW_ROWS = 20

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _load_api_key() -> str:
    """Read ANTHROPIC_API_KEY from environment or .env file."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    return ""


def _resolve_provider(cfg: AppConfig, mode: str):
    """Return (provider, actual_mode).

    If *live* mode is requested but no API key is found, emits a Streamlit
    warning and silently falls back to dry-run so the app never crashes.
    """
    if mode == "dry":
        return MockProvider(), "dry"

    api_key = _load_api_key()
    if not api_key:
        st.warning(
            "⚠️ **Live mode selected but ANTHROPIC_API_KEY is not set.**  \n"
            "Add it to your `.env` file and restart the app.  \n"
            "**Falling back to dry-run (mock data) for this run.**",
            icon="⚠️",
        )
        return MockProvider(), "dry"

    try:
        from gcf.providers.anthropic_provider import AnthropicProvider

        pcfg = cfg.provider
        return (
            AnthropicProvider(
                model=pcfg.model,
                temperature=pcfg.temperature,
                max_tokens=pcfg.max_tokens,
            ),
            "live",
        )
    except Exception as exc:
        st.warning(
            f"⚠️ **Could not initialise Anthropic provider** (`{exc}`).  \n"
            "**Falling back to dry-run.**",
            icon="⚠️",
        )
        return MockProvider(), "dry"


def _build_new_ads_csv_bytes(rows: List[Dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False, encoding="utf-8").encode("utf-8")


def _build_handoff_csv_bytes(new_ads_rows: List[Dict]) -> bytes:
    rows = [
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
    df = pd.DataFrame(rows)
    for col in ("variant_set_id", "TAG", "H1", "DESC", "status", "notes"):
        if col not in df.columns:
            df[col] = ""
    return (
        df[["variant_set_id", "TAG", "H1", "DESC", "status", "notes"]]
        .to_csv(index=False, encoding="utf-8")
        .encode("utf-8")
    )


def _build_figma_tsv_bytes(rows: List[Dict]) -> bytes:
    """UTF-8 no-BOM TSV with columns H1, DESC, TAG."""
    df = pd.DataFrame(rows)
    for col in ("H1", "DESC", "TAG"):
        if col not in df.columns:
            df[col] = ""
    df = df[["H1", "DESC", "TAG"]]
    buf = io.StringIO()
    df.to_csv(buf, sep="\t", index=False)  # StringIO never writes a BOM
    return buf.getvalue().encode("utf-8")  # explicit UTF-8, no BOM marker


# ─────────────────────────────────────────────────────────────────────────────
# Step indicator
# ─────────────────────────────────────────────────────────────────────────────


def _render_stepper(current: int) -> None:
    cols = st.columns(len(STEP_LABELS))
    for i, (col, label) in enumerate(zip(cols, STEP_LABELS)):
        step_num = i + 1
        if step_num < current:
            col.success(f"✓ {label}")
        elif step_num == current:
            col.info(f"▶ **{label}**")
        else:
            col.caption(f"○ {label}")
    st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# Guard: redirect to step 1 if required session state is missing
# ─────────────────────────────────────────────────────────────────────────────


def _require_state(*keys: str) -> bool:
    """Return True if all keys are in session_state; otherwise redirect to step 1."""
    if all(k in st.session_state for k in keys):
        return True
    st.warning("Session data missing — returning to Step 1.")
    st.session_state.wizard_step = 1
    st.rerun()
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Upload & Config
# ─────────────────────────────────────────────────────────────────────────────


def step1() -> None:
    st.header("Step 1 — Upload your ads CSV and choose a run mode")
    st.markdown(
        "Export ad performance from **Google Ads** or **Meta Ads Manager** and upload it here.  \n"
        "Required columns: `campaign` · `ad_group` · `ad_id` · `headline` · `description` "
        "· `impressions` · `clicks` · `cost` · `conversions` · `revenue`"
    )

    # ── File upload ──────────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "📄 **Ads CSV file**",
        type=["csv"],
        help="Export from Google Ads or Meta Ads Manager.",
    )

    # ── Mode + config ────────────────────────────────────────────────────────
    col_mode, col_cfg = st.columns([1, 2], gap="large")

    with col_mode:
        st.markdown("#### Run mode")
        mode = st.radio(
            "run_mode",
            ["dry", "live"],
            index=0,
            label_visibility="collapsed",
            help=(
                "**dry** — instant mock data, zero API cost. Perfect for testing.  \n\n"
                "**live** — calls Anthropic API to write real copy "
                "(requires `ANTHROPIC_API_KEY` in `.env`)."
            ),
        )
        if mode == "live":
            if _load_api_key():
                st.success("🔑 API key found.", icon="✅")
            else:
                st.warning(
                    "No API key found in `.env`. Will fall back to dry-run.",
                    icon="⚠️",
                )

    with col_cfg:
        with st.expander("⚙️ Threshold settings (click to expand)", expanded=False):
            st.markdown(
                "Ads with **≥ min impressions** AND failing at least one metric are flagged."
            )
            cfg = load_config("config.yaml")
            cfg.selector.min_impressions = st.number_input(
                "Min impressions — ignore low-traffic ads",
                value=cfg.selector.min_impressions,
                min_value=0,
                step=100,
            )
            cfg.selector.max_ctr = st.number_input(
                "Max CTR — below this = underperforming",
                value=cfg.selector.max_ctr,
                min_value=0.0,
                step=0.005,
                format="%.4f",
            )
            cfg.selector.max_cpa = st.number_input(
                "Max CPA — above this = underperforming",
                value=cfg.selector.max_cpa,
                min_value=0.0,
                step=5.0,
            )
            cfg.selector.min_roas = st.number_input(
                "Min ROAS — below this = underperforming",
                value=cfg.selector.min_roas,
                min_value=0.0,
                step=0.5,
            )
            # cfg is defined inside this expander block — expose it to the outer scope
            st.session_state["_cfg_draft"] = cfg

    # Retrieve cfg whether or not the expander was opened
    cfg = st.session_state.get("_cfg_draft", load_config("config.yaml"))

    # ── Parse + preview ──────────────────────────────────────────────────────
    if uploaded is not None:
        raw_bytes = uploaded.read()
        try:
            df = read_ads_csv(io.BytesIO(raw_bytes))
        except InputSchemaError as exc:
            st.error(f"❌ **CSV schema error:** {exc}")
            st.stop()
        except Exception as exc:
            st.error(f"❌ **Could not read CSV:** {exc}")
            st.stop()

        st.success(f"✅ **{len(df)} ads loaded** from `{uploaded.name}`.")

        preview_cols = [
            c
            for c in [
                "campaign",
                "ad_group",
                "ad_id",
                "headline",
                "description",
                "impressions",
                "clicks",
                "cost",
            ]
            if c in df.columns
        ]
        with st.expander("👀 Preview — first 5 rows"):
            st.dataframe(df[preview_cols].head(5), use_container_width=True)

        # ── Next button ──────────────────────────────────────────────────────
        if st.button("Next: Select underperformers →", type="primary"):
            # Clear all downstream state from any previous run
            for key in [
                "selected_ids",
                "new_ads_rows",
                "figma_rows",
                "generation_done",
                "summary",
                "report_text",
                "generation_approved",
                "_cfg_draft",
            ]:
                st.session_state.pop(key, None)

            st.session_state.df = df
            st.session_state.cfg = cfg
            st.session_state.mode = mode
            st.session_state.wizard_step = 2
            st.rerun()
    else:
        st.info(
            "👆 Upload a CSV to begin.  \n"
            "No file yet? Use `examples/ads_sample.csv` from the repo to try the wizard."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Select underperformers
# ─────────────────────────────────────────────────────────────────────────────


def step2() -> None:
    if not _require_state("df", "cfg"):
        return

    st.header("Step 2 — Review underperforming ads")
    st.markdown(
        "The table shows ads flagged by **rule-based analysis** "
        "(CTR · CPA · ROAS thresholds set in Step 1).  \n"
        "**Remove any ad from the selection box** below if you don't want variations for it."
    )

    df: pd.DataFrame = st.session_state.df
    cfg: AppConfig = st.session_state.cfg
    selected_df, reasons = select_underperforming(df, cfg.selector)

    # ── No underperformers ───────────────────────────────────────────────────
    if selected_df.empty:
        st.warning(
            "⚠️ **No underperforming ads found** with the current thresholds.  \n"
            "Go back to Step 1 and lower *Min impressions* or relax the CTR/CPA/ROAS limits.",
            icon="⚠️",
        )
        if st.button("← Back to Step 1"):
            st.session_state.wizard_step = 1
            st.rerun()
        return

    # ── Display table ────────────────────────────────────────────────────────
    reason_map = {r["ad_id"]: r["reasons"] for r in reasons}

    display_cols = [
        c
        for c in [
            "ad_id",
            "campaign",
            "ad_group",
            "headline",
            "impressions",
            "ctr",
            "cpa",
            "roas",
        ]
        if c in selected_df.columns
    ]
    display_df = selected_df[display_cols].copy()
    display_df["why flagged"] = display_df["ad_id"].map(reason_map).fillna("")

    # Format float columns
    if "ctr" in display_df.columns:
        display_df["ctr"] = display_df["ctr"].apply(
            lambda x: f"{x:.4f}" if pd.notna(x) else "—"
        )
    for col in ("cpa", "roas"):
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"{x:.2f}" if pd.notna(x) else "—"
            )

    st.dataframe(display_df, use_container_width=True)
    st.caption(
        f"**{len(selected_df)} ads auto-selected** out of {len(df)} total ads in the CSV."
    )

    # ── Manual override ──────────────────────────────────────────────────────
    st.markdown("#### Confirm which ads to include")
    all_ids = selected_df["ad_id"].tolist()

    id_to_headline: Dict[str, str] = dict(
        zip(
            selected_df["ad_id"],
            (
                selected_df["headline"]
                if "headline" in selected_df.columns
                else selected_df["ad_id"]
            ),
        )
    )

    chosen_ids: List[str] = st.multiselect(
        "Ads to generate variations for (deselect to skip):",
        options=all_ids,
        default=all_ids,
        format_func=lambda i: f"{i}  —  {id_to_headline.get(i, i)}",
    )

    if not chosen_ids:
        st.warning("⚠️ Select at least one ad to continue.", icon="⚠️")

    # ── Navigation ───────────────────────────────────────────────────────────
    col_back, spacer, col_next = st.columns([1, 4, 2])
    with col_back:
        if st.button("← Back"):
            st.session_state.wizard_step = 1
            st.rerun()
    with col_next:
        label = (
            f"Next: Generate for {len(chosen_ids)} ad(s) →"
            if chosen_ids
            else "Select ads first"
        )
        if st.button(label, type="primary", disabled=not chosen_ids):
            st.session_state.selected_ids = chosen_ids
            st.session_state.pop("generation_done", None)
            st.session_state.pop("generation_approved", None)
            st.session_state.wizard_step = 3
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Generate
# ─────────────────────────────────────────────────────────────────────────────


def _run_generation(
    df: pd.DataFrame,
    chosen_ids: List[str],
    cfg: AppConfig,
    mode: str,
) -> tuple:
    """Run the generation loop; returns (new_ads_rows, figma_rows, summary, report_text)."""
    provider, actual_mode = _resolve_provider(cfg, mode)
    subset = df[df["ad_id"].isin(chosen_ids)].copy()
    n = len(subset)

    new_ads_rows: List[Dict] = []
    figma_rows: List[Dict] = []
    total_pass = total_fail = 0
    report_details: List[Dict] = []

    progress = st.progress(0, text="⏳ Starting…")
    status = st.empty()

    for idx, (_, row) in enumerate(subset.iterrows()):
        ad = row.to_dict()
        ad["_issue"] = "selected via Wizard"
        strategy = f"Improve engagement for ad {ad.get('ad_id', '')} — boost CTR/ROAS"

        progress.progress(idx / n, text=f"⏳ Ad {idx + 1}/{n} — {ad.get('ad_id', '')}")
        status.caption(
            f"Generating headlines + descriptions for **{ad.get('ad_id', '')}**…"
        )

        headlines, h_fail = generate_headlines(provider, ad, strategy, cfg, "")
        descriptions, d_fail = generate_descriptions(provider, ad, strategy, cfg, "")

        total_pass += len(headlines) + len(descriptions)
        total_fail += h_fail + d_fail

        variant_set_id = (
            f"vs_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{idx:03d}"
        )
        combos = list(itertools_product(headlines, descriptions))[
            : cfg.generation.max_variants_per_run
        ]

        for ci, (h, d) in enumerate(combos):
            tag = f"V{ci + 1:03d}"
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

        # ── Log to memory ────────────────────────────────────────────────────
        try:
            append_entry(
                memory_path=cfg.memory.path,
                campaign=ad.get("campaign", ""),
                ad_group=ad.get("ad_group", ""),
                ad_id=ad.get("ad_id", ""),
                hypothesis=strategy,
                variant_set_id=variant_set_id,
                generated={"headlines": headlines, "descriptions": descriptions},
                notes=f"mode={actual_mode}",
            )
        except Exception:
            pass  # memory logging is non-critical; never block the wizard

        report_details.append(
            {
                "ad_id": ad.get("ad_id", ""),
                "campaign": ad.get("campaign", ""),
                "issue": ad["_issue"],
                "strategy": strategy,
                "headlines_generated": len(headlines),
                "descriptions_generated": len(descriptions),
                "combos": len(combos),
                "variant_set_id": variant_set_id,
            }
        )

    progress.progress(1.0, text="✅ Generation complete!")
    status.empty()

    summary: Dict = {
        "total_ads": len(df),
        "selected": n,
        "variants_generated": len(new_ads_rows),
        "pass_count": total_pass,
        "fail_count": total_fail,
        "message": f"Wizard run · mode={actual_mode}",
    }
    return new_ads_rows, figma_rows, summary, _format_report(summary, report_details)


def step3() -> None:
    if not _require_state("df", "cfg", "mode", "selected_ids"):
        return

    df: pd.DataFrame = st.session_state.df
    cfg: AppConfig = st.session_state.cfg
    mode: str = st.session_state.mode
    chosen_ids: List[str] = st.session_state.selected_ids

    st.header("Step 3 — Generate ad variations")
    st.markdown(
        f"Creating headline + description variations for **{len(chosen_ids)} ad(s)** "
        f"in **{mode.upper()}** mode.  \n"
        "Review the stats and preview below, then click **Approve Export** "
        "to unlock the downloads."
    )

    # ── Run generation exactly once; cache in session_state ──────────────────
    if not st.session_state.get("generation_done", False):
        rows, figma_rows, summary, report_text = _run_generation(
            df, chosen_ids, cfg, mode
        )
        st.session_state.new_ads_rows = rows
        st.session_state.figma_rows = figma_rows
        st.session_state.summary = summary
        st.session_state.report_text = report_text
        st.session_state.generation_done = True
        st.session_state.generation_approved = False

    # ── Stats ────────────────────────────────────────────────────────────────
    summary: Dict = st.session_state.summary
    figma_rows: List[Dict] = st.session_state.figma_rows

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ads processed", summary["selected"])
    c2.metric("Variants generated", summary["variants_generated"])
    c3.metric("Copy passed", summary["pass_count"])
    c4.metric(
        "Copy failed",
        summary["fail_count"],
        delta=f"-{summary['fail_count']}" if summary["fail_count"] else None,
        delta_color="inverse",
    )

    # ── TSV preview ──────────────────────────────────────────────────────────
    if figma_rows:
        n_preview = min(MAX_PREVIEW_ROWS, len(figma_rows))
        st.subheader(f"Figma TSV preview — first {n_preview} of {len(figma_rows)} rows")
        st.dataframe(pd.DataFrame(figma_rows[:n_preview]), use_container_width=True)
        if len(figma_rows) > MAX_PREVIEW_ROWS:
            st.caption(
                f"… {len(figma_rows) - MAX_PREVIEW_ROWS} more rows will be in the exported file."
            )
    else:
        st.warning(
            "⚠️ No variants were produced — check policy/char-limit settings in `config.yaml`.",
            icon="⚠️",
        )

    st.divider()

    # ── Navigation ───────────────────────────────────────────────────────────
    col_back, spacer, col_approve = st.columns([1, 4, 2])

    with col_back:
        if st.button("← Back to Select"):
            # Clear so that returning to Step 3 re-generates with the new selection
            st.session_state.pop("generation_done", None)
            st.session_state.pop("generation_approved", None)
            st.session_state.wizard_step = 2
            st.rerun()

    with col_approve:
        already_approved = st.session_state.get("generation_approved", False)
        if already_approved:
            st.success("Export approved ✓")
            if st.button("Go to Export →", type="primary"):
                st.session_state.wizard_step = 4
                st.rerun()
        else:
            if st.button(
                "✅ Approve Export →",
                type="primary",
                disabled=not figma_rows,
                help="No variants to export." if not figma_rows else "",
            ):
                st.session_state.generation_approved = True
                st.session_state.wizard_step = 4
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Export
# ─────────────────────────────────────────────────────────────────────────────


def step4() -> None:
    if not _require_state("new_ads_rows", "figma_rows", "report_text", "summary"):
        return

    # Must have approved in Step 3
    if not st.session_state.get("generation_approved", False):
        st.error(
            "⛔ **Export not approved.**  \n"
            "Go back to Step 3 and click **Approve Export** to unlock downloads."
        )
        if st.button("← Back to Step 3"):
            st.session_state.wizard_step = 3
            st.rerun()
        return

    st.header("Step 4 — Download your files")
    st.markdown(
        "All three files are ready. Download them and follow the Figma SOP to produce creatives."
    )

    new_ads_rows: List[Dict] = st.session_state.new_ads_rows
    figma_rows: List[Dict] = st.session_state.figma_rows
    report_text: str = st.session_state.report_text
    summary: Dict = st.session_state.summary

    # ── Build in-memory bytes (generated once per render) ────────────────────
    new_ads_bytes = _build_new_ads_csv_bytes(new_ads_rows)
    figma_tsv_bytes = _build_figma_tsv_bytes(figma_rows)
    handoff_bytes = _build_handoff_csv_bytes(new_ads_rows)
    report_bytes = report_text.encode("utf-8")

    # ── Summary bar ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total ads in CSV", summary["total_ads"])
    c2.metric("Ads processed", summary["selected"])
    c3.metric("Variant combinations", summary["variants_generated"])
    c4.metric("Figma rows", len(figma_rows))

    st.divider()

    # ── Download cards ───────────────────────────────────────────────────────
    col_csv, col_tsv, col_handoff, col_md = st.columns(4)

    with col_csv:
        st.markdown("##### 📊 new_ads.csv")
        st.caption(
            "All H1 × DESC combinations — bulk-upload ready for Google Ads / Meta Ads Manager."
        )
        st.download_button(
            "⬇️ Download new_ads.csv",
            data=new_ads_bytes,
            file_name="new_ads.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )

    with col_tsv:
        st.markdown("##### 🎨 figma_variations.tsv")
        st.caption(
            f"UTF-8 · no BOM · columns `H1 / DESC / TAG`  ({len(figma_rows)} rows).  \n"
            "Paste directly into the Figma plugin."
        )
        st.download_button(
            "⬇️ Download figma_variations.tsv",
            data=figma_tsv_bytes,
            file_name="figma_variations.tsv",
            mime="text/tab-separated-values",
            use_container_width=True,
            type="primary",
        )

    with col_handoff:
        st.markdown("##### 🤝 handoff.csv")
        st.caption(
            "Marketing review sheet with blank `status` / `notes` columns for team collaboration."
        )
        st.download_button(
            "⬇️ Download handoff sheet",
            data=handoff_bytes,
            file_name="handoff.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )

    with col_md:
        st.markdown("##### 📋 report.md")
        st.caption(
            "Run summary with stats and variant-set IDs.  \n"
            "Paste into Notion or open in any Markdown viewer."
        )
        st.download_button(
            "⬇️ Download report.md",
            data=report_bytes,
            file_name="report.md",
            mime="text/markdown",
            use_container_width=True,
            type="primary",
        )

    # ── Inline report ────────────────────────────────────────────────────────
    with st.expander("📋 View report inline"):
        st.markdown(report_text)

    # ── Figma SOP cheat-sheet ────────────────────────────────────────────────
    with st.expander("📐 How to use figma_variations.tsv in Figma"):
        st.markdown(
            """
**Prerequisites:** Figma Desktop + Growth Creative Factory plugin.

1. **Import plugin (once)** — Figma menu → Plugins → Development → Import plugin from manifest
   → select `figma_plugin/manifest.json`.

2. **Set up template** — Create a frame named exactly `AD_TEMPLATE` with text layers
   named `H1` and `DESC` (optionally `CTA`, `H2`).

3. **Open the plugin** — Plugins → Growth Creative Factory.

4. **Review handoff sheet** — Open `handoff.csv`, collaborate in `status`/`notes`, finalize approved lines.

5. **Paste TSV** — Open `figma_variations.tsv` in any text editor → Select All → Copy
   → paste into the TSV text area in the plugin.

6. **Generate** — Click **Generate Variations** → frames appear in a grid,
   each with H1 and DESC filled in.

7. **Export PNGs** — Click **Export PNGs** in the plugin to download all frames at 2×.
            """
        )

    st.divider()

    # ── Back / Restart ───────────────────────────────────────────────────────
    col_back, spacer, col_restart = st.columns([1, 3, 2])
    with col_back:
        if st.button("← Back to Generate"):
            st.session_state.wizard_step = 3
            st.rerun()
    with col_restart:
        if st.button("🔄 Start over (new CSV)", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Learning Board
# ─────────────────────────────────────────────────────────────────────────────


def learning_board() -> None:
    """Render the Learning Board — insights from memory.jsonl."""
    st.header("📊 Learning Board")
    st.caption(
        "Insights drawn from `memory/memory.jsonl`.  "
        "Run `python -m gcf ingest-results --input results/performance.csv` "
        "to load real performance data."
    )

    # Load config + memory
    cfg = load_config("config.yaml")
    entries = load_memory(cfg.memory.path)

    n_entries = len(entries)
    n_with_results = sum(1 for e in entries if e.get("results"))

    # Top-level stats
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total experiments logged", n_entries)
    mc2.metric("With performance results", n_with_results)
    mc3.metric(
        "Memory file",
        Path(cfg.memory.path).name,
        help=cfg.memory.path,
    )

    st.divider()

    tab_angles, tab_blacklist, tab_recent = st.tabs(
        ["🏆 Top Angles", "🚫 Blacklist Phrases", "🧪 Recent Experiments"]
    )

    # ── Tab 1 : Top Angles ───────────────────────────────────────────────────
    with tab_angles:
        st.subheader("Top creative angles by performance")
        st.markdown(
            "Angles are tags you supply in `results/performance.csv` (the `angle` column).  \n"
            "Only experiments that have been ingested via `ingest-results` appear here."
        )

        if n_with_results == 0:
            st.info(
                "📭 No performance data yet.  \n\n"
                "Run `python -m gcf ingest-results --input results/performance.csv` "
                "to populate this section.",
                icon="ℹ️",
            )
        else:
            col_metric, col_n = st.columns([2, 1])
            with col_metric:
                sel_metric = st.selectbox(
                    "Rank by",
                    ["roas", "ctr", "cpa"],
                    index=0,
                    key="lb_metric",
                )
            with col_n:
                top_n = st.number_input(
                    "Show top N angles",
                    value=10,
                    min_value=1,
                    max_value=50,
                    step=1,
                    key="lb_top_n",
                )

            ascending = sel_metric == "cpa"  # lower CPA = better
            df_angles = get_top_angles(
                entries,
                metric=sel_metric,
                n=int(top_n),
                ascending=ascending,
            )

            if df_angles.empty:
                st.warning(
                    f"No entries have `{sel_metric}` in their results.  \n"
                    "Check that your performance CSV includes that column.",
                    icon="⚠️",
                )
            else:
                # Pretty-format numeric columns
                mean_col = f"mean_{sel_metric}"
                best_col = f"best_{sel_metric}"
                display = df_angles.copy()
                for col in (mean_col, best_col):
                    if col in display.columns:
                        display[col] = display[col].apply(lambda x: f"{x:.3f}")

                st.dataframe(display, use_container_width=True)
                st.caption(
                    f"{'↓ lower is better' if ascending else '↑ higher is better'} · "
                    f"sorted by mean {sel_metric}"
                )

                # Bar chart
                chart_df = df_angles.set_index("angle")[[mean_col]]
                st.bar_chart(chart_df, use_container_width=True)

    # ── Tab 2 : Blacklist Phrases ────────────────────────────────────────────
    with tab_blacklist:
        st.subheader("Blocked phrases & patterns")
        st.markdown(
            "These patterns are applied by the **policy checker** during generation.  \n"
            "Any headline or description matching a pattern is **rejected** and regenerated.  \n\n"
            "To add or remove patterns, edit `config.yaml` → `policy.blocked_patterns`."
        )

        patterns = cfg.policy.blocked_patterns
        if not patterns:
            st.info("No blocked patterns configured.", icon="ℹ️")
        else:
            rows = []
            for p in patterns:
                # Strip common regex wrappers for a human-readable preview
                readable = p
                for prefix in ("(?i)", r"(?i)"):
                    readable = readable.replace(prefix, "")
                readable = readable.strip().strip(r"\b").strip()
                rows.append({"pattern (regex)": p, "readable": readable})

            df_bl = pd.DataFrame(rows)
            st.dataframe(df_bl, use_container_width=True)
            st.caption(
                f"{len(patterns)} blocked pattern(s) active. "
                "Patterns use Python `re` syntax (case-insensitive where shown)."
            )

            with st.expander("📖 How policy checking works"):
                st.markdown(
                    """
The pipeline checks every generated headline and description against
each blocked pattern using `re.search(pattern, text)`.

- If **any pattern matches**, the copy piece is **rejected** (counted as a fail).
- Rejections are retried up to `generation.retry_limit` times (default: 3).
- After retries are exhausted, the piece is dropped from the output.

The fail count shown in Step 3 includes both char-limit failures and policy violations.
                    """
                )

    # ── Tab 3 : Recent Experiments ───────────────────────────────────────────
    with tab_recent:
        st.subheader("Recent experiments")
        st.markdown(
            "The last 20 entries logged to `memory/memory.jsonl`, newest first.  \n"
            "Each row represents one ad processed in one pipeline run."
        )

        if not entries:
            st.info(
                "📭 No experiments logged yet.  \n\n"
                "Run the wizard (Steps 1–4) or use "
                "`python -m gcf run --input examples/ads_sample.csv --out output` "
                "to populate this log.",
                icon="ℹ️",
            )
        else:
            df_recent = get_recent_experiments(entries, n=20)

            # Colour-code the results column
            st.dataframe(df_recent, use_container_width=True)
            st.caption(
                f"Showing last {min(20, len(entries))} of {len(entries)} entries.  "
                "✅ = performance results ingested · — = not yet measured."
            )

            # Download full memory as JSONL
            try:
                raw = Path(cfg.memory.path).read_bytes()
                st.download_button(
                    "⬇️ Download full memory.jsonl",
                    data=raw,
                    file_name="memory.jsonl",
                    mime="application/jsonlines",
                )
            except FileNotFoundError:
                pass


def handoff_tab() -> None:
    st.header("🤝 Handoff (Optional Google Sheets)")
    st.caption(
        "Push generated TSV/CSV outputs to Google Sheets, or continue with local files only."
    )

    spreadsheet_id = st.text_input("Spreadsheet ID", key="handoff_spreadsheet_id")
    ws_tsv = st.text_input(
        "Worksheet for TSV", value="Variations", key="handoff_ws_tsv"
    )
    ws_csv = st.text_input("Worksheet for CSV", value="Ads", key="handoff_ws_csv")

    tsv_path = Path("output/figma_variations.tsv")
    csv_path = Path("output/new_ads.csv")

    creds_present = bool(
        os.environ.get("GCF_GOOGLE_CREDS_JSON")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )
    if not creds_present:
        st.info(
            "Google credentials not configured. Set `GCF_GOOGLE_CREDS_JSON` (or "
            "`GOOGLE_APPLICATION_CREDENTIALS`) and see `docs/CONNECT_GOOGLE_SHEETS.md`."
        )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Push TSV to Google Sheets", use_container_width=True):
            if not spreadsheet_id.strip():
                st.error("Please enter Spreadsheet ID")
            elif not tsv_path.exists():
                st.error("TSV file not found: output/figma_variations.tsv")
            else:
                try:
                    n = push_tabular_file(
                        spreadsheet_id.strip(),
                        ws_tsv.strip() or "Variations",
                        str(tsv_path),
                    )
                    st.success(f"Pushed {n} rows to {ws_tsv}.")
                except GoogleSheetsConfigError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Push failed: {exc}")

    with c2:
        if st.button("Push CSV to Google Sheets", use_container_width=True):
            if not spreadsheet_id.strip():
                st.error("Please enter Spreadsheet ID")
            elif not csv_path.exists():
                st.error("CSV file not found: output/new_ads.csv")
            else:
                try:
                    n = push_tabular_file(
                        spreadsheet_id.strip(), ws_csv.strip() or "Ads", str(csv_path)
                    )
                    st.success(f"Pushed {n} rows to {ws_csv}.")
                except GoogleSheetsConfigError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Push failed: {exc}")

    st.divider()
    st.markdown("### Local fallback")
    st.caption(
        "No Google Sheets? Continue downloading files from Step 4 in the Wizard."
    )


def connectors_tab() -> None:
    st.header("🔌 Connectors")

    tab_ga, tab_meta = st.tabs(["Google Ads", "Meta Ads"])

    with tab_ga:
        st.subheader("Google Ads (optional)")
        st.caption(
            "Pull performance data into `input/ads.csv` using your own Google Ads credentials."
        )

        customer_id = st.text_input(
            "Customer ID", key="ga_customer_id", placeholder="1234567890"
        )
        date_range = st.selectbox(
            "Date range",
            ["LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "THIS_MONTH", "LAST_MONTH"],
            index=2,
            key="ga_date_range",
        )

        if st.button("Pull from Google Ads", use_container_width=True):
            if not customer_id.strip():
                st.error("Customer ID is required.")
            else:
                try:
                    out = Path("input/ads.csv")
                    rows = pull_google_ads_rows(
                        customer_id=customer_id.strip(),
                        date_range=date_range,
                        level="ad",
                        out_path=str(out),
                    )
                    st.success(f"Pulled {len(rows)} rows into {out}.")
                    if out.exists():
                        preview = pd.read_csv(out).head(20)
                        st.dataframe(preview, use_container_width=True)
                except GoogleAdsConnectorError as exc:
                    st.error(str(exc))
                    st.info("See docs/CONNECT_GOOGLE_ADS.md for setup instructions.")
                except Exception as exc:
                    st.error(f"Google Ads pull failed: {exc}")

        st.info(
            "Missing config? Create `google-ads.yaml` or set env vars. "
            "See docs/CONNECT_GOOGLE_ADS.md"
        )

    with tab_meta:
        st.subheader("Meta Ads (optional)")
        st.caption(
            "Pull Meta Ads insights into `input/ads.csv` using your own token/account ID."
        )

        date_preset = st.selectbox(
            "Date preset",
            ["last_7d", "last_14d", "last_30d", "this_month", "last_month"],
            index=2,
            key="meta_date_preset",
        )

        if st.button("Pull from Meta Ads", use_container_width=True):
            try:
                out = Path("input/ads.csv")
                rows = pull_meta_ads_rows(date_preset=date_preset, out_path=str(out))
                st.success(f"Pulled {len(rows)} rows into {out}.")
                if out.exists():
                    preview = pd.read_csv(out).head(20)
                    st.dataframe(preview, use_container_width=True)
            except MetaAdsConnectorError as exc:
                st.error(str(exc))
                st.info("See docs/CONNECT_META_ADS.md for setup instructions.")
            except Exception as exc:
                st.error(f"Meta Ads pull failed: {exc}")

        if not os.environ.get("META_ACCESS_TOKEN"):
            st.info(
                "Missing META_ACCESS_TOKEN / META_AD_ACCOUNT_ID. "
                "See docs/CONNECT_META_ADS.md"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    st.set_page_config(
        page_title="Growth Creative Factory",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 1

    st.title("🚀 Growth Creative Factory")
    st.caption("AI-powered ad variation pipeline · 4-step wizard for marketing teams")

    tab_wizard, tab_board, tab_handoff, tab_connectors = st.tabs(
        ["🧙 Wizard", "📊 Learning Board", "🤝 Handoff", "🔌 Connectors"]
    )

    with tab_wizard:
        _render_stepper(st.session_state.wizard_step)

        step = st.session_state.wizard_step
        if step == 1:
            step1()
        elif step == 2:
            step2()
        elif step == 3:
            step3()
        elif step == 4:
            step4()
        else:
            st.error(f"Unknown step {step}. Resetting to Step 1.")
            st.session_state.wizard_step = 1
            st.rerun()

    with tab_board:
        learning_board()

    with tab_handoff:
        handoff_tab()

    with tab_connectors:
        connectors_tab()


if __name__ == "__main__":
    main()
