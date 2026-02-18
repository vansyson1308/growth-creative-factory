"""Tests for Google Sheets connector with mocking (no network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gcf.connectors.google_sheets import GoogleSheetsConfigError, push_tabular_file


def test_missing_credentials_raises(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("a\n1\n", encoding="utf-8")
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(GoogleSheetsConfigError):
            push_tabular_file("sid", "ws", str(f))


def test_push_calls_worksheet_update(tmp_path):
    creds = tmp_path / "sa.json"
    creds.write_text("{}", encoding="utf-8")
    f = tmp_path / "a.csv"
    f.write_text("H1,DESC\nHello,World\n", encoding="utf-8")

    ws = MagicMock()
    sh = MagicMock()
    sh.worksheet.return_value = ws
    client = MagicMock()
    client.open_by_key.return_value = sh

    with patch.dict("os.environ", {"GCF_GOOGLE_CREDS_JSON": str(creds)}, clear=True):
        fake_creds_cls = MagicMock()
        fake_creds_cls.from_service_account_file.return_value = object()
        fake_gspread = MagicMock()
        fake_gspread.authorize.return_value = client

        with patch("gcf.connectors.google_sheets.Credentials", fake_creds_cls):
            with patch("gcf.connectors.google_sheets.gspread", fake_gspread):
                n = push_tabular_file("sid", "ws", str(f))

    assert n == 1
    ws.clear.assert_called_once()
    ws.update.assert_called_once()
