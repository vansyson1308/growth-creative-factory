"""CLI entry point for Growth Creative Factory."""

from __future__ import annotations

import click

from gcf import __version__
from gcf.config import load_config
from gcf.connectors.google_ads import GoogleAdsConnectorError, pull_google_ads_rows
from gcf.connectors.google_sheets import GoogleSheetsConfigError, push_tabular_file
from gcf.connectors.meta_ads import MetaAdsConnectorError, pull_meta_ads_rows
from gcf.io_csv import InputSchemaError, read_performance_csv
from gcf.memory import ingest_performance
from gcf.pipeline import run_pipeline


def _get_provider(cfg, mode: str):
    """Return the appropriate provider based on mode."""
    from gcf.providers import make_provider

    try:
        return make_provider(cfg, mode)
    except EnvironmentError as exc:
        raise click.ClickException(
            f"{exc}\nTip: use --mode dry to run offline with the built-in copywriter."
        )


def _load_cfg(config_path: str):
    try:
        return load_config(config_path)
    except (ValueError, TypeError) as exc:
        raise click.ClickException(f"Invalid config {config_path}: {exc}")


def _apply_render_overrides(
    rcfg, formats, templates, brand, max_creatives, image_format
):
    from gcf.creative import TEMPLATES, parse_formats

    if formats:
        try:
            rcfg.formats = parse_formats(formats)
        except KeyError as exc:
            raise click.BadParameter(str(exc), param_hint="--formats")
    if templates:
        keys = [t.strip().lower() for t in templates.split(",") if t.strip()]
        bad = [k for k in keys if k not in TEMPLATES]
        if bad:
            raise click.BadParameter(
                f"Unknown template(s) {', '.join(bad)}. Available: {', '.join(TEMPLATES)}",
                param_hint="--templates",
            )
        rcfg.templates = keys
    if brand:
        rcfg.brand = brand
    if max_creatives is not None:
        rcfg.max_creatives = max_creatives
    if image_format:
        rcfg.image_format = image_format
    try:
        from gcf.creative import load_brand

        load_brand(rcfg.brand)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--brand")
    return rcfg


class _Bar:
    """Tiny progress printer that works in any terminal and in CI logs."""

    def __init__(self, label: str):
        self.label = label
        self._last = -1

    def __call__(self, done: int, total: int) -> None:
        if total <= 0:
            return
        pct = int(done * 100 / total)
        if pct // 10 != self._last // 10 or done == total:
            self._last = pct
            click.echo(f"   {self.label}: {done}/{total} ({pct}%)")


_render_options = [
    click.option(
        "--formats",
        default=None,
        help="Comma list: square,portrait,story,landscape,wide or 'all'",
    ),
    click.option(
        "--templates",
        default=None,
        help="Comma list of templates (default: rotate all)",
    ),
    click.option(
        "--brand", default=None, help="Brand preset name or path to brand YAML"
    ),
    click.option("--image-format", type=click.Choice(["png", "jpg"]), default=None),
]


def render_options(f):
    for opt in reversed(_render_options):
        f = opt(f)
    return f


@click.group()
@click.version_option(version=__version__, prog_name="gcf")
def cli():
    """Growth Creative Factory — AI ad & social creative factory.

    \b
    Quick start (no API key needed):
      gcf run --input examples/ads_sample.csv --mode dry
      gcf create --product "Cloudstep sneakers" --offer "30% off" --n 6
      gcf showcase --out docs/showcase
    """
    pass


