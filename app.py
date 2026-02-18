"""Streamlit UI for Growth Creative Factory — designed for non-dev marketing teams."""
import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from gcf.config import load_config, AppConfig
from gcf.pipeline import run_pipeline
from gcf.providers.mock_provider import MockProvider


def _get_provider(cfg: AppConfig, mode: str):
    if mode == "dry":
        return MockProvider()
    else:
        from gcf.providers.anthropic_provider import AnthropicProvider
        pcfg = cfg.provider
        return AnthropicProvider(
            model=pcfg.model,
            temperature=pcfg.temperature,
            max_tokens=pcfg.max_tokens,
        )


def main():
    st.set_page_config(page_title="Growth Creative Factory", page_icon="🚀", layout="wide")

    st.title("🚀 Growth Creative Factory")
    st.caption("Upload ads CSV → Auto-detect underperformers → Generate ad variations → Export for Figma")

    # --- Sidebar: Config ---
    st.sidebar.header("⚙️ Settings")

    cfg = load_config("config.yaml")

    st.sidebar.subheader("Underperforming Thresholds")
    cfg.selector.min_impressions = st.sidebar.number_input(
        "Min Impressions", value=cfg.selector.min_impressions, min_value=0, step=100
    )
    cfg.selector.max_ctr = st.sidebar.number_input(
        "Max CTR (below = underperforming)", value=cfg.selector.max_ctr, min_value=0.0, step=0.005, format="%.4f"
    )
    cfg.selector.max_cpa = st.sidebar.number_input(
        "Max CPA (above = underperforming)", value=cfg.selector.max_cpa, min_value=0.0, step=5.0
    )
    cfg.selector.min_roas = st.sidebar.number_input(
        "Min ROAS (below = underperforming)", value=cfg.selector.min_roas, min_value=0.0, step=0.5
    )

    st.sidebar.subheader("Mode")
    mode = st.sidebar.radio("Run mode", ["dry", "live"], index=0, help="dry = mock data (no API cost); live = call Anthropic API")

    # --- Main area ---
    uploaded = st.file_uploader("📄 Upload your ads CSV", type=["csv"])

    if uploaded is not None:
        df_preview = pd.read_csv(uploaded)
        st.subheader("Preview: Input Data")
        st.dataframe(df_preview.head(10), use_container_width=True)

        # Reset file pointer for pipeline
        uploaded.seek(0)

        if st.button("🎯 Generate Variations", type="primary"):
            with st.spinner("Running pipeline..."):
                # Save uploaded file to temp
                with tempfile.TemporaryDirectory() as tmpdir:
                    input_path = Path(tmpdir) / "ads.csv"
                    input_path.write_bytes(uploaded.read())

                    output_dir = Path(tmpdir) / "output"
                    output_dir.mkdir()

                    provider = _get_provider(cfg, mode)
                    summary = run_pipeline(input_path, output_dir, cfg, provider, mode)

                st.success(f"✅ Done! {summary['variants_generated']} variants generated from {summary['selected']} underperforming ads.")

                # Stats
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Ads", summary["total_ads"])
                col2.metric("Underperforming", summary["selected"])
                col3.metric("Variants", summary["variants_generated"])
                col4.metric("Passed Validation", summary["pass_count"])

                # Preview output
                new_ads_path = output_dir / "new_ads.csv"
                figma_path = output_dir / "figma_variations.tsv"
                report_path = output_dir / "report.md"

                if new_ads_path.exists():
                    st.subheader("Preview: Generated Ads (first 10)")
                    out_df = pd.read_csv(new_ads_path)
                    st.dataframe(out_df.head(10), use_container_width=True)

                    st.download_button(
                        "⬇️ Download new_ads.csv",
                        data=new_ads_path.read_bytes(),
                        file_name="new_ads.csv",
                        mime="text/csv",
                    )

                if figma_path.exists():
                    st.download_button(
                        "⬇️ Download figma_variations.tsv",
                        data=figma_path.read_bytes(),
                        file_name="figma_variations.tsv",
                        mime="text/tab-separated-values",
                    )

                if report_path.exists():
                    report_text = report_path.read_text(encoding="utf-8")
                    st.download_button(
                        "⬇️ Download report.md",
                        data=report_text.encode("utf-8"),
                        file_name="report.md",
                        mime="text/markdown",
                    )
                    with st.expander("📋 Report preview"):
                        st.markdown(report_text)
    else:
        st.info("👆 Upload a CSV with columns: campaign, ad_group, ad_id, headline, description, impressions, clicks, cost, conversions, revenue")


if __name__ == "__main__":
    main()
