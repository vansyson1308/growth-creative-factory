"""Tests for gcf.memory — schema, ingest, and analytics helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gcf.memory import (
    _normalize,
    append_entry,
    get_recent_experiments,
    get_top_angles,
    ingest_performance,
    load_memory,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ─────────────────────────────────────────────────────────────────────────────


def _write_entry(path: Path, **kwargs) -> None:
    """Helper: write a raw JSON line without going through append_entry."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(kwargs, ensure_ascii=False) + "\n")


def _make_mem(tmp_path: Path) -> Path:
    return tmp_path / "memory.jsonl"


# ─────────────────────────────────────────────────────────────────────────────
# TestNormalize — backward-compatibility normalisation
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalize:
    def test_old_schema_headlines_moved_to_generated(self):
        entry = {
            "inputs": {"ad_id": "AD001"},
            "outputs": {"headlines": ["H1"], "descriptions": ["D1"]},
        }
        n = _normalize(entry)
        assert n["generated"]["headlines"] == ["H1"]
        assert n["generated"]["descriptions"] == ["D1"]
        assert n["ad_id"] == "AD001"

    def test_old_schema_missing_fields_get_defaults(self):
        entry = {"outputs": {"headlines": []}}
        n = _normalize(entry)
        assert n["ad_group"] == ""
        assert n["angle"] == ""
        assert n["tag"] == ""
        assert n["results"] is None

    def test_old_perf_ingest_metrics_moved_to_results(self):
        entry = {
            "hypothesis": "performance_ingest",
            "outputs": {"ctr": 0.02, "cpa": 40.0, "roas": 3.0},
        }
        n = _normalize(entry)
        assert n["results"]["roas"] == 3.0
        assert n["generated"]["headlines"] == []

    def test_new_schema_unchanged(self):
        entry = {
            "campaign": "X",
            "ad_group": "G",
            "ad_id": "A1",
            "angle": "urgency",
            "tag": "t1",
            "generated": {"headlines": ["H"], "descriptions": ["D"]},
            "results": {"roas": 4.0},
        }
        n = _normalize(entry)
        assert n["results"]["roas"] == 4.0
        assert n["generated"]["headlines"] == ["H"]
        assert n["angle"] == "urgency"

    def test_idempotent_double_normalize(self):
        entry = {
            "inputs": {"ad_id": "AD002"},
            "outputs": {"headlines": ["X"], "descriptions": []},
        }
        first = _normalize(entry.copy())
        second = _normalize(first.copy())
        assert first["generated"] == second["generated"]
        assert first["ad_id"] == second["ad_id"]


# ─────────────────────────────────────────────────────────────────────────────
# TestAppendEntry — new-schema writes
# ─────────────────────────────────────────────────────────────────────────────