@cli.command()
@click.option("--input", "input_path", required=True, help="Path to ads CSV")
@click.option("--out", "output_dir", default="output", help="Output directory")
@click.option(
    "--mode",
    type=click.Choice(["live", "dry"]),
    default="dry",
    help="live = call Claude; dry = offline copywriter (free)",
)
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
@click.option(
    "--render/--no-render",
    default=None,
    help="Render creative images (default: config)",
)
@click.option(
    "--max-creatives", type=int, default=None, help="Variants to render (0 = all)"
)
@render_options
def run(
    input_path: str,
    output_dir: str,
    mode: str,
    config_path: str,
    render,
    max_creatives,
    formats,
    templates,
    brand,
    image_format,
):
    """Run the full pipeline: select → write → check → render."""
    cfg = _load_cfg(config_path)
    _apply_render_overrides(
        cfg.render, formats, templates, brand, max_creatives, image_format
    )
    do_render = cfg.render.enabled if render is None else render

    if mode == "dry":
        cfg.provider.name = "mock"
        click.echo("🏃 DRY-RUN mode — offline copywriter (no API calls, no cost)")
    else:
        click.echo(f"🚀 LIVE mode — Claude ({cfg.provider.model})")
        click.echo(f"   Budget: max_calls_per_run={cfg.budget.max_calls_per_run}")
        click.echo(
            f"   Cache:  {'enabled' if cfg.cache.enabled else 'disabled'} → {cfg.cache.path}"
        )

    provider = _get_provider(cfg, mode)

    click.echo(f"📂 Input:  {input_path}")
    click.echo(f"📂 Output: {output_dir}")

    bars = {"generate": _Bar("Writing copy (ads)"), "render": _Bar("Rendering images")}

    def progress(stage, done, total):
        bars[stage](done, total)

    try:
        summary = run_pipeline(
            input_path,
            output_dir,
            cfg,
            provider,
            mode,
            render=do_render,
            progress=progress,
        )
    except InputSchemaError as exc:
        raise click.ClickException(str(exc))
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"Input file not found: {exc.filename or input_path}"
        )

    click.echo("")
    click.echo("✅ Pipeline complete!")
    click.echo(f"   Ads analyzed:  {summary['total_ads']}")
    click.echo(f"   Underperforming: {summary['selected']}")
    click.echo(f"   Variants created: {summary['variants_generated']}")
    click.echo(f"   Validation passed: {summary['pass_count']}")
    click.echo(f"   Validation failed: {summary['fail_count']}")
    if summary.get("creatives_rendered"):
        rinfo = summary.get("render", {})
        click.echo(f"   Images rendered: {summary['creatives_rendered']}")
        if rinfo.get("gallery"):
            click.echo(f"   🖼  Review gallery: {rinfo['gallery']}")
    click.echo(f"   Files written to: {output_dir}/")

    # Print API / cache stats for live mode
    pstats = summary.get("provider_stats", {})
    cstats = summary.get("cache_stats", {})
    if pstats and mode == "live":
        click.echo("")
        click.echo("📊 LLM Stats:")
        click.echo(
            f"   API calls: {pstats.get('call_count', 0)}  |  Retries: {pstats.get('retry_count', 0)}"
        )
        click.echo(
            f"   Tokens:    {pstats.get('total_tokens', 0):,}  "
            f"(in: {pstats.get('total_input_tokens', 0):,}  "
            f"out: {pstats.get('total_output_tokens', 0):,})"
        )
        if pstats.get("last_error"):
            click.echo(f"   Last error: {pstats['last_error']}", err=True)
    if cstats:
        hit_pct = f"{cstats.get('hit_rate', 0) * 100:.1f}%"
        click.echo(
            f"   Cache:     hits={cstats.get('hits', 0)}  "
            f"misses={cstats.get('misses', 0)}  "
            f"hit_rate={hit_pct}"
        )


@cli.command("render")
@click.option(
    "--input",
    "input_path",
    required=True,
    help="CSV/TSV with headline (+ description, cta, …)",
)
@click.option("--out", "output_dir", default="output/rendered", show_default=True)
@click.option("--limit", type=int, default=0, help="Max rows to render (0 = all)")
@click.option("--title", default="Creative batch", help="Gallery title")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
@render_options
def render_cmd(
    input_path,
    output_dir,
    limit,
    title,
    config_path,
    formats,
    templates,
    brand,
    image_format,
):
    """Render images from any copy sheet (Figma TSV, new_ads.csv, your own CSV)."""
    from gcf.studio import creatives_from_file, render_outputs

    cfg = _load_cfg(config_path)
    rcfg = _apply_render_overrides(
        cfg.render, formats, templates, brand, None, image_format
    )
    try:
        creatives = creatives_from_file(input_path, limit=limit)
    except FileNotFoundError:
        raise click.ClickException(f"Input file not found: {input_path}")
    except ValueError as exc:
        raise click.ClickException(str(exc))
    click.echo(
        f"🎨 Rendering {len(creatives)} creatives × {len(rcfg.formats)} formats …"
    )
    rs = render_outputs(
        creatives, output_dir, rcfg, title=title, progress=_Bar("Rendering")
    )
    click.echo(f"✅ {rs.count} images → {rs.creatives_dir}")
    if rs.gallery:
        click.echo(f"   🖼  Review gallery: {rs.gallery}")


