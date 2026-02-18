"""Helper to obtain Google Ads refresh token (installed app OAuth flow).

Usage:
  export GCF_GOOGLE_CLIENT_ID=...
  export GCF_GOOGLE_CLIENT_SECRET=...
  python scripts/google_ads_oauth.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    client_id = os.environ.get("GCF_GOOGLE_CLIENT_ID") or os.environ.get(
        "GOOGLE_CLIENT_ID"
    )
    client_secret = os.environ.get("GCF_GOOGLE_CLIENT_SECRET") or os.environ.get(
        "GOOGLE_CLIENT_SECRET"
    )

    if not client_id or not client_secret:
        print(
            "Missing client credentials. Set GCF_GOOGLE_CLIENT_ID and "
            "GCF_GOOGLE_CLIENT_SECRET (or GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET).",
            file=sys.stderr,
        )
        return 2

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception:
        print(
            "Missing dependency google-auth-oauthlib. Install it and retry.",
            file=sys.stderr,
        )
        return 2

    scopes = ["https://www.googleapis.com/auth/adwords"]
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    creds = flow.run_local_server(port=8080, prompt="consent", access_type="offline")

    print("\n✅ OAuth complete.")
    print("Your refresh token (store securely, do not commit):")
    print(creds.refresh_token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
