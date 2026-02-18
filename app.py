"""Streamlit 4-step Wizard — Growth Creative Factory.

Designed for non-dev marketing teams:
  Step 1  Upload ads CSV + choose dry/live mode + (optionally) tweak thresholds
  Step 2  Review auto-selected underperformers; un-tick any you want to skip
  Step 3  Watch variations being generated; preview first 20 Figma rows; Approve
  Step 4  Download new_ads.csv / figma_variations.tsv / report.md
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

from gcf.config import load_config, AppConfig
from gcf.io_csv import read_ads_csv, InputSchemaError
from gcf.selector import select_underperforming
from gcf.generator_headline import generate_headlines
from gcf.generator_description import generate_descriptions
from gcf.pipeline import _format_report
from gcf.providers.mock_provider import MockProvider

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
            c for c in
            ["campaign", "ad_group", "ad_id", "headline", "description",
             "impressions", "clicks", "cost"]
            if c in df.columns
        ]
        with st.expander("👀 Preview — first 5 rows"):
            st.dataframe(df[preview_cols].head(5), use_container_width=True)

        # ── Next button ──────────────────────────────────────────────────────
        if st.button("Next: Select underperformers →", type="primary"):
            # Clear all downstream state from any previous run
            for key in [
                "selected_ids", "new_ads_rows", "figma_rows",
                "generation_done", "summary", "report_text", "generation_approved",
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
        c for c in
        ["ad_id", "campaign", "ad_group", "headline", "impressions", "ctr", "cpa", "roas"]
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
        zip(selected_df["ad_id"],
            selected_df["headline"] if "headline" in selected_df.columns else selected_df["ad_id"])
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
        label = f"Next: Generate for {len(chosen_ids)} ad(s) →" if chosen_ids else "Select ads first"
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
        status.caption(f"Generating headlines + descriptions for **{ad.get('ad_id', '')}**…")

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
            new_ads_rows.append({
                "campaign":             ad.get("campaign", ""),
                "ad_group":             ad.get("ad_group", ""),
                "ad_id":                ad.get("ad_id", ""),
                "original_headline":    ad.get("headline", ""),
                "original_description": ad.get("description", ""),
                "variant_headline":     h,
                "variant_description":  d,
                "variant_set_id":       variant_set_id,
                "tag":                  tag,
            })
            figma_rows.append({"H1": h, "DESC": d, "TAG": tag})

        report_details.append({
            "ad_id":                  ad.get("ad_id", ""),
            "campaign":               ad.get("campaign", ""),
            "issue":                  ad["_issue"],
            "strategy":               strategy,
            "headlines_generated":    len(headlines),
            "descriptions_generated": len(descriptions),
            "combos":                 len(combos),
            "variant_set_id":         variant_set_id,
        })

    progress.progress(1.0, text="✅ Generation complete!")
    status.empty()

    summary: Dict = {
        "total_ads":          len(df),
        "selected":           n,
        "variants_generated": len(new_ads_rows),
        "pass_count":         total_pass,
        "fail_count":         total_fail,
        "message":            f"Wizard run · mode={actual_mode}",
    }
    return new_ads_rows, figma_rows, summary, _format_report(summary, report_details)


def step3() -> None:
    if not _require_state("df", "cfg", "mode", "selected_ids"):
        return

    df: pd.DataFrame       = st.session_state.df
    cfg: AppConfig         = st.session_state.cfg
    mode: str              = st.session_state.mode
    chosen_ids: List[str]  = st.session_state.selected_ids

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
        st.session_state.new_ads_rows        = rows
        st.session_state.figma_rows          = figma_rows
        st.session_state.summary             = summary
        st.session_state.report_text         = report_text
        st.session_state.generation_done     = True
        st.session_state.generation_approved = False

    # ── Stats ────────────────────────────────────────────────────────────────
    summary: Dict        = st.session_state.summary
    figma_rows: List[Dict] = st.session_state.figma_rows

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ads processed",       summary["selected"])
    c2.metric("Variants generated",  summary["variants_generated"])
    c3.metric("Copy passed",         summary["pass_count"])
    c4.metric("Copy failed",         summary["fail_count"],
              delta=f"-{summary['fail_count']}" if summary["fail_count"] else None,
              delta_color="inverse")

    # ── TSV preview ──────────────────────────────────────────────────────────
    if figma_rows:
        n_preview = min(MAX_PREVIEW_ROWS, len(figma_rows))
        st.subheader(
            f"Figma TSV preview — first {n_preview} of {len(figma_rows)} rows"
        )
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
            st.session_state.pop("generation_done",     None)
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
    figma_rows:   List[Dict] = st.session_state.figma_rows
    report_text:  str        = st.session_state.report_text
    summary:      Dict       = st.session_state.summary

    # ── Build in-memory bytes (generated once per render) ────────────────────
    new_ads_bytes    = _build_new_ads_csv_bytes(new_ads_rows)
    figma_tsv_bytes  = _build_figma_tsv_bytes(figma_rows)
    report_bytes     = report_text.encode("utf-8")

    # ── Summary bar ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total ads in CSV",       summary["total_ads"])
    c2.metric("Ads processed",          summary["selected"])
    c3.metric("Variant combinations",   summary["variants_generated"])
    c4.metric("Figma rows",             len(figma_rows))

    st.divider()

    # ── Download cards ───────────────────────────────────────────────────────
    col_csv, col_tsv, col_md = st.columns(3)

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

4. **Paste TSV** — Open `figma_variations.tsv` in any text editor → Select All → Copy
   → paste into the TSV text area in the plugin.

5. **Generate** — Click **Generate Variations** → frames appear in a grid,
   each with H1 and DESC filled in.

6. **Export PNGs** — Click **Export PNGs** in the plugin to download all frames at 2×.
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


if __name__ == "__main__":
    main()