class TestAppendEntry:
    def test_creates_file_if_missing(self, tmp_path):
        mem = _make_mem(tmp_path)
        assert not mem.exists()
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": ["H1"], "descriptions": ["D1"]},
        )
        assert mem.exists()

    def test_correct_schema_keys(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="Summer",
            ad_group="GroupA",
            ad_id="AD001",
            hypothesis="Improve CTR",
            angle="urgency",
            tag="round1",
            variant_set_id="vs_001",
            generated={"headlines": ["H"], "descriptions": ["D"]},
            notes="mode=dry",
        )
        line = json.loads(mem.read_text(encoding="utf-8").strip())
        assert line["campaign"] == "Summer"
        assert line["ad_group"] == "GroupA"
        assert line["ad_id"] == "AD001"
        assert line["angle"] == "urgency"
        assert line["tag"] == "round1"
        assert line["generated"]["headlines"] == ["H"]
        assert line["results"] is None
        assert "date" in line

    def test_multiple_entries_separate_lines(self, tmp_path):
        mem = _make_mem(tmp_path)
        for i in range(3):
            append_entry(
                mem,
                campaign=f"C{i}",
                hypothesis="test",
                variant_set_id=f"vs_{i:03d}",
                generated={"headlines": [], "descriptions": []},
            )
        lines = [
            line
            for line in mem.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 3

    def test_results_field_can_be_populated(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": [], "descriptions": []},
            results={"roas": 4.2, "ctr": 0.025},
        )
        entry = json.loads(mem.read_text(encoding="utf-8").strip())
        assert entry["results"]["roas"] == 4.2
        assert entry["results"]["ctr"] == 0.025

    def test_utf8_vietnamese_preserved(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="Tết",
            hypothesis="Tăng CTR",
            variant_set_id="vs_vn_001",
            generated={"headlines": ["Tiết kiệm ngay"], "descriptions": []},
        )
        raw = mem.read_bytes()
        assert "Tiết kiệm ngay".encode("utf-8") in raw
        # Must NOT be BOM-encoded
        assert not raw.startswith(b"\xef\xbb\xbf")


# ─────────────────────────────────────────────────────────────────────────────
# TestLoadMemory — reading and normalising
# ─────────────────────────────────────────────────────────────────────────────


class TestLoadMemory:
    def test_empty_file_returns_empty_list(self, tmp_path):
        mem = _make_mem(tmp_path)
        mem.touch()
        assert load_memory(mem) == []

    def test_missing_file_returns_empty_list(self, tmp_path):
        mem = _make_mem(tmp_path)
        assert load_memory(mem) == []

    def test_new_schema_entry_loaded(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": ["H1"], "descriptions": []},
        )
        entries = load_memory(mem)
        assert len(entries) == 1
        assert entries[0]["generated"]["headlines"] == ["H1"]

    def test_old_schema_normalised_on_load(self, tmp_path):
        mem = _make_mem(tmp_path)
        _write_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_old",
            inputs={"ad_id": "AD99"},
            outputs={"headlines": ["H"], "descriptions": ["D"]},
            notes="old format",
        )
        entries = load_memory(mem)
        assert entries[0]["ad_id"] == "AD99"
        assert entries[0]["generated"]["headlines"] == ["H"]
        assert entries[0]["results"] is None

    def test_blank_lines_skipped(self, tmp_path):
        mem = _make_mem(tmp_path)
        mem.write_text(
            '\n{"campaign": "C", "hypothesis": "H", "variant_set_id": "vs_x", '
            '"generated": {"headlines": [], "descriptions": []}, "results": null}\n\n',
            encoding="utf-8",
        )
        entries = load_memory(mem)
        assert len(entries) == 1

    def test_mixed_old_new_schemas(self, tmp_path):
        mem = _make_mem(tmp_path)
        # Old entry
        _write_entry(
            mem,
            campaign="C",
            hypothesis="old",
            variant_set_id="vs_old",
            inputs={"ad_id": "AD1"},
            outputs={"headlines": ["X"], "descriptions": []},
        )
        # New entry
        append_entry(
            mem,
            campaign="C",
            hypothesis="new",
            variant_set_id="vs_new",
            generated={"headlines": ["Y"], "descriptions": []},
        )
        entries = load_memory(mem)
        assert len(entries) == 2
        assert entries[0]["generated"]["headlines"] == ["X"]
        assert entries[1]["generated"]["headlines"] == ["Y"]


# ─────────────────────────────────────────────────────────────────────────────
# TestIngestPerformance — update-or-append logic
# ─────────────────────────────────────────────────────────────────────────────


