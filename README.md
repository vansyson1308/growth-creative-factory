# Growth Creative Factory

AI-powered ad variation pipeline for marketing teams. Upload underperforming ads, auto-generate headline & description variations (Google Ads / Meta Ads compliant), and export directly to Figma for bulk creative production.

---

## Quick start (dry-run)

**No API key required.** The dry-run mode uses the built-in mock provider so you can verify the entire pipeline locally before touching the Anthropic API.

### Step 1 — Install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Step 2 — Run the pipeline

```bash
python -m gcf run \
  --input  examples/ads_sample.csv \
  --out    output \
  --mode   dry
```

Windows one-liner:

```
scripts\run_cli.bat
```

Expected terminal output:

```
🏃 DRY-RUN mode — using MockProvider (no API calls)
📂 Input:  examples/ads_sample.csv
📂 Output: output
✅ Pipeline complete!
   Ads analyzed:      8
   Underperforming:   N
   Variants created:  M
   Validation passed: P
   Validation failed: F
   Files written to:  output/
```

### Step 3 — Verify the output files

| File | What it contains |
|------|-----------------|
| `output/new_ads.csv` | All H1 × DESC variant combinations — bulk-upload ready |
| `output/figma_variations.tsv` | **UTF-8 no BOM** · columns `H1 TAB DESC TAB TAG` — paste straight into Figma plugin |
| `output/report.md` | Run summary: stats, strategies, variant-set IDs |

Quick sanity checks:

```bash
# Confirm TSV has no BOM (first 3 bytes must NOT be ef bb bf)
python - <<'EOF'
raw = open("output/figma_variations.tsv", "rb").read(3)
assert raw != b"\xef\xbb\xbf", "BOM found! Encoding bug."
print("✅  No BOM — file is clean UTF-8")
EOF

# Confirm all H1 <= 30 chars and all DESC <= 90 chars
python - <<'EOF'
import csv
with open("output/figma_variations.tsv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f, delimiter="\t"):
        h1_len = len(row["H1"])
        d_len  = len(row["DESC"])
        assert h1_len <= 30, f"H1 too long ({h1_len}): {row['H1']!r}"
        assert d_len  <= 90, f"DESC too long ({d_len}): {row['DESC']!r}"
print("✅  All char limits OK")
EOF
```

### Step 4 — Run tests

```bash
pytest tests/ -v
```

The suite covers `char_count()`, `validate_limits()`, `dedupe()`, TSV encoding, and TSV schema.

---

## Setup (Manual)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## CLI Usage

```bash
# Dry-run (mock data, no API calls)
python -m gcf run --input examples/ads_sample.csv --out output --mode dry

# Live (calls Anthropic API — requires ANTHROPIC_API_KEY in .env)
python -m gcf run --input input/ads.csv --out output --mode live --config config.yaml

# Ingest performance results into memory
python -m gcf ingest-results --input results/performance.csv
```

## Streamlit App

```bash
streamlit run app.py
```

Upload CSV → set thresholds → click Generate → download outputs.

## Output Files

| File | Purpose |
|------|---------|
| `output/new_ads.csv` | Bulk-friendly CSV with all variant combinations |
| `output/figma_variations.tsv` | TSV for pasting into Figma plugin |
| `output/report.md` | Run summary with stats and strategy notes |

## Config

Edit `config.yaml` to adjust thresholds, generation limits, policy filters, and LLM settings.

## Tests

```bash
pytest tests/ -v
```

---

## Marketing SOP (1 page)

### Step 1: Export CSV from Ads Platform
Export your ad performance data from Google Ads or Meta Ads Manager. Required columns: `campaign, ad_group, ad_id, headline, description, impressions, clicks, cost, conversions, revenue`.

### Step 2: Generate Variations
Open the Streamlit app (`scripts\run_app.bat` or `streamlit run app.py`). Upload your CSV, adjust thresholds if needed, select dry-run or live mode, and click **Generate Variations**. Download all 3 output files.

### Step 3: Import Plugin into Figma
In Figma Desktop: Menu → Plugins → Development → Import plugin from manifest. Select `figma_plugin/manifest.json`. The plugin appears under Plugins → Growth Creative Factory.

### Step 4: Create Variations in Figma
1. Create a frame named `AD_TEMPLATE` with text layers named `H1` and `DESC` (optional: `CTA`, `H2`).
2. Open the plugin (Plugins → Growth Creative Factory).
3. Open `figma_variations.tsv` in any text editor, Select All, Copy.
4. Paste into the TSV text area in the plugin.
5. Click **Generate Variations** → up to 100 frames appear in a grid.

### Step 5: Export PNGs (Optional)
Click **Export PNGs** in the plugin to download all generated frames as 2x PNG files.

### Step 6: Close the Loop — Ingest Results
After running ads with the new variations, export performance data as `performance.csv` (columns: `variant_set_id, campaign, ctr, cpa, roas, notes`). Then run:
```bash
python -m gcf ingest-results --input results/performance.csv
```
This feeds learnings into the memory log so the next generation cycle produces smarter copy.

---

## Repo Structure

```
growth-creative-factory/
├── gcf/                        # Core Python package
│   ├── cli.py                  # Click CLI entry point
│   ├── pipeline.py             # Main orchestrator
│   ├── config.py               # YAML config loader
│   ├── io_csv.py               # CSV/TSV I/O
│   ├── selector.py             # Underperforming ad selector
│   ├── generator_headline.py   # Headline sub-agent
│   ├── generator_description.py# Description sub-agent
│   ├── validator.py            # Char limit + policy checker
│   ├── dedupe.py               # Near-duplicate removal
│   ├── memory.py               # JSONL memory log
│   ├── providers/              # LLM provider abstraction
│   │   ├── base.py
│   │   ├── anthropic_provider.py
│   │   └── mock_provider.py
│   └── prompts/                # Jinja2 prompt templates
│       ├── selector_prompt.txt
│       ├── headline_prompt.txt
│       ├── description_prompt.txt
│       └── checker_prompt.txt
├── app.py                      # Streamlit UI
├── config.yaml                 # Default configuration
├── figma_plugin/               # Figma plugin (ready to import)
│   ├── manifest.json
│   ├── ui.html
│   ├── code.ts
│   └── dist/code.js            # Pre-built JS
├── scripts/
│   ├── run_app.bat             # One-click Streamlit launcher
│   └── run_cli.bat             # One-click CLI launcher
├── examples/ads_sample.csv     # Sample input
├── input/                      # Your input files
├── output/                     # Generated outputs
├── memory/                     # Memory log (auto-created)
├── tests/                      # Pytest suite
├── requirements.txt
├── .env.example
└── README.md
```

## License

Internal use. Modify as needed for your team.
