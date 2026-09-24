"""Tests for studio glue, pipeline rendering, config validation and the CLI."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pandas as pd
import pytest
from click.testing import CliRunner
from PIL import Image

from gcf.cli import cli
from gcf.config import AppConfig, RenderConfig, load_config
from gcf.pipeline import _combine, run_pipeline
from gcf.providers.mock_provider import MockProvider
from gcf.studio import build_showcase, creatives_from_file, creatives_from_variants

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "ads_sample.csv"


def _cfg(tmp_path) -> AppConfig:
    cfg = load_config(ROOT / "config.yaml")
    cfg.memory.path = str(tmp_path / "memory.jsonl")
    cfg.cache.path = str(tmp_path / "cache.db")
    cfg.render = RenderConfig(
        enabled=True, formats=["square"], max_creatives=4, workers=2, executor="thread"
    )
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────


class TestPipelineVariants:
    def test_combine_prefix_covers_all_headlines(self):
        combos = _combine(["h1", "h2", "h3"], ["d1", "d2"], cap=3)
        assert [h for h, _ in combos] == ["h1", "h2", "h3"]
        assert len(_combine(["h1", "h2"], ["d1", "d2"], cap=99)) == 4
        assert _combine([], ["d"], 5) == []

    def test_tags_unique_and_run_cap_respected(self, tmp_path):
        cfg = _cfg(tmp_path)
        cfg.generation.max_variants_per_run = 20
        out = tmp_path / "out"
        summary = run_pipeline(SAMPLE, out, cfg, MockProvider(), "dry", render=False)
        rows = list(csv.DictReader(open(out / "new_ads.csv", encoding="utf-8")))
        assert summary["variants_generated"] == len(rows) <= 20
        tags = [r["tag"] for r in rows]
        assert len(tags) == len(set(tags)), "tags must be unique across ads"
        assert {r["ad_id"] for r in rows} == {f"AD00{i}" for i in range(1, 9)}
        assert not (tmp_path / "cache.db").exists(), "dry runs must not use the cache"

    def test_render_step_creates_images_and_gallery(self, tmp_path):
        cfg = _cfg(tmp_path)
        out = tmp_path / "out"
        summary = run_pipeline(SAMPLE, out, cfg, MockProvider(), "dry")
        assert summary["creatives_rendered"] == 4
        pngs = sorted((out / "creatives" / "square").glob("*.png"))
        assert len(pngs) == 4
        assert (out / "gallery.html").exists()
        assert (out / "contact_sheet.png").exists()
        assert "Creative images rendered: 4" in (out / "report.md").read_text(
            encoding="utf-8"
        )
        # round-robin: the 4 rendered variants come from 4 different ads
        manifest = list(
            csv.DictReader(open(out / "creatives" / "manifest.csv", encoding="utf-8"))
        )
        assert len({m["tag"].split("-V")[0] for m in manifest}) == 4


class TestStudio:
    def test_creatives_from_variants_round_robin(self):
        rows = [
            {
                "ad_id": a,
                "variant_headline": f"{a} h{i}",
                "variant_description": "d",
                "tag": f"{a}-{i}",
            }
            for a in ("A", "B")
            for i in range(3)
        ]
        cs = creatives_from_variants(rows, limit=3)
        assert [c.tag for c in cs] == ["A-0", "B-0", "A-1"]
        assert all(c.eyebrow for c in cs)

    def test_creatives_from_figma_tsv_with_bom(self, tmp_path):
        p = tmp_path / "v.tsv"
        p.write_text("﻿H1\tDESC\tTAG\nHello\tWorld\tV1\n\t\tempty\n", encoding="utf-8")
        cs = creatives_from_file(p)
        assert len(cs) == 1 and cs[0].headline == "Hello" and cs[0].tag == "V1"

    def test_creatives_from_file_requires_headline(self, tmp_path):
        p = tmp_path / "x.csv"
        p.write_text("foo,bar\n1,2\n", encoding="utf-8")
        with pytest.raises(ValueError):
            creatives_from_file(p)

    def test_showcase(self, tmp_path):
        written = build_showcase(tmp_path, formats=["square"])
        assert len(written) == 6
        for path in written.values():
            with Image.open(path) as im:
                assert im.size == (1080, 1080)


class TestConfig:
    def test_unknown_key_is_rejected(self, tmp_path):
        p = tmp_path / "c.yaml"
        p.write_text("render:\n  formatz: [square]\n", encoding="utf-8")
        with pytest.raises(ValueError, match="formatz"):
            load_config(p)

    def test_shipped_config_loads(self):
        cfg = load_config(ROOT / "config.yaml")
        assert cfg.render.enabled is True
        assert cfg.provider.temperature is None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        (ROOT / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


class TestCLI:
    def test_listing_commands(self):
        r = CliRunner()
        for cmd, needle in (
            ("templates", "editorial"),
            ("formats", "1080×1920"),
            ("brands", "noir"),
        ):
            res = r.invoke(cli, [cmd])
            assert res.exit_code == 0, res.output
            assert needle in res.output

    def test_run_dry_with_render(self, in_tmp):
        res = CliRunner().invoke(
            cli,
            [
                "run",
                "--input",
                str(SAMPLE),
                "--out",
                "out",
                "--mode",
                "dry",
                "--formats",
                "square",
                "--max-creatives",
                "2",
                "--brand",
                "tide",
            ],
        )
        assert res.exit_code == 0, res.output
        assert "Images rendered: 2" in res.output
        assert len(list((in_tmp / "out" / "creatives" / "square").glob("*.png"))) == 2

    def test_run_no_render(self, in_tmp):
        res = CliRunner().invoke(
            cli, ["run", "--input", str(SAMPLE), "--out", "out", "--no-render"]
        )
        assert res.exit_code == 0, res.output
        assert not (in_tmp / "out" / "creatives").exists()

    def test_run_missing_input_is_friendly(self, in_tmp):
        res = CliRunner().invoke(cli, ["run", "--input", "nope.csv", "--no-render"])
        assert res.exit_code != 0
        assert "not found" in res.output.lower()

    def test_bad_options_are_friendly(self, in_tmp):
        r = CliRunner()
        res = r.invoke(cli, ["run", "--input", str(SAMPLE), "--formats", "billboard"])
        assert res.exit_code != 0 and "billboard" in res.output
        res = r.invoke(cli, ["run", "--input", str(SAMPLE), "--templates", "fancy"])
        assert res.exit_code != 0 and "fancy" in res.output
        res = r.invoke(cli, ["run", "--input", str(SAMPLE), "--brand", "nobrand"])
        assert res.exit_code != 0 and "nobrand" in res.output

    def test_create_and_render_commands(self, in_tmp):
        r = CliRunner()
        res = r.invoke(
            cli,
            [
                "create",
                "--product",
                "Lumen lamp",
                "--offer",
                "20% off",
                "--benefit",
                "Warm light",
                "--n",
                "2",
                "--formats",
                "square",
                "--out",
                "studio",
            ],
        )
        assert res.exit_code == 0, res.output
        posts = pd.read_csv(in_tmp / "studio" / "posts.csv")
        assert len(posts) == 2
        assert (in_tmp / "studio" / "gallery.html").exists()

        res = r.invoke(
            cli,
            [
                "render",
                "--input",
                "studio/posts.csv",
                "--formats",
                "story",
                "--out",
                "re",
                "--limit",
                "1",
            ],
        )
        assert res.exit_code == 0, res.output
        assert len(list((in_tmp / "re" / "creatives" / "story").glob("*.png"))) == 1

    def test_live_without_key_suggests_dry(self, in_tmp, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setattr(
            "gcf.providers.anthropic_provider.load_dotenv", lambda *a, **k: False
        )
        res = CliRunner().invoke(cli, ["create", "--product", "X", "--mode", "live"])
        assert res.exit_code != 0
        assert "--mode dry" in res.output


def test_app_module_imports():
    """The Streamlit app must at least import cleanly (no NameErrors at import)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gcf_app", ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
    assert callable(module.main) and callable(module.studio_tab)


