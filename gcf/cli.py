"""CLI entry point for Growth Creative Factory."""
from __future__ import annotations

import click
from pathlib import Path

from gcf.config import load_config
from gcf.pipeline import run_pipeline
from gcf.io_csv import read_performance_csv, InputSchemaError
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
            retry_cfg=cfg.retry_api,
            budget_cfg=cfg.budget,
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
        click.echo(f"   Budget: max_calls_per_run={cfg.budget.max_calls_per_run}")
        click.echo(f"   Cache:  {'enabled' if cfg.cache.enabled else 'disabled'} → {cfg.cache.path}")

    provider = _get_provider(cfg, mode)

    click.echo(f"📂 Input:  {input_path}")
    click.echo(f"📂 Output: {output_dir}")

    try:
        summary = run_pipeline(input_path, output_dir, cfg, provider, mode)
    except InputSchemaError as exc:
        raise click.ClickException(str(exc))

    click.echo("")
    click.echo("✅ Pipeline complete!")
    click.echo(f"   Ads analyzed:  {summary['total_ads']}")
    click.echo(f"   Underperforming: {summary['selected']}")
    click.echo(f"   Variants created: {summary['variants_generated']}")
    click.echo(f"   Validation passed: {summary['pass_count']}")
    click.echo(f"   Validation failed: {summary['fail_count']}")
    click.echo(f"   Files written to: {output_dir}/")

    # Print API / cache stats for live mode
    pstats = summary.get("provider_stats", {})
    cstats = summary.get("cache_stats", {})
    if pstats:
        click.echo("")
        click.echo("📊 LLM Stats:")
        click.echo(f"   API calls: {pstats.get('call_count', 0)}  |  Retries: {pstats.get('retry_count', 0)}")
        click.echo(f"   Tokens:    {pstats.get('total_tokens', 0):,}  "
                   f"(in: {pstats.get('total_input_tokens', 0):,}  "
                   f"out: {pstats.get('total_output_tokens', 0):,})")
        if pstats.get("last_error"):
            click.echo(f"   Last error: {pstats['last_error']}", err=True)
    if cstats:
        hit_pct = f"{cstats.get('hit_rate', 0) * 100:.1f}%"
        click.echo(f"   Cache:     hits={cstats.get('hits', 0)}  "
                   f"misses={cstats.get('misses', 0)}  "
                   f"hit_rate={hit_pct}")


@cli.command("ingest-results")
@click.option("--input", "input_path", required=True, help="Path to performance.csv")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def ingest_results(input_path: str, config_path: str):
    """Ingest test performance results into memory."""
    cfg = load_config(config_path)

    click.echo(f"📊 Ingesting results from: {input_path}")
    click.echo(f"📂 Memory file: {cfg.memory.path}")

    perf_df = read_performance_csv(input_path)
    updated, appended = ingest_performance(cfg.memory.path, perf_df)

    click.echo("")
    click.echo("✅ Ingest complete!")
    click.echo(f"   Existing entries updated : {updated}")
    click.echo(f"   New entries appended      : {appended}")
    click.echo(f"   Total rows processed      : {updated + appended}")


if __name__ == "__main__":
    cli()
