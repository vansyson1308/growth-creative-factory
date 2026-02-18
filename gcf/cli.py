"""CLI entry point for Growth Creative Factory."""
from __future__ import annotations

import click
from pathlib import Path

from gcf.config import load_config
from gcf.pipeline import run_pipeline
from gcf.io_csv import read_performance_csv
from gcf.memory import ingest_performance


def _get_provider(cfg, mode: str):
    """Return the appropriate provider based on mode."""
    if mode == "dry":
        from gcf.providers.mock_provider import MockProvider
        return MockProvider()
    else:
        from gcf.providers.anthropic_provider import AnthropicProvider
        pcfg = cfg.provider
        return AnthropicProvider(
            model=pcfg.model,
            temperature=pcfg.temperature,
            max_tokens=pcfg.max_tokens,
        )


@click.group()
def cli():
    """Growth Creative Factory — AI ad variation pipeline."""
    pass


@cli.command()
@click.option("--input", "input_path", required=True, help="Path to ads CSV")
@click.option("--out", "output_dir", default="output", help="Output directory")
@click.option("--mode", type=click.Choice(["live", "dry"]), default="dry", help="live = call API; dry = mock")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def run(input_path: str, output_dir: str, mode: str, config_path: str):
    """Run the full ad variation pipeline."""
    cfg = load_config(config_path)

    if mode == "dry":
        cfg.provider.name = "mock"
        click.echo("🏃 DRY-RUN mode — using MockProvider (no API calls)")
    else:
        click.echo("🚀 LIVE mode — using Anthropic API")

    provider = _get_provider(cfg, mode)

    click.echo(f"📂 Input:  {input_path}")
    click.echo(f"📂 Output: {output_dir}")

    summary = run_pipeline(input_path, output_dir, cfg, provider, mode)

    click.echo("")
    click.echo("✅ Pipeline complete!")
    click.echo(f"   Ads analyzed:  {summary['total_ads']}")
    click.echo(f"   Underperforming: {summary['selected']}")
    click.echo(f"   Variants created: {summary['variants_generated']}")
    click.echo(f"   Files written to: {output_dir}/")


@cli.command("ingest-results")
@click.option("--input", "input_path", required=True, help="Path to performance.csv")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def ingest_results(input_path: str, config_path: str):
    """Ingest test performance results into memory."""
    cfg = load_config(config_path)

    click.echo(f"📊 Ingesting results from: {input_path}")

    perf_df = read_performance_csv(input_path)
    count = ingest_performance(cfg.memory.path, perf_df)

    click.echo(f"✅ Ingested {count} rows into {cfg.memory.path}")


if __name__ == "__main__":
    cli()
