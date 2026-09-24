"""Tests for the creative rendering engine (gcf.creative)."""

from __future__ import annotations

import csv

import numpy as np
import pytest
from PIL import Image

from gcf.creative import (
    FORMATS,
    PRESETS,
    TEMPLATE_ORDER,
    BrandKit,
    Creative,
    detect_language,
    extract_badge,
    load_brand,
    parse_formats,
    render_batch,
    render_creative,
)
from gcf.creative.color import contrast_ratio, hex_to_rgb, readable_on
from gcf.creative.fonts import font_path, load_font
from gcf.creative.gallery import contact_sheet, html_gallery
from gcf.creative.text import clean_text, fit_text, splits_words, wrap_balanced

# ─────────────────────────────────────────────────────────────────────────────
# Colour
# ─────────────────────────────────────────────────────────────────────────────


class TestColor:
    def test_hex_parsing(self):
        assert hex_to_rgb("#fff") == (255, 255, 255)
        assert hex_to_rgb("5B5BF7") == (91, 91, 247)

    def test_bad_hex_raises(self):
        with pytest.raises(ValueError):
            hex_to_rgb("#12")
        with pytest.raises(ValueError):
            hex_to_rgb("#GGGGGG")

    def test_readable_on_picks_contrast(self):
        assert readable_on((0, 0, 0)) == (255, 255, 255)
        assert readable_on((255, 255, 255)) != (255, 255, 255)
        assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21, rel=1e-3)


# ─────────────────────────────────────────────────────────────────────────────
# Formats & brands
# ─────────────────────────────────────────────────────────────────────────────


class TestFormatsAndBrands:
    def test_parse_formats(self):
        assert parse_formats("square, story") == ["square", "story"]
        assert parse_formats("all") == list(FORMATS)
        assert parse_formats(None) == ["square", "portrait", "story"]
        with pytest.raises(KeyError):
            parse_formats("billboard")

    def test_presets_are_valid(self):
        for kit in PRESETS.values():
            kit.validate()

    def test_load_brand_variants(self, tmp_path):
        assert load_brand(None).name == PRESETS["aurora"].name
        assert load_brand("SUNSET").name == "Sunset Supply"
        kit = load_brand({"preset": "noir", "name": "Acme"})
        assert kit.name == "Acme" and kit.accent == PRESETS["noir"].accent
        y = tmp_path / "brand.yaml"
        y.write_text(
            "name: Yaml Co\nprimary: '#112233'\nlogo: logo.png\n", encoding="utf-8"
        )
        kit = load_brand(str(y))
        assert kit.name == "Yaml Co"
        assert kit.primary == "#112233"
        assert kit.logo.endswith("logo.png")  # resolved relative to the YAML

    def test_load_brand_errors(self, tmp_path):
        with pytest.raises(ValueError):
            load_brand("does-not-exist")
        with pytest.raises(ValueError):
            load_brand({"primary": "not-a-colour"})

    def test_overrides(self):
        kit = load_brand("aurora", overrides={"name": "Override", "cta": ""})
        assert kit.name == "Override"


# ─────────────────────────────────────────────────────────────────────────────
# Copy model helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestModel:
    def test_language(self):
        assert detect_language("Giày chạy bộ") == "vi"
        assert detect_language("Running shoes") == "en"

    @pytest.mark.parametrize(
        "text,badge",
        [
            ("Save 30% today", "-30%"),
            ("Giảm 25% tuần này", "-25%"),
            ("Mua 1 tặng 1", "1+1"),
            ("Free shipping on all orders", "FREE SHIP"),
            ("Miễn phí vận chuyển", "FREESHIP"),
            ("Up to 100% organic", ""),  # not a discount, and out of range
            ("Plain copy", ""),
        ],
    )
    def test_extract_badge(self, text, badge):
        assert extract_badge(text) == badge

    def test_from_row_aliases(self):
        c = Creative.from_row(
            {"H1": "Hello", "DESC": "World", "TAG": "V1", "extra": "x"}
        )
        assert (c.headline, c.description, c.tag) == ("Hello", "World", "V1")
        c = Creative.from_row(
            {"headline": " A ", "primary_text": "B", "cta": "Go", "badge": float("nan")}
        )
        assert (c.headline, c.description, c.cta, c.badge) == ("A", "B", "Go", "")

    def test_cta_defaults_follow_language(self):
        assert Creative("Giày mới").resolved_cta() == "Mua ngay"
        assert Creative("New shoes").resolved_cta() == "Shop now"
        assert Creative("New shoes").resolved_cta("Book now") == "Book now"

    def test_seed_is_stable(self):
        assert Creative("A", tag="t").seed == Creative("A", tag="t").seed
        assert Creative("A", tag="t").seed != Creative("B", tag="t").seed


# ─────────────────────────────────────────────────────────────────────────────
# Typography
# ─────────────────────────────────────────────────────────────────────────────


