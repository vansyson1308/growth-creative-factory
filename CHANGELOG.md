# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `gcf demo` rebuilds the README proof set in `docs/demo` from `examples/`:
  - before→after board (underperforming ads, their diagnosis, and the new creatives)
  - 75-image run mosaic with measured timings
  - brief→posts sheets in EN and VI
  - brand-kit swap, including a custom YAML kit with a logo
  - every placement from one creative
  - `demo.json` with versions, timings and the generated copy
- `scripts/record_demo_media.py` records the app walkthrough GIF and the review-gallery screenshot with a headless browser.
- `examples/demo_ads.csv` and `examples/demo_brand/` (fictional advertisers and a custom brand kit).
- CI smoke job runs `gcf demo` and uploads the result.

### Changed
- The offline copywriter no longer invents facts. Review counts, star ratings, delivery and returns promises, and "while stock lasts" scarcity were removed from every template.
- Offline copy is grammatically safe with plural product names. English product names are never shortened below two words; Vietnamese names are kept whole, with service clauses dropped ("Rau hữu cơ giao tận nhà" → "Rau hữu cơ").
- The dry-mode strategist ranks the ad's actual CTR/CPA/ROAS gaps and cites the numbers, instead of giving every ad the same diagnosis.
- `run_pipeline` returns per-ad `details` in its summary.
- Story split layouts use Meta's ~13% bottom safe zone, so the copy panel is no longer half empty.

## [0.2.0] - 2026-09-24

### Added
- **Creative engine** (`gcf.creative`): renders copy into on-brand images — 6 templates
  (bold, editorial, split, glass, promo, photo), 5 formats (square, portrait, story,
  landscape, wide) with platform safe zones, brand kits (6 presets + YAML), bundled OFL
  fonts with full Vietnamese coverage, auto-fit balanced typography, product photos or
  generative art, parallel batch rendering, HTML review gallery and contact sheet.
- **Offline copywriter** (`gcf.copywriter`): context-aware EN/VI ad copy and social posts
  for dry mode — on-topic, within limits, policy-safe and angle-diverse.
- **Creative Studio**: brief → posts → images (`gcf create`, `gcf.posts`, Streamlit tab),
  copy sheet → images (`gcf render`), showcase builder (`gcf showcase`).
- Pipeline render step (`render:` config section, `--render/--no-render`, `--formats`,
  `--templates`, `--brand`, `--max-creatives`) and render step in the Streamlit wizard.
- `gcf templates`, `gcf formats`, `gcf brands`; `pip install` packaging with a `gcf`
  console script and `ui` / `connectors` / `dev` extras.
- CI matrix for Python 3.10–3.13 and an end-to-end smoke job that uploads rendered images.
- English README with showcase, Vietnamese README, creative-engine reference.

### Changed
- Claude provider targets current models: default `claude-opus-5`, `effort: low`,
  server-side refusal fallbacks, sampling parameters omitted unless configured, thinking
  blocks and refusals handled safely.
- The Streamlit wizard now runs the same agent chain as the CLI (strategy, checker,
  compliance) instead of a reduced copy of it.
- `max_variants_per_run` is now enforced per run and shared fairly across ads; combos are
  ordered so a capped set still uses every headline.
- Config sections reject unknown keys with a clear error.
- Response cache is used in live mode only.

### Fixed
- Variant tags were reused across ads (`V001` for every ad); tags are now `<ad_id>-Vnn`.
- Checker retries looked up violations by index in an already-filtered list and could drop
  the wrong copy; retries now use the flagged text, and invalid indexes are ignored.
- Policy patterns never matched `#1` after a space, nor accented `cam kết` / `tuyệt đối`.
- Live-mode compliance retries could leave risky claims when retries ran out.

## [0.1.0] - 2026-02-18

### Added
- Core pipeline for selecting underperforming ads and generating headline/description variations.
- Dry-run mode via mock provider for local validation without API credentials.
- Optional connectors for Google Ads, Meta Ads, and Google Sheets handoff.
- Streamlit 4-step wizard and Figma plugin integration for creative export workflows.
- OSS governance package (`LICENSE`, `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT`) and CI checks.
