# Growth Creative Factory — Status Audit Report

**Date:** 2026-02-17
**Auditor:** automated (Claude)
**Commit scope:** read-only audit; no code changes

---

## 1. What Works (Confirmed)

| Component | Status | Notes |
|-----------|--------|-------|
| **CLI dry-run** (`python -m gcf run --mode dry`) | ✅ Pass | 8 ads read → 4 selected → 240 variants → 3 output files |
| **Config loading** (`config.yaml` → dataclasses) | ✅ Pass | All sub-configs parsed correctly |
| **CSV read / derived metrics** (CTR, CPA, ROAS) | ✅ Pass | Division-by-zero handled via NaN |
| **Selector** (threshold-based underperformance) | ✅ Pass | 4/8 ads flagged; reasons string accurate |
| **Headline generator** (mock provider) | ✅ Pass | 10 headlines returned per ad |
| **Description generator** (mock provider) | ✅ Pass | 6 descriptions returned per ad |
| **Deduplication** (rapidfuzz with difflib fallback) | ✅ Pass | Fallback ratio correctly scaled ×100 |
| **Validator** (char limit, all-caps, policy regex) | ✅ Pass | All 20 validator tests pass |
| **Output: new_ads.csv** | ✅ Pass | 240 rows, correct columns, utf-8-sig encoding |
| **Output: figma_variations.tsv** | ✅ Pass | Tab-separated H1/DESC/TAG, 240 rows |
| **Output: report.md** | ✅ Pass | Summary + per-ad detail rendered |
| **Memory JSONL** (append + load) | ✅ Pass | 4 entries logged after dry run |
| **Unit tests** (30 tests across 3 modules) | ✅ Pass | test_validator (20), test_dedupe (6), test_selector (4) — all green |
| **Figma plugin manifest + UI** | ✅ Present | manifest.json, ui.html, code.ts, dist/code.js all present |
| **Prompt templates** (Jinja2) | ✅ Present | headline_prompt.txt, description_prompt.txt, selector_prompt.txt, checker_prompt.txt |

---

## 2. Issues Found (Thiếu / Chưa Đúng)

### 2.1 Bugs

| # | Severity | File | Issue |
|---|----------|------|-------|
| B1 | **Medium** | `pipeline.py:74` | `total_fail` counter initialised to 0 but **never incremented**. Report always shows `fail_count = 0`. |
| B2 | **Low** | `mock_provider.py:45` | `__init__(self, seed: int = 42)` — passing a `ProviderConfig` object instead of int causes `TypeError: unhashable type`. Current CLI/app.py call `MockProvider()` with default so bug is latent. |
| B3 | **Medium** | `generator_headline.py`, `generator_description.py` | Retry loop **accumulates** `all_valid` across attempts instead of resetting. May return inconsistent mix of results from different retry rounds. |
| B4 | **Low** | `app.py:69-78` | Output files are written inside `tempfile.TemporaryDirectory()` context manager. Download buttons reference paths **after** the `with` block exits in Streamlit flow — may work due to Streamlit's caching, but fragile. |

### 2.2 TSV Format

- TSV file uses `utf-8-sig` encoding (BOM `\xEF\xBB\xBF` prefix). Figma plugin's `ui.html` splits on `\t` and `\n`, so the BOM will be embedded in the first header cell (`﻿H1` instead of `H1`). Not a blocker because Figma plugin matches headers by position, not name, but breaks any downstream tool that checks header names.

### 2.3 Memory JSONL

- **No corruption handling**: `load_memory()` silently skips bad lines (good), but `append_entry()` has no file locking — parallel runs can interleave partial JSON lines.
- **Unbounded growth**: no pruning or rotation strategy. Over time the file will slow down `_build_memory_context`.
- **Performance ingestion** (`ingest-results`) expects `variant_set_id`, `ctr`, `cpa`, `roas` columns but doesn't validate their presence.

### 2.4 Retry & Validation

- Generator retry loop generates new candidates each round but does **not re-validate** the accumulated set. There is no "retry on validation failure" logic — it just generates more and hopes enough are valid.
- Validation failures are silently discarded. No logging of which candidates failed or why.
- `checker_prompt.txt` exists for LLM-based validation but is **unused** (dead code).

### 2.5 Figma Plugin Font Loading

- `code.ts` collects fonts from template text nodes via `fontName` property and calls `figma.loadFontAsync()`. However:
  - If a font is unavailable on the machine, the load silently fails and text nodes default to the system font — mismatching the design.
  - No user-facing error message when a font fails to load.
  - `dist/code.js` is a pre-compiled snapshot; any edits to `code.ts` won't take effect until recompiled (no build script in repo).

### 2.6 Other Gaps