def test_budget_exhaustion_keeps_partial_results(tmp_path):
    from gcf.providers.base import BudgetExceededError

    class Budgeted(MockProvider):
        def __init__(self, limit):
            super().__init__()
            self.limit = limit

        def generate(self, prompt, system="", max_tokens=2048):
            if len(self._call_log) >= self.limit:
                raise BudgetExceededError(f"max_calls_per_run={self.limit} reached")
            return super().generate(prompt, system, max_tokens)

    cfg = _cfg(tmp_path)
    out = tmp_path / "out"
    summary = run_pipeline(SAMPLE, out, cfg, Budgeted(9), "dry", render=False)
    # 4 calls per ad in dry mode → 2 full ads fit in a budget of 9
    assert summary["stopped_reason"].startswith("Stopped after 2 of 8 ads")
    rows = list(csv.DictReader(open(out / "new_ads.csv", encoding="utf-8")))
    assert {r["ad_id"] for r in rows} == {"AD001", "AD002"}
    assert "call budget reached" in (out / "report.md").read_text(encoding="utf-8")


def test_demo_header_wraps_long_commands():
    from gcf.demo import _command_lines, header_height

    long = "gcf create " + " ".join(
        f'--benefit "Benefit number {i}"' for i in range(12)
    )
    lines = _command_lines(2400, long)
    assert len(lines) > 1 and lines[0].startswith("$ gcf create")
    assert header_height(2400, long) > header_height(2400, "gcf demo")