@cli.command("create")
@click.option("--product", required=True, help="Product or service name")
@click.option("--audience", default="", help="Who it is for")
@click.option("--offer", default="", help='Offer, e.g. "30% off launch week"')
@click.option("--benefit", "benefits", multiple=True, help="Key benefit (repeatable)")
@click.option("--pain", default="", help="Problem the product solves")
@click.option("--tone", default="", help="Voice, e.g. playful, premium")
@click.option("--lang", type=click.Choice(["auto", "en", "vi"]), default="auto")
@click.option(
    "--n", "n_posts", type=click.IntRange(1, 200), default=6, show_default=True
)
@click.option(
    "--mode", type=click.Choice(["live", "dry"]), default="dry", show_default=True
)
@click.option("--out", "output_dir", default="output/studio", show_default=True)
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
@render_options
def create_cmd(
    product,
    audience,
    offer,
    benefits,
    pain,
    tone,
    lang,
    n_posts,
    mode,
    output_dir,
    config_path,
    formats,
    templates,
    brand,
    image_format,
):
    """Brief → N social posts → on-brand images for every format."""
    from gcf.copywriter import Brief
    from gcf.studio import create_from_brief

    cfg = _load_cfg(config_path)
    rcfg = _apply_render_overrides(
        cfg.render, formats, templates, brand, None, image_format
    )
    provider = _get_provider(cfg, mode)
    brief = Brief(
        product=product,
        audience=audience,
        offer=offer,
        benefits=list(benefits),
        pain=pain,
        tone=tone,
        language=None if lang == "auto" else lang,
    )
    click.echo(
        f"✍️  Writing {n_posts} posts for “{product}” ({'Claude' if mode == 'live' else 'offline'}) …"
    )
    result = create_from_brief(
        brief,
        provider,
        output_dir,
        n=n_posts,
        cfg=cfg,
        rcfg=rcfg,
        progress=_Bar("Rendering"),
    )
    rs = result["render"]
    click.echo("")
    for i, post in enumerate(result["posts"], 1):
        click.echo(f"   {i:>2}. [{post.angle}] {post.headline}")
    click.echo("")
    click.echo(f"✅ {len(result['posts'])} posts → {result['posts_csv']}")
    click.echo(f"   {rs.count} images → {rs.creatives_dir}")
    if rs.gallery:
        click.echo(f"   🖼  Review gallery: {rs.gallery}")


@cli.command("showcase")
@click.option("--out", "output_dir", default="docs/showcase", show_default=True)
@click.option("--formats", default="square,portrait,story,landscape", show_default=True)
@click.option(
    "--readme-assets",
    is_flag=True,
    help="Also build the composite images used in the README",
)
def showcase_cmd(output_dir, formats, readme_assets):
    """Render the multi-brand showcase (the images in the README)."""
    from gcf.creative import parse_formats
    from gcf.creative.gallery import contact_sheet
    from gcf.studio import build_showcase, build_showcase_assets

    if readme_assets:
        click.echo(f"✨ Building README showcase assets → {output_dir}")
        files = build_showcase_assets(output_dir, progress=_Bar("Showcase"))
        for f in files:
            click.echo(f"   • {f}")
        return
    fmts = parse_formats(formats)
    click.echo(f"✨ Rendering showcase → {output_dir}")
    written = build_showcase(output_dir, fmts, progress=_Bar("Showcase"))
    sq = [p for k, p in written.items() if k.endswith("/square")]
    if sq:
        contact_sheet(
            sq,
            f"{output_dir}/showcase-grid.png",
            width=2400,
            row_height=560,
            title="Growth Creative Factory",
            subtitle="6 fictional brands · 6 templates · rendered offline in seconds",
        )
    click.echo(f"✅ {len(written)} images written.")


@cli.command("templates")
def templates_cmd():
    """List creative templates."""
    from gcf.creative import TEMPLATES

    for t in TEMPLATES.values():
        click.echo(f"  {t.key:<10} {t.name:<16} {t.description}")


@cli.command("formats")
def formats_cmd():
    """List output formats (sizes & placements)."""
    from gcf.creative import FORMATS

    for f in FORMATS.values():
        click.echo(
            f"  {f.key:<10} {f.width}×{f.height:<5} {f.label:<12} {f.placements}"
        )