- **No API retry/backoff**: `AnthropicProvider.generate()` has zero retry logic. A transient 429 or 500 will crash the pipeline.
- **No input validation**: CLI and Streamlit accept any CSV without checking required columns exist.
- **Selector & checker prompts unused**: `selector_prompt.txt` and `checker_prompt.txt` are in the repo but never loaded — dead code or planned features.
- **No test coverage** for `pipeline.py`, `config.py`, `memory.py`, `io_csv.py`, `cli.py`, `app.py`, providers.
- **No logging framework**: all output is `click.echo` or Streamlit calls. No structured logs for debugging.

---

## 3. Upgrade Priorities

| Priority | # | Task | Rationale |
|----------|---|------|-----------|
| **P0** | 1 | **Add API retry with exponential backoff** in `AnthropicProvider.generate()` | Live mode will crash on transient errors. Blocking for production use. |
| **P0** | 2 | **Fix `total_fail` counter** in `pipeline.py` — actually track validation failures | Report data is misleading; users can't trust quality metrics. |
| **P0** | 3 | **Add input CSV column validation** (required columns check with clear error) | Garbage-in currently produces cryptic KeyError. |
| **P1** | 4 | **Fix generator retry logic** — reset `all_valid` per attempt or properly dedupe across attempts | Inconsistent quality; may mix good/bad candidates silently. |
| **P1** | 5 | **Remove BOM from TSV output** — use `encoding="utf-8"` for `write_figma_tsv()` | BOM breaks header matching in downstream tools and Figma plugin edge cases. |
| **P1** | 6 | **Add integration test** covering full pipeline dry-run end-to-end (mock provider → CSV → TSV → report → memory) | Core orchestration has zero test coverage. |
| **P1** | 7 | **Add file locking or atomic writes** for `memory.jsonl` | Parallel runs can corrupt the memory file. |
| **P2** | 8 | **Implement LLM-based checker** using `checker_prompt.txt` as a second validation pass | Currently dead code; would catch semantic issues that regex misses (e.g., misleading claims). |
| **P2** | 9 | **Add structured logging** (`logging` module) with configurable level | No observability today. Critical for debugging live runs. |
| **P2** | 10 | **Figma plugin: add font fallback + error banner** when `loadFontAsync` fails; add `npm build` script | Silent font failures produce broken designs; no build pipeline for TS → JS. |

---

## 4. File Structure Audit

```
growth-creative-factory/
├── app.py                          ✅ Streamlit UI
├── config.yaml                     ✅ Central config
├── requirements.txt                ✅ Dependencies (no pinning)
├── .env.example                    ✅ API key template
├── .gitignore                      ✅ Correct exclusions
├── README.md                       ✅ Present
│
├── gcf/
│   ├── __init__.py                 ✅ v1.0.0
│   ├── __main__.py                 ✅ CLI entry
│   ├── cli.py                      ✅ Click commands
│   ├── config.py                   ✅ Dataclass configs
│   ├── pipeline.py                 ⚠️ total_fail bug
│   ├── generator_headline.py       ⚠️ Retry accumulation
│   ├── generator_description.py    ⚠️ Retry accumulation
│   ├── selector.py                 ✅ Clean
│   ├── validator.py                ✅ Clean
│   ├── dedupe.py                   ✅ Clean
│   ├── memory.py                   ⚠️ No locking
│   ├── io_csv.py                   ⚠️ BOM in TSV
│   │
│   ├── providers/
│   │   ├── __init__.py             ✅
│   │   ├── base.py                 ✅ ABC
│   │   ├── anthropic_provider.py   ⚠️ No retry
│   │   └── mock_provider.py        ⚠️ Latent seed bug
│   │
│   └── prompts/
│       ├── headline_prompt.txt     ✅ Used
│       ├── description_prompt.txt  ✅ Used
│       ├── selector_prompt.txt     ❌ Unused (dead code)
│       └── checker_prompt.txt      ❌ Unused (dead code)
│
├── tests/
│   ├── __init__.py                 ✅
│   ├── test_validator.py           ✅ 20 tests
│   ├── test_dedupe.py              ✅ 6 tests
│   └── test_selector.py            ✅ 4 tests
│
├── figma_plugin/
│   ├── manifest.json               ✅
│   ├── ui.html                     ✅
│   ├── code.ts                     ⚠️ No font error handling
│   └── dist/code.js                ⚠️ No build script
│
├── examples/
│   └── ads_sample.csv              ✅ 8 sample ads
│
├── input/                          ✅ .gitkeep
├── output/                         ✅ Sample outputs present
├── memory/
│   └── memory.jsonl                ✅ Sample entries
│
├── scripts/
│   ├── run_app.bat                 ✅ Windows launcher
│   └── run_cli.bat                 ✅ Windows launcher
│
└── docs/
    └── STATUS.md                   ← this file
```

---

*End of audit report.*
