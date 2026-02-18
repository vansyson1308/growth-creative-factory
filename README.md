# Growth Creative Factory

[![CI](https://github.com/your-org/growth-creative-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/growth-creative-factory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

Growth Creative Factory (GCF) is a local-first pipeline that helps marketing teams turn ad performance exports into validated headline/description variants, with optional AI generation and optional ad-platform connectors, then hands off clean TSV output to Figma for fast creative production.

## What is this?

GCF ingests ad performance CSVs, filters underperforming rows, generates compliant copy variants, validates character/policy constraints, and exports both bulk-upload CSV and Figma-ready TSV. It supports dry-run mode with no API calls and optional live mode via Anthropic.

## Quickstart (5-minute dry-run)

> Goal: run end-to-end locally without external credentials.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m gcf --version
python -m gcf run --input examples/ads_sample.csv --out output --mode dry
pytest -v
```

Windows helpers:

- `scripts\run_cli.bat`
- `scripts\run_app.bat`

## Demo workflow (5 steps)

1. **Pull data**: Export manually from ad platforms, or use connectors (`google-ads pull`, `meta-ads pull`).
2. **Generate**: Run `python -m gcf run --mode dry|live ...`.
3. **Paste TSV**: Open `output/figma_variations.tsv`, copy all rows.
4. **Figma plugin**: Load `figma_plugin/manifest.json`, paste TSV into plugin UI, generate frames.
   - If `figma_plugin/dist/code.js` is missing, build it with: `npx --yes tsc figma_plugin/code.ts --outDir figma_plugin/dist --target ES2017 --lib ES2017,DOM --noEmitOnError false`
5. **Export PNG**: Use plugin export action for creative handoff.

## Bring Your Own Credentials (optional)

You only need credentials for services you choose to use:

- **Anthropic** (`live` mode only): `ANTHROPIC_API_KEY`
- **Google Ads** connector: `GCF_GOOGLE_ADS_*` vars (see docs)
- **Meta Ads** connector: `META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`
- **Google Sheets** connector: `GCF_GOOGLE_CREDS_JSON` / `GOOGLE_APPLICATION_CREDENTIALS`

Use `.env.example` as your template and never commit secrets.

## Troubleshooting

- **529 overloaded / transient provider errors**: retry after backoff, reduce request load, or use dry mode.
- **Missing columns**: ensure required schema fields are present in your CSV header.
- **Font load failed in Figma**: ensure text layer fonts are installed/available in Figma and layer names match expected keys (`H1`, `DESC`).
- **Auth errors for connectors / token invalid**: verify scopes, account permissions, credential paths, and token freshness.

## Project structure

```text
gcf/            # Core package (pipeline, CLI, providers, validators)
gcf/connectors/ # Optional data connectors (Google Ads, Meta Ads, Sheets)
gcf/prompts/    # Prompt templates for generation/checking
figma_plugin/   # Figma plugin source (manifest, UI, code)
docs/           # Connector, privacy, and project docs
examples/       # Synthetic sample inputs
```

## Contributing / Before pushing

Run the formatting + lint + test script before opening a PR:

```bash
# macOS/Linux
bash scripts/format.sh

# Windows
scripts\format.bat
```

This keeps local results aligned with CI (`black --check .`, `ruff check .`, `pytest -q`).

## Documentation

- [Documentation Index](docs/INDEX.md)
- [Connect Google Ads](docs/CONNECT_GOOGLE_ADS.md)
- [Connect Meta Ads](docs/CONNECT_META_ADS.md)
- [Connect Google Sheets](docs/CONNECT_GOOGLE_SHEETS.md)
- [Privacy](docs/PRIVACY.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)

## Version

Current package version is exposed in `gcf.__version__` and via CLI:

```bash
python -m gcf --version
```

## Roadmap

- Harden connector ergonomics and diagnostics.
- Expand prompt/provider test coverage.
- Publish reproducible release artifacts and tags.
- Add optional containerized local dev workflow.

## Credits

Built by contributors focused on practical, local-first AI tooling for marketing creative operations.
