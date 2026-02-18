"""Tests for io_csv helpers — focussed on the Figma TSV output."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from gcf.io_csv import write_figma_tsv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_sample(tmp_path: Path) -> Path:
    rows = [
        {"H1": "Tiết kiệm ngay", "DESC": "Mua ngay để nhận ưu đãi.", "TAG": "V001"},
        {"H1": "Ưu đãi có hạn",  "DESC": "Sản phẩm chất lượng cao.", "TAG": "V002"},
    ]
    out = tmp_path / "figma_variations.tsv"
    write_figma_tsv(rows, out)
    return out


# ---------------------------------------------------------------------------
# Encoding tests
# ---------------------------------------------------------------------------

class TestFigmaTsvEncoding:
    """figma_variations.tsv must be UTF-8 *without* BOM."""

    def test_no_bom(self, tmp_path):
        """First 3 bytes must NOT be the UTF-8 BOM (0xEF 0xBB 0xBF)."""
        tsv = _write_sample(tmp_path)
        raw = tsv.read_bytes()
        bom = b"\xef\xbb\xbf"
        assert not raw.startswith(bom), (
            "TSV file starts with a UTF-8 BOM — Figma plugin expects no BOM."
        )

    def test_utf8_readable(self, tmp_path):
        """File must decode as UTF-8 without errors."""
        tsv = _write_sample(tmp_path)
        content = tsv.read_text(encoding="utf-8")  # would raise if broken
        assert "Tiết kiệm ngay" in content

    def test_tab_separated(self, tmp_path):
        """Each data row must contain tab delimiters."""
        tsv = _write_sample(tmp_path)
        lines = tsv.read_text(encoding="utf-8").splitlines()
        # Skip header row; every data row has tabs
        for line in lines[1:]:
            assert "\t" in line, f"No tab found in line: {line!r}"


# ---------------------------------------------------------------------------
# Column order / schema tests
# ---------------------------------------------------------------------------

class TestFigmaTsvSchema:
    """Figma TSV must have exactly H1, DESC, TAG columns in that order."""

    def test_column_order(self, tmp_path):
        tsv = _write_sample(tmp_path)
        header = tsv.read_text(encoding="utf-8").splitlines()[0]
        assert header == "H1\tDESC\tTAG"

    def test_row_count(self, tmp_path):
        tsv = _write_sample(tmp_path)
        lines = [l for l in tsv.read_text(encoding="utf-8").splitlines() if l.strip()]
        # header + 2 data rows
        assert len(lines) == 3

    def test_missing_tag_gets_empty_string(self, tmp_path):
        """Rows without TAG should still produce a valid file."""
        rows = [{"H1": "H", "DESC": "D"}]  # no TAG key
        out = tmp_path / "no_tag.tsv"
        write_figma_tsv(rows, out)
        header = out.read_text(encoding="utf-8").splitlines()[0]
        assert header == "H1\tDESC\tTAG"
        data_row = out.read_text(encoding="utf-8").splitlines()[1]
        parts = data_row.split("\t")
        assert len(parts) == 3

    def test_parent_dir_created(self, tmp_path):
        """write_figma_tsv must create missing parent directories."""
        out = tmp_path / "nested" / "dir" / "figma.tsv"
        write_figma_tsv([{"H1": "H", "DESC": "D", "TAG": "V001"}], out)
        assert out.exists()
