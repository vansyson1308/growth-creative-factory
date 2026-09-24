# Project Status

**Version:** 0.2.0 · **Updated:** 2026-09-24

## Health

| Area | Status |
|---|---|
| Test suite | 326 tests, Python 3.10–3.13 |
| Lint / format | `ruff`, `black` enforced in CI |
| End-to-end | CI smoke job runs `gcf run`, `gcf create`, `gcf render` on a core-only install and uploads the rendered images |
| Packaging | `pip install .` → `gcf` console script; extras `ui`, `connectors`, `dev` |

## Feature matrix

| Capability | Dry (offline) | Live (Claude) |
|---|---|---|
| Underperformer selection (CTR/CPA/ROAS) | ✅ | ✅ |
| Root-cause strategy per ad | ✅ heuristic | ✅ LLM |
| Headline / description variants | ✅ offline copywriter | ✅ LLM |
| Character limits, ALL-CAPS, policy blocklist | ✅ | ✅ |
| LLM compliance checker + targeted retries | ✅ (mock passes) | ✅ |
| Brand-voice guideline + risky-claim filter | — | ✅ |
| Brief → social posts | ✅ | ✅ |
| Image rendering (6 templates × 5 formats) | ✅ | ✅ |
| Memory log + results ingestion | ✅ | ✅ |
| Budget, retry/backoff, cache, refusal fallbacks | n/a | ✅ |

## Resolved from the February 2026 audit

- API retry/backoff, validation-failure accounting, input schema validation — done in 0.1.0.
- BOM-free TSV, generator retry logic, checker/selector prompts wired in — done in 0.1.0.
- Wizard duplicated the pipeline without strategy/checker — now shares `generate_variants`.
- Tag collisions across ads, per-run cap semantics, checker index drift, policy regex gaps —
  fixed in 0.2.0 (see CHANGELOG).
- "Needs Figma to get images" — the built-in creative engine now renders final images; the
  Figma plugin remains for fully custom layouts.

## Known limitations

- Right-to-left scripts and complex shaping (Arabic, Thai, Devanagari) are not yet supported
  by the bundled fonts; Latin and Vietnamese are fully covered.
- The offline copywriter is template-based: great for dry runs and demos, but live mode
  writes noticeably more specific copy.
- `memory.jsonl` has no file locking; avoid concurrent runs writing to the same file.
