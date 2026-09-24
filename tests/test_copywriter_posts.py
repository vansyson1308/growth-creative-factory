"""Tests for the offline copywriter, the brief→posts generator and MockProvider."""

from __future__ import annotations

import json
import re

import pytest

from gcf.config import AppConfig
from gcf.copywriter import (
    Brief,
    extract_product,
    write_descriptions,
    write_headlines,
    write_posts,
)
from gcf.dedupe import detect_angle_bucket
from gcf.posts import generate_posts
from gcf.providers.mock_provider import MockProvider, _detect_prompt_type
from gcf.validator import validate_description, validate_headline

POLICY = AppConfig().policy


class TestExtractProduct:
    @pytest.mark.parametrize(
        "src,expected",
        [
            ("Spring Shoes Offer", "Spring Shoes"),
            ("Weekend Sneaker Deals", "Weekend Sneaker"),
            ("SYNTH_Spring", "Spring"),
            ("Holiday Snack Box", "Holiday Snack Box"),
            ("Giày chạy bộ khuyến mãi", "Giày chạy bộ"),
        ],
    )
    def test_extract(self, src, expected):
        assert extract_product(src) == expected

    def test_falls_through_empty_sources(self):
        assert extract_product("", "Sale!", "Travel Pack") == "Travel Pack"


class TestAdCopy:
    @pytest.mark.parametrize(
        "product,lang", [("spring shoes", "en"), ("giày chạy bộ", "vi")]
    )
    def test_headlines_valid_diverse_and_on_topic(self, product, lang):
        heads = write_headlines(product, n=10, max_chars=30, language=lang, seed=3)
        assert len(heads) == 10
        assert len({h.lower() for h in heads}) == 10
        for h in heads:
            assert validate_headline(h, 30, POLICY)["valid"], h
        angles = {detect_angle_bucket(h) for h in heads}
        assert len(angles) == 5  # every creative angle represented
        assert (
            sum(product.split()[-1 if lang == "en" else 0] in h.lower() for h in heads)
            >= 5
        )

    def test_long_product_is_shortened_not_overflowing(self):
        heads = write_headlines(
            "Ultra Premium Waterproof Hiking Boots", n=6, max_chars=30
        )
        assert heads and all(len(h) <= 30 for h in heads)

    def test_descriptions_have_cta_and_fit(self):
        for lang, product in (("en", "travel pack"), ("vi", "balo du lịch")):
            descs = write_descriptions(product, n=6, max_chars=90, language=lang)
            assert len(descs) >= 5
            for d in descs:
                assert validate_description(d, 90, POLICY)["valid"], d
                assert d.rstrip().endswith(("!", ".", "?"))

    def test_deterministic_per_seed(self):
        assert write_headlines("bags", seed=1) == write_headlines("bags", seed=1)


class TestPosts:
    def test_offline_posts_use_brief(self):
        brief = Brief(
            product="Cloudstep",
            audience="busy runners",
            offer="30% off launch week",
            benefits=["Featherlight 180g build", "Cushioned for 20km runs"],
            pain="sore feet",
        )
        posts = write_posts(brief, n=7)
        assert len(posts) == 7
        text = " ".join(p.headline + " " + p.description for p in posts)
        assert "Cloudstep" in text and "Featherlight" in text and "sore feet" in text
        assert any(p.badge == "-30%" for p in posts)
        assert {p.angle for p in posts} >= {"benefit", "urgency", "social_proof"}

    def test_no_offer_means_no_badge_and_no_offer_text(self):
        posts = write_posts(Brief(product="Tea"), n=5)
        assert all(not p.badge for p in posts)
        assert all("{O}" not in p.headline for p in posts)

    def test_vietnamese_brief(self):
        posts = write_posts(
            Brief(product="Cà phê Arabica", offer="Giảm 25% tuần này"), n=5
        )
        assert all(p.cta for p in posts)
        assert any("Cà phê Arabica" in p.headline for p in posts)
        assert posts[0].eyebrow and re.search(
            r"[ăâđêôơư]", " ".join(p.cta for p in posts).lower()
        )

    def test_generate_posts_via_mock_provider(self):
        posts = generate_posts(
            Brief(product="Lumen desk lamp", offer="Buy 1 get 1"), MockProvider(), n=4
        )
        assert len(posts) == 4
        assert any(p.badge == "1+1" for p in posts)

    def test_generate_posts_backfills_bad_llm_output(self):
        class BadProvider:
            def generate(self, prompt, system="", max_tokens=0):
                return json.dumps(
                    {
                        "posts": [
                            {
                                "headline": "The BEST lamp, guaranteed",
                                "description": "x",
                            },
                            {"headline": "OK lamp", "description": "Fine."},
                            {"headline": "OK lamp", "description": "Duplicate."},
                            "not a dict",
                        ]
                    }
                )

        posts = generate_posts(Brief(product="Lamp"), BadProvider(), n=5)
        assert len(posts) == 5
        assert posts[0].headline == "OK lamp"
        assert all("best" not in p.headline.lower() for p in posts)

    def test_generate_posts_handles_garbage(self):
        class Garbage:
            def generate(self, prompt, system="", max_tokens=0):
                return "sorry, no json here"

        assert len(generate_posts(Brief(product="Mug"), Garbage(), n=3)) == 3


class TestMockProvider:
    def test_prompt_type_posts(self):
        assert (
            _detect_prompt_type("You are a SOCIAL POST WRITER for brands.\nTASK: x")
            == "posts"
        )

    def test_headline_prompt_is_on_topic(self):
        prompt = (
            "You are a senior direct-response copywriter.\n\n"
            "TASK: Generate exactly 4 headline variations for the ad below.\n\n"
            "ORIGINAL AD:\n- Campaign: SYNTH_Spring / Group_A\n"
            "- Current headline: Spring Shoes Offer\n"
            "1. Each headline MUST be <= 30 characters including spaces."
        )
        data = json.loads(MockProvider().generate(prompt))
        assert len(data["headlines"]) == 4
        assert all(len(h) <= 30 for h in data["headlines"])
        assert any("shoes" in h.lower() for h in data["headlines"])

    def test_strategy_mentions_metric(self):
        prompt = (
            "You are an expert performance marketing analyst.\n"
            "Analyse the single underperforming ad below and return a root-cause analysis\n"
            "- AD ID: AD9\n- Current headline: Travel Pack Promo\n"
            "Issues detected: ROAS 0.40 < 2.0"
        )
        data = json.loads(MockProvider().generate(prompt))
        assert data["ad_id"] == "AD9"
        assert "revenue" in data["analysis"].lower()
