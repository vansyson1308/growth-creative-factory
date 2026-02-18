# Privacy

Growth Creative Factory is designed to run locally on your machine.

## Data handling model

- Input CSV/TSV files are processed locally.
- Generated outputs are written to your local `output/` directory.
- Memory/cache files are stored locally unless you explicitly move them.

## Credentials

You bring your own credentials via environment variables or local credential files.
Common examples:

- `ANTHROPIC_API_KEY`
- `META_ACCESS_TOKEN`
- Google Ads / Google Sheets credential files

Never commit these credentials to git.

## External data transfer

The project only sends data to providers you explicitly configure:

- Anthropic (if running in `live` mode)
- Meta Ads API (if using Meta connector)
- Google Ads API (if using Google Ads connector)
- Google Sheets API (if using Sheets connector)

If you use `dry` mode with the mock provider and no connectors, no external provider calls are made.