class TestIngestPerformance:
    def _seed(self, mem: Path, vsid: str, campaign: str = "C") -> None:
        append_entry(
            mem,
            campaign=campaign,
            hypothesis="test",
            variant_set_id=vsid,
            generated={"headlines": ["H"], "descriptions": ["D"]},
        )

    def test_update_existing_entry(self, tmp_path):
        mem = _make_mem(tmp_path)
        self._seed(mem, "vs_001")

        perf = pd.DataFrame([{"variant_set_id": "vs_001", "roas": 4.5, "ctr": 0.03}])
        updated, appended = ingest_performance(mem, perf)

        assert updated == 1
        assert appended == 0
        entries = load_memory(mem)
        assert entries[-1]["results"]["roas"] == 4.5
        assert entries[-1]["results"]["ctr"] == 0.03

    def test_append_unknown_variant_set(self, tmp_path):
        mem = _make_mem(tmp_path)

        perf = pd.DataFrame(
            [
                {
                    "variant_set_id": "vs_NOTEXIST",
                    "campaign": "New",
                    "roas": 2.1,
                    "cpa": 60.0,
                }
            ]
        )
        updated, appended = ingest_performance(mem, perf)

        assert updated == 0
        assert appended == 1
        entries = load_memory(mem)
        assert len(entries) == 1
        assert entries[0]["results"]["roas"] == 2.1

    def test_mixed_update_and_append(self, tmp_path):
        mem = _make_mem(tmp_path)
        self._seed(mem, "vs_001")
        self._seed(mem, "vs_002")

        perf = pd.DataFrame(
            [
                {"variant_set_id": "vs_001", "roas": 3.8},
                {"variant_set_id": "vs_UNKNOWN", "roas": 1.9},
            ]
        )
        updated, appended = ingest_performance(mem, perf)

        assert updated == 1
        assert appended == 1
        entries = load_memory(mem)
        assert len(entries) == 3

    def test_results_overwrite_on_second_ingest(self, tmp_path):
        mem = _make_mem(tmp_path)
        self._seed(mem, "vs_001")

        perf1 = pd.DataFrame([{"variant_set_id": "vs_001", "roas": 2.0}])
        ingest_performance(mem, perf1)

        perf2 = pd.DataFrame([{"variant_set_id": "vs_001", "roas": 5.0}])
        ingest_performance(mem, perf2)

        entries = load_memory(mem)
        # Still only one original entry — both ingests updated the SAME entry
        assert entries[0]["results"]["roas"] == 5.0

    def test_metadata_fields_updated(self, tmp_path):
        mem = _make_mem(tmp_path)
        self._seed(mem, "vs_001", campaign="OldCampaign")

        perf = pd.DataFrame(
            [
                {
                    "variant_set_id": "vs_001",
                    "campaign": "NewCampaign",
                    "angle": "urgency",
                    "roas": 3.0,
                }
            ]
        )
        ingest_performance(mem, perf)

        entries = load_memory(mem)
        assert entries[0]["campaign"] == "NewCampaign"
        assert entries[0]["angle"] == "urgency"

    def test_nan_values_skipped(self, tmp_path):
        """NaN values in the CSV should not appear in results."""
        mem = _make_mem(tmp_path)
        self._seed(mem, "vs_001")

        perf = pd.DataFrame(
            [
                {
                    "variant_set_id": "vs_001",
                    "roas": float("nan"),
                    "ctr": 0.02,
                }
            ]
        )
        ingest_performance(mem, perf)

        entries = load_memory(mem)
        r = entries[0]["results"]
        assert "roas" not in r
        assert r["ctr"] == 0.02

    def test_file_rewritten_not_appended_only(self, tmp_path):
        """After ingest, the file should only contain updated+original entries."""
        mem = _make_mem(tmp_path)
        self._seed(mem, "vs_001")

        perf = pd.DataFrame([{"variant_set_id": "vs_001", "roas": 3.0}])
        ingest_performance(mem, perf)

        lines = [
            line
            for line in mem.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 1  # One entry, rewritten in place

    def test_all_metrics_stored(self, tmp_path):
        mem = _make_mem(tmp_path)

        perf = pd.DataFrame(
            [
                {
                    "variant_set_id": "vs_001",
                    "ctr": 0.025,
                    "cpa": 42.0,
                    "roas": 3.8,
                    "impr": 12500,
                    "clicks": 312,
                    "conv": 8,
                }
            ]
        )
        ingest_performance(mem, perf)

        entries = load_memory(mem)
        r = entries[0]["results"]
        assert r["ctr"] == 0.025
        assert r["cpa"] == 42.0
        assert r["roas"] == 3.8
        assert r["impr"] == 12500.0
        assert r["clicks"] == 312.0
        assert r["conv"] == 8.0


# ─────────────────────────────────────────────────────────────────────────────
# TestGetTopAngles — analytics helper
# ─────────────────────────────────────────────────────────────────────────────


def _make_entries_with_results(*angle_roas_pairs):
    """Return a list of normalised entries with results pre-set."""
    entries = []
    for angle, roas in angle_roas_pairs:
        entries.append(
            {
                "angle": angle,
                "campaign": "C",
                "results": {"roas": roas, "cpa": 100.0 / roas, "ctr": roas / 100.0},
                "generated": {"headlines": [], "descriptions": []},
            }
        )
    return entries


class TestGetTopAngles:
    def test_empty_entries_returns_empty_df(self):
        df = get_top_angles([])
        assert len(df) == 0
        assert "angle" in df.columns

    def test_no_results_returns_empty_df(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": [], "descriptions": []},
        )
        entries = load_memory(mem)
        df = get_top_angles(entries)
        assert len(df) == 0

    def test_sorted_by_roas_descending(self):
        entries = _make_entries_with_results(
            ("urgency", 5.0), ("value_prop", 3.0), ("social_proof", 4.0)
        )
        df = get_top_angles(entries, metric="roas")
        assert df.iloc[0]["angle"] == "urgency"
        assert df.iloc[1]["angle"] == "social_proof"

    def test_sorted_by_cpa_ascending(self):
        entries = _make_entries_with_results(
            ("urgency", 5.0),  # cpa = 20
            ("social_proof", 2.0),  # cpa = 50
        )
        df = get_top_angles(entries, metric="cpa", ascending=True)
        assert df.iloc[0]["angle"] == "urgency"  # lowest cpa first

    def test_top_n_limit(self):
        entries = _make_entries_with_results(
            *[(f"angle_{i}", float(i)) for i in range(1, 11)]
        )
        df = get_top_angles(entries, metric="roas", n=3)
        assert len(df) == 3

    def test_grouping_averages_same_angle(self):
        entries = _make_entries_with_results(
            ("urgency", 4.0), ("urgency", 6.0), ("other", 3.0)
        )
        df = get_top_angles(entries, metric="roas")
        urgency_row = df[df["angle"] == "urgency"].iloc[0]
        assert urgency_row["count"] == 2
        assert abs(urgency_row["mean_roas"] - 5.0) < 0.001

    def test_no_angle_falls_back_to_label(self):
        entries = [
            {
                "angle": "",
                "campaign": "C",
                "results": {"roas": 3.0},
                "generated": {"headlines": [], "descriptions": []},
            },
        ]
        df = get_top_angles(entries, metric="roas")
        assert df.iloc[0]["angle"] == "(no angle)"

    def test_best_column_is_max_for_roas(self):
        entries = _make_entries_with_results(("urgency", 3.0), ("urgency", 7.0))
        df = get_top_angles(entries, metric="roas")
        assert df.iloc[0]["best_roas"] == 7.0

    def test_best_column_is_min_for_cpa(self):
        entries = _make_entries_with_results(
            ("urgency", 5.0),  # cpa = 20
            ("urgency", 2.0),  # cpa = 50
        )
        df = get_top_angles(entries, metric="cpa", ascending=True)
        assert df.iloc[0]["best_cpa"] == 20.0


# ─────────────────────────────────────────────────────────────────────────────
# TestGetRecentExperiments — analytics helper
# ─────────────────────────────────────────────────────────────────────────────


class TestGetRecentExperiments:
    def test_empty_returns_empty_df(self):
        df = get_recent_experiments([])
        assert len(df) == 0

    def test_newest_first_ordering(self, tmp_path):
        mem = _make_mem(tmp_path)
        for i in range(3):
            append_entry(
                mem,
                campaign=f"C{i}",
                hypothesis="H",
                variant_set_id=f"vs_{i:03d}",
                generated={"headlines": [], "descriptions": []},
            )
        entries = load_memory(mem)
        df = get_recent_experiments(entries)
        # Most recent entry (vs_002) should appear first
        assert df.iloc[0]["variant_set_id"] == "vs_002"

    def test_n_limit_respected(self, tmp_path):
        mem = _make_mem(tmp_path)
        for i in range(25):
            append_entry(
                mem,
                campaign="C",
                hypothesis="H",
                variant_set_id=f"vs_{i:03d}",
                generated={"headlines": [], "descriptions": []},
            )
        entries = load_memory(mem)
        df = get_recent_experiments(entries, n=5)
        assert len(df) == 5

    def test_has_results_shows_checkmark(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": ["H"], "descriptions": []},
            results={"roas": 4.0},
        )
        entries = load_memory(mem)
        df = get_recent_experiments(entries)
        assert df.iloc[0]["results"] == "✅"

    def test_no_results_shows_dash(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": [], "descriptions": []},
        )
        entries = load_memory(mem)
        df = get_recent_experiments(entries)
        assert df.iloc[0]["results"] == "—"

    def test_headline_count_correct(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": ["A", "B", "C"], "descriptions": ["D1", "D2"]},
        )
        entries = load_memory(mem)
        df = get_recent_experiments(entries)
        assert df.iloc[0]["headlines#"] == 3
        assert df.iloc[0]["descs#"] == 2

    def test_roas_ctr_cpa_populated_when_results_present(self, tmp_path):
        mem = _make_mem(tmp_path)
        append_entry(
            mem,
            campaign="C",
            hypothesis="H",
            variant_set_id="vs_001",
            generated={"headlines": [], "descriptions": []},
            results={"roas": 3.5, "ctr": 0.022, "cpa": 45.0},
        )
        entries = load_memory(mem)
        df = get_recent_experiments(entries)
        assert df.iloc[0]["roas"] == 3.5
        assert df.iloc[0]["ctr"] == 0.022
        assert df.iloc[0]["cpa"] == 45.0