class TestText:
    def test_clean_text(self):
        assert clean_text("  a \n b ") == "a b"
        assert clean_text(None) == ""
        assert clean_text(float("nan")) == ""
        # NFD input is normalised to NFC
        assert clean_text("Việt") == "Việt"

    def test_fit_text_respects_box(self):
        path = font_path("display")
        block = fit_text(
            "Spring sneakers, now 30% off", path, 400, 300, 200, 10, max_lines=4
        )
        assert block.width <= 400.5
        assert block.height <= 300
        assert len(block.lines) <= 4
        assert not splits_words("Spring sneakers, now 30% off", block.lines)

    def test_fit_text_truncates_instead_of_overflowing(self):
        path = font_path("body")
        long = "word " * 200
        block = fit_text(long, path, 200, 60, 20, 18, max_lines=2)
        assert len(block.lines) <= 2
        assert block.lines[-1].endswith("…")

    def test_balanced_wrap_keeps_line_count(self):
        font = load_font(font_path("display"), 60)
        lines = wrap_balanced("One two three four five six seven", font, 500)
        widths = [font.getlength(line) for line in lines]
        assert max(widths) - min(widths) < 250


def test_bundled_fonts_cover_vietnamese():
    """Every bundled font renders Vietnamese glyphs (no .notdef boxes)."""
    sample = "ẮẰẲẴẶắằẳẵặỆệỘộỰựĐđ"
    for role in ("display", "heading", "body", "serif"):
        font = load_font(font_path(role), 40)
        tofu = font.getmask("￿").getbbox()
        for ch in sample:
            assert font.getmask(ch).getbbox() != tofu, (role, ch)


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────


def _not_blank(img: Image.Image) -> bool:
    arr = np.asarray(img.convert("L"), dtype=np.float32)
    return float(arr.std()) > 8.0


@pytest.mark.parametrize("template", TEMPLATE_ORDER)
@pytest.mark.parametrize("fmt", list(FORMATS))
def test_every_template_renders_every_format(template, fmt):
    c = Creative(
        headline="Giày chạy bộ êm như mây, giảm 30%",
        description="Đệm khí thế hệ mới, nhẹ hơn 20%. Giao nhanh 2h nội thành.",
        eyebrow="Bộ sưu tập mới",
        tag="T1",
    )
    img = render_creative(c, template, fmt, "sunset", supersample=1)
    assert img.size == FORMATS[fmt].size
    assert img.mode == "RGB"
    assert _not_blank(img)


def test_render_is_deterministic():
    c = Creative(
        headline="Deterministic output", description="Same in, same out.", tag="D"
    )
    a = np.asarray(render_creative(c, "glass", "square", supersample=1))
    b = np.asarray(render_creative(c, "glass", "square", supersample=1))
    assert np.array_equal(a, b)


def test_render_handles_extreme_copy():
    c = Creative(headline="A" * 300, description="word " * 120, cta="Go", tag="X")
    for tpl in TEMPLATE_ORDER:
        img = render_creative(c, tpl, "landscape", supersample=1)
        assert img.size == FORMATS["landscape"].size


def test_render_with_product_photo_and_logo(tmp_path):
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (800, 600), (200, 120, 80)).save(photo)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (300, 100), (255, 255, 255, 255)).save(logo)
    kit = BrandKit(name="Photo Co", logo=str(logo))
    c = Creative(
        headline="With a real photo", description="Cover-cropped.", image=str(photo)
    )
    for tpl in TEMPLATE_ORDER:
        img = render_creative(c, tpl, "portrait", kit, supersample=1)
        assert img.size == (1080, 1350)


def test_render_batch_writes_files_and_manifest(tmp_path):
    creatives = [
        Creative(headline=f"Headline {i}", description="Body copy.", tag="SAME")
        for i in range(3)
    ]
    items = render_batch(
        creatives,
        tmp_path,
        formats=["square", "story"],
        brand="verde",
        workers=2,
        executor="thread",
    )
    assert len(items) == 6
    paths = {it.path for it in items}
    assert len(paths) == 6  # duplicate tags never overwrite each other
    for it in items:
        with Image.open(it.path) as im:
            assert im.size == FORMATS[it.format].size
    rows = list(csv.DictReader(open(tmp_path / "manifest.csv", encoding="utf-8")))
    assert len(rows) == 6
    assert all(not r["path"].startswith("/") for r in rows)  # relative paths


def test_render_batch_jpg_and_template_override(tmp_path):
    c = Creative(headline="Forced template", template="promo", tag="J")
    items = render_batch([c], tmp_path, formats="square", image_format="jpg", workers=1)
    assert items[0].template == "promo"
    assert items[0].path.endswith(".jpg")


def test_gallery_and_contact_sheet(tmp_path):
    items = render_batch(
        [Creative(headline="<script>alert(1)</script>", tag="G")],
        tmp_path / "c",
        formats=["square", "landscape"],
        workers=1,
    )
    html = html_gallery(items, tmp_path / "gallery.html", title="T & <b>")
    text = html.read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text  # payload is escaped
    assert "T &amp; &lt;b&gt;" in text
    assert "c/square/" in text
    sheet = contact_sheet(
        [it.path for it in items], tmp_path / "sheet.png", title="Sheet"
    )
    with Image.open(sheet) as im:
        assert im.width == 2400