@cli.command("brands")
def brands_cmd():
    """List built-in brand kit presets."""
    from gcf.creative import PRESETS

    for key, b in PRESETS.items():
        click.echo(
            f"  {key:<8} {b.name:<16} {b.primary} → {b.secondary}  accent {b.accent}"
        )
    click.echo(
        "\n  Custom kit: copy examples/brand_kit.yaml and pass --brand path/to/it.yaml"
    )


@cli.command("ingest-results")
@click.option("--input", "input_path", required=True, help="Path to performance.csv")
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
def ingest_results(input_path: str, config_path: str):
    """Ingest test performance results into memory."""
    cfg = _load_cfg(config_path)

    click.echo(f"📊 Ingesting results from: {input_path}")
    click.echo(f"📂 Memory file: {cfg.memory.path}")

    perf_df = read_performance_csv(input_path)
    updated, appended = ingest_performance(cfg.memory.path, perf_df)

    click.echo("")
    click.echo("✅ Ingest complete!")
    click.echo(f"   Existing entries updated : {updated}")
    click.echo(f"   New entries appended      : {appended}")
    click.echo(f"   Total rows processed      : {updated + appended}")


@cli.group("sheets")
def sheets_group():
    """Google Sheets helper commands."""
    pass


@sheets_group.command("push")
@click.option("--spreadsheet_id", required=True, help="Target Google Sheet ID")
@click.option("--worksheet", required=True, help="Worksheet/tab name")
@click.option("--input", "input_path", required=True, help="Input CSV or TSV path")
def sheets_push(spreadsheet_id: str, worksheet: str, input_path: str):
    """Push local CSV/TSV output to Google Sheets (optional connector)."""
    try:
        n = push_tabular_file(spreadsheet_id, worksheet, input_path)
    except GoogleSheetsConfigError as exc:
        raise click.ClickException(str(exc))
    except Exception as exc:
        raise click.ClickException(f"Failed to push to Google Sheets: {exc}")

    click.echo(
        f"✅ Pushed {n} rows to worksheet '{worksheet}' in spreadsheet {spreadsheet_id}."
    )


@cli.group("google-ads")
def google_ads_group():
    """Google Ads connector commands."""
    pass


@google_ads_group.command("pull")
@click.option("--customer_id", required=True, help="Google Ads customer ID")
@click.option(
    "--date_range",
    default="LAST_30_DAYS",
    show_default=True,
    help="Google Ads date range",
)
@click.option("--level", default="ad", show_default=True, type=click.Choice(["ad"]))
@click.option(
    "--out",
    "out_path",
    default="input/ads.csv",
    show_default=True,
    help="Output CSV path",
)
@click.option(
    "--config", "config_path", default=None, help="Optional google-ads.yaml path"
)
def google_ads_pull(
    customer_id: str,
    date_range: str,
    level: str,
    out_path: str,
    config_path: str | None,
):
    """Pull Google Ads performance into unified AdsRow CSV."""
    try:
        rows = pull_google_ads_rows(
            customer_id=customer_id,
            date_range=date_range,
            level=level,
            out_path=out_path,
            config_path=config_path,
        )
    except GoogleAdsConnectorError as exc:
        raise click.ClickException(str(exc))
    except Exception as exc:
        raise click.ClickException(f"Google Ads pull failed: {exc}")

    click.echo(f"✅ Pulled {len(rows)} rows from Google Ads into {out_path}")


@cli.group("meta-ads")
def meta_ads_group():
    """Meta Ads connector commands."""
    pass


@meta_ads_group.command("pull")
@click.option(
    "--date_preset", default="last_30d", show_default=True, help="Meta date preset"
)
@click.option(
    "--out",
    "out_path",
    default="input/ads.csv",
    show_default=True,
    help="Output CSV path",
)
def meta_ads_pull(date_preset: str, out_path: str):
    """Pull Meta Ads insights into unified AdsRow CSV."""
    try:
        rows = pull_meta_ads_rows(date_preset=date_preset, out_path=out_path)
    except MetaAdsConnectorError as exc:
        raise click.ClickException(str(exc))
    except Exception as exc:
        raise click.ClickException(f"Meta Ads pull failed: {exc}")

    click.echo(f"✅ Pulled {len(rows)} rows from Meta Ads into {out_path}")


if __name__ == "__main__":
    cli()
