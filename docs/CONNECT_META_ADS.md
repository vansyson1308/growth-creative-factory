# Connect Meta Ads (Optional, BYO Credentials)

This connector is optional. Manual CSV upload remains fully supported.

## Required environment variables
- `META_ACCESS_TOKEN`
- `META_AD_ACCOUNT_ID` (format: `act_<id>`)

Optional:
- `META_APP_ID`
- `META_APP_SECRET`
- `META_ACTION_PRIORITY` (comma-separated, e.g. `purchase,lead,complete_registration`)

Example:
```bash
export META_ACCESS_TOKEN="<token>"
export META_AD_ACCOUNT_ID="act_1234567890"
export META_ACTION_PRIORITY="purchase,lead,complete_registration"
```

## Access token overview (guideline)
Use Meta developer/business tooling to obtain a token with ad insights permissions for your ad account.
Typical scopes include read access to ads and insights. Token creation details vary by app mode and business setup.

## Pull command
```bash
python -m gcf meta-ads pull --date_preset last_30d --out input/ads.csv
```

## Conversion/revenue mapping
The connector reads:
- `actions` → conversion counts
- `action_values` → revenue values

It chooses the first available action type from priority order:
1. `purchase`
2. `lead`
3. `complete_registration`

Override with env:
```bash
export META_ACTION_PRIORITY="purchase,subscribe,lead"
```

## Streamlit usage
Open **Connectors → Meta Ads**, choose date preset, click **Pull from Meta Ads**.

## Troubleshooting
- Invalid token / permissions: refresh token and verify account access.
- Rate limits / transient API errors: connector retries with exponential backoff + jitter.
