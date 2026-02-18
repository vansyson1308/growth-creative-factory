# Release Candidate A–Z Verification (v0.1.0)

Date: 2026-02-18
Scope: Repository clone-and-run quality, offline-friendly smoke checks, and docs drift verification.

## Part 1 — Preflight Audit

### 1) OSS files present

- PASS: `LICENSE`
- PASS: `README.md`
- PASS: `CONTRIBUTING.md`
- PASS: `SECURITY.md`
- PASS: `CODE_OF_CONDUCT.md`
- PASS: `docs/INDEX.md`
- PASS: `CHANGELOG.md`
- PASS: `.github/workflows/ci.yml`

### 2) Secret hygiene (`.gitignore`)

- PASS: Blocks `.env`, `*.env`, `.env.*` (except `.env.example`)
- PASS: Blocks credential directories (`credentials/`, `secrets/`)
- PASS: Blocks credential JSON patterns (`*credentials*.json`, `*service-account*.json`, `google-ads*.json`, `oauth*.json`)
- PASS: Blocks token/config files (`.streamlit/secrets.toml`)
- PASS: Blocks runtime data folders likely to hold sensitive data (`output/`, `memory/`, `input/`, `cache/`, `.cache/`)

### 3) README quickstart drift

- PASS: Quickstart commands align with existing files (`examples/ads_sample.csv`, `python -m gcf`, `pytest`).
- PASS: Windows helper scripts referenced in README are present (`scripts/run_cli.bat`, `scripts/run_app.bat`).

## Part 2 — Local Run Matrix

### A) CLI dry-run

Command executed:

```bash
python -m gcf run --input examples/ads_sample.csv --out output --mode dry
```

Result:

- PASS: `output/new_ads.csv` generated
- PASS: `output/figma_variations.tsv` generated
- PASS: `output/report.md` generated
- PASS: `figma_variations.tsv` encoding validated as UTF-8 without BOM
- PASS: Report metrics consistency check (`Copy pieces failed validation: 0`, `Retries (backoff): 0`)

### B) Streamlit dry-run

Commands executed:

```bash
streamlit run app.py --server.headless true --server.port 8501
curl -I http://127.0.0.1:8501
```

Result:

- PASS: Streamlit app starts and serves HTTP 200 locally.
- LIMITATION: Browser automation for full wizard clickthrough could not be completed in this container because Playwright Chromium crashes (`SIGSEGV`) at launch.

### C) Tests

Command executed:

```bash
pytest -v
```

Result:

- PASS: `195 passed`

### D) Lint/format

Commands executed:

```bash
black .
ruff check .
```

Result:

- PASS: `black` completed with repository-wide formatting applied.
- PASS: `ruff check .` passes after minimal cleanup and one runtime bugfix.

## Part 3 — Connector Sanity (offline-friendly)

Covered by existing tests:

- PASS: Google Ads mapping -> AdsRow metrics (`tests/test_google_ads_connector.py`)
- PASS: Meta Ads mapping -> AdsRow metrics (`tests/test_meta_ads_connector.py`)
- PASS: Google Sheets push mocked (`tests/test_google_sheets_connector.py`)
- PASS: Missing credentials returns clear actionable error (Google Sheets connector tests).

## Part 4 — Figma plugin verification

- PASS: `figma_plugin/manifest.json` valid JSON and points to `dist/code.js`.
- PASS: Compiled runtime file present: `figma_plugin/dist/code.js`.
- PASS: Import instructions documented in README workflow section.
- PASS: `code.ts` includes font preflight + guarded font loading with non-crashing skip behavior.
- PASS: UI TSV parser normalizes newlines and reports missing required headers.
- PASS: Generation payload is hard-capped to 100 rows for stability.

## Part 5 — Docs Drift + Troubleshooting

- PASS: Connector docs env names and CLI commands match code (`google-ads pull`, `meta-ads pull`, `sheets push`).
- PASS: README troubleshooting includes overloaded provider, missing columns, token/auth errors, and font load issues.

## Part 6 — Release Finalization

- PASS: Version is `0.1.0` in `gcf/__init__.py`.
- PASS: CLI version works via `python -m gcf --version`.
- PASS: `CHANGELOG.md` includes v0.1.0 key release notes.

## Tag Notes

Overall verdict: **PASS (with one environment limitation)**

Remaining limitation:

- Playwright Chromium crash in this CI/container image prevents end-to-end automated Streamlit wizard clickthrough, but app startup and serving checks are green.
