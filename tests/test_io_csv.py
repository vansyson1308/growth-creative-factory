"""Tests for io_csv helpers — focussed on the Figma TSV output."""

from __future__ import annotations

from pathlib import Path

from gcf.io_csv import (
    InputSchemaError,
    read_ads_csv,
    write_figma_tsv,
    write_handoff_csv,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_sample(tmp_path: Path) -> Path:
    rows = [
        {"H1": "Tiết kiệm ngay", "DESC": "Mua ngay để nhận ưu đãi.", "TAG": "V001"},
        {"H1": "Ưu đãi có hạn", "DESC": "Sản phẩm chất lượng cao.", "TAG": "V002"},
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
        assert not raw.startswith(
            bom
        ), "TSV file starts with a UTF-8 BOM — Figma plugin expects no BOM."

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
        lines = [
            line
            for line in tsv.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
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


class TestHandoffCsv:
    def test_handoff_schema_and_blank_columns(self, tmp_path):
        rows = [
            {
                "variant_set_id": "vs_001",
                "TAG": "V001",
                "H1": "Save now",
                "DESC": "Shop today",
            }
        ]
        out = tmp_path / "handoff.csv"
        write_handoff_csv(rows, out)

        lines = out.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "variant_set_id,TAG,H1,DESC,status,notes"
        assert lines[1].endswith(",,")


class TestInputValidation:
    def test_missing_required_columns_has_suggestions(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("campaign,ad_id\nC1,A1\n", encoding="utf-8")
        try:
            read_ads_csv(bad)
            assert False, "Expected InputSchemaError"
        except InputSchemaError as e:
            msg = str(e)
            assert "missing required" in msg.lower()
            assert "ad_group" in msg
            assert "headline" in msg

    def test_numeric_normalization_and_nan(self, tmp_path):
        p = tmp_path / "ok.csv"
        p.write_text(
            "campaign,ad_group,ad_id,headline,description,impressions,clicks,cost,conversions,revenue\n"
            "C1,G1,A1,H,D,1000,10,50,0,0\n"
            "C1,G1,A2,H,D,,nan,,2,200\n",
            encoding="utf-8",
        )
        df = read_ads_csv(p)
        assert int(df.loc[1, "impressions"]) == 0
        assert float(df.loc[1, "spend"]) == 0.0
