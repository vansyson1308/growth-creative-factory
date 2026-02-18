# Connect Google Ads (Optional, BYO Credentials)

This connector is optional. Manual CSV upload still works without Google Ads setup.

## Required credentials
You need:
- `developer_token`
- `client_id`
- `client_secret`
- `refresh_token`
- `customer_id` (required)
- `login_customer_id` (optional)

## Option A: `google-ads.yaml`
Create a local `google-ads.yaml` (do **not** commit):

```yaml
developer_token: "YOUR_DEV_TOKEN"
client_id: "YOUR_OAUTH_CLIENT_ID"
client_secret: "YOUR_OAUTH_CLIENT_SECRET"
refresh_token: "YOUR_REFRESH_TOKEN"
customer_id: "1234567890"
# login_customer_id: "0987654321"
```

## Option B: Environment variables
```bash
export GCF_GOOGLE_ADS_DEVELOPER_TOKEN=...
export GCF_GOOGLE_ADS_CLIENT_ID=...
export GCF_GOOGLE_ADS_CLIENT_SECRET=...
export GCF_GOOGLE_ADS_REFRESH_TOKEN=...
export GCF_GOOGLE_ADS_CUSTOMER_ID=1234567890
# optional
export GCF_GOOGLE_ADS_LOGIN_CUSTOMER_ID=0987654321
```

## Get refresh token (OAuth helper)
```bash
export GCF_GOOGLE_CLIENT_ID=...
export GCF_GOOGLE_CLIENT_SECRET=...
python scripts/google_ads_oauth.py
```

Store the printed refresh token securely (never commit it).

## Pull command
```bash
python -m gcf google-ads pull --customer_id 1234567890 --date_range LAST_30_DAYS --out input/ads.csv
```

Supported level:
- `--level ad` (default)

## Streamlit usage
Open **Connectors → Google Ads**, input Customer ID + Date range, then click **Pull from Google Ads**.

## Troubleshooting
- Auth/permission errors: verify account access, developer token status, OAuth credentials, and refresh token.
- Rate limit/quota errors: connector retries with exponential backoff + jitter.
