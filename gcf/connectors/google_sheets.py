"""Optional Google Sheets connector for handoff workflows."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import pandas as pd

try:
    import gspread  # type: ignore
except Exception:  # pragma: no cover
    gspread = None

try:
    from google.oauth2.service_account import Credentials  # type: ignore
except Exception:  # pragma: no cover
    Credentials = None


class GoogleSheetsConfigError(RuntimeError):
    pass


def _resolve_creds_path() -> str:
    path = os.environ.get("GCF_GOOGLE_CREDS_JSON") or os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if not path:
        raise GoogleSheetsConfigError(
            "Google credentials not configured. Set GCF_GOOGLE_CREDS_JSON or "
            "GOOGLE_APPLICATION_CREDENTIALS to a Service Account JSON path. "
            "See docs/CONNECT_GOOGLE_SHEETS.md"
        )
    if not Path(path).exists():
        raise GoogleSheetsConfigError(
            f"Credential file not found: {path}. See docs/CONNECT_GOOGLE_SHEETS.md"
        )
    return path


def push_tabular_file(spreadsheet_id: str, worksheet: str, input_path: str) -> int:
    """Push CSV/TSV to a worksheet. Returns number of data rows uploaded."""
    creds_path = _resolve_creds_path()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    if gspread is None or Credentials is None:
        raise GoogleSheetsConfigError(
            "Google Sheets dependencies missing. Install gspread and google-auth, "
            "then retry."
        )

    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)

    p = Path(input_path)
    if p.suffix.lower() == ".tsv":
        df = pd.read_csv(p, sep="\t", dtype=str).fillna("")
    else:
        df = pd.read_csv(p, dtype=str).fillna("")

    sh = client.open_by_key(spreadsheet_id)
    ws = sh.worksheet(worksheet)

    values: List[List[str]] = [list(df.columns)] + df.astype(str).values.tolist()
    ws.clear()
    ws.update("A1", values)
    return len(df)
