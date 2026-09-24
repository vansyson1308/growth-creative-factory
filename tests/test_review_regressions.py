"""Regression tests for issues found in the independent review of v0.2.0."""

from __future__ import annotations

import json
import re
import tracemalloc

import pytest
from click.testing import CliRunner
from PIL import Image

from gcf.cli import cli
from gcf.config import RenderConfig
from gcf.copywriter import ANGLES, Brief, write_posts
from gcf.creative import FORMATS, Creative, render_batch, render_creative
from gcf.creative.engine import assign_templates
from gcf.creative.gallery import html_gallery
from gcf.posts import generate_posts
from gcf.providers.mock_provider import MockProvider
from gcf.studio import creatives_from_file, render_outputs


def test_single_column_csv_is_not_split_on_letters(tmp_path):
    p = tmp_path / "one.csv"
    p.write_text("headline\nSpring sale\nSummer shoes\n", encoding="utf-8")
    cs = creatives_from_file(p)
    assert [c.headline for c in cs] == ["Spring sale", "Summer shoes"]


def test_semicolon_csv_is_supported(tmp_path):
    p = tmp_path / "semi.csv"
    p.write_text("headline;description\nHello, world;Body, text\n", encoding="utf-8")
    cs = creatives_from_file(p)
    assert cs[0].headline == "Hello, world" and cs[0].description == "Body, text"


def test_unknown_row_template_falls_back_instead_of_crashing(tmp_path):
    cs = [Creative("A", template="fancy"), Creative("B", template="glass")]
    assert assign_templates(cs)[1] == "glass"
    assert assign_templates(cs)[0] in {
        "bold",
        "editorial",
        "split",
        "glass",
        "promo",
        "photo",
    }
    items = render_batch(cs, tmp_path, formats="square", workers=1)
    assert len(items) == 2


def test_mock_brief_without_product_does_not_crash():
    posts = generate_posts(Brief(product="", audience="runners"), MockProvider(), n=3)
    assert len(posts) == 3


@pytest.mark.parametrize("product", ["Best Buy headphones", "100% cotton tee"])
def test_generate_posts_returns_n_even_when_brief_trips_policy(product):
    posts = generate_posts(Brief(product=product, offer="20% off"), MockProvider(), n=6)
    assert len(posts) == 6


def test_write_posts_with_empty_angles():
    assert len(write_posts(Brief(product="Tea"), n=3, angles=[])) == 3


def test_gallery_placeholders_cannot_inject_html(tmp_path):
    items = render_batch(
        [Creative("<img src=x onerror=alert(1)>", description="<!--<script>", tag="x")],
        tmp_path / "c",
        formats="square",
        workers=1,
    )
    html = html_gallery(
        items, tmp_path / "g.html", title="Promo __SUBTITLE__", subtitle="__DATA__"
    ).read_text(encoding="utf-8")
    head, body = html.split("<script>", 1)
    assert "<img src=x" not in head and "onerror" not in head
    assert "Promo __SUBTITLE__" in head  # placeholder text shown literally
    script = body.split("</script>", 1)[0]
    assert "<" not in script.split("const DATA=", 1)[1].split(";", 1)[0]
    data = json.loads(re.search(r"const DATA=(\[.*?\]);", html, re.S).group(1))
    assert data[0]["headline"] == "<img src=x onerror=alert(1)>"


def test_sphere_cache_memory_is_bounded():
    from gcf.creative import draw as D

    D._sphere_master.cache_clear()
    tracemalloc.start()
    for i in range(40):
        D._sphere(1800 + i, (10 * i % 255, 80, 200))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    info = D._sphere_master.cache_info()
    assert info.currsize <= 24
    assert peak < 200 * 1024 * 1024
    img = D._sphere(1800, (0, 80, 200))
    img.putpixel((0, 0), (1, 2, 3, 4))  # callers may mutate: must not poison the cache
    assert D._sphere(1800, (0, 80, 200)).getpixel((0, 0)) != (1, 2, 3, 4)


@pytest.mark.parametrize("fmt", ["landscape", "square", "story"])
def test_long_cta_and_eyebrow_are_bounded(fmt):
    from gcf.creative.brand import load_brand
    from gcf.creative.components import Ctx, cta_button, cta_link, pill
    from gcf.creative.formats import get_format

    long = "Click here to read absolutely everything about this amazing product line"
    ctx = Ctx(Creative("x", cta=long), get_format(fmt), load_brand("aurora"), ss=1)
    limit = 300 * ctx.u
    for box in (
        cta_button(ctx, (10, 10), 27, (0, 0, 0), max_width=limit),
        cta_link(ctx, (10, 10), 27, (0, 0, 0), max_width=limit),
        pill(
            ctx,
            long.upper(),
            (10, 10),
            22,
            (0, 0, 0, 255),
            (255, 255, 255),
            max_width=limit,
        ),
    ):
        assert box[2] - box[0] <= limit + 1
    # Without an explicit limit, labels are bounded by the safe area.
    box = cta_button(ctx, (ctx.safe[0], 10), 27, (0, 0, 0))
    assert box[2] <= ctx.safe[2] + 1


@pytest.mark.parametrize(
    "template", ["split", "bold", "editorial", "glass", "promo", "photo"]
)
def test_long_labels_render_in_every_template(template):
    c = Creative(
        headline="Short headline",
        cta="Click here to read absolutely everything about this amazing product line",
        eyebrow="An extremely long eyebrow label that keeps going and going forever",
    )
    img = render_creative(c, template, "landscape", "aurora", supersample=1)
    assert img.size == FORMATS["landscape"].size


def test_rerender_clears_previous_images(tmp_path):
    rc = RenderConfig(enabled=True, formats=["story"], workers=1)
    render_outputs([Creative("A", tag="a"), Creative("B", tag="b")], tmp_path, rc)
    rc2 = RenderConfig(enabled=True, formats=["square"], workers=1)
    rs = render_outputs([Creative("C", tag="c")], tmp_path, rc2)
    files = sorted(p.name for p in (tmp_path / "creatives").rglob("*.png"))
    assert rs.count == 1 and len(files) == 1
    assert not (tmp_path / "creatives" / "story").exists()


def test_rerender_keeps_foreign_files(tmp_path):
    rc = RenderConfig(enabled=True, formats=["square"], workers=1)
    render_outputs([Creative("A", tag="a")], tmp_path, rc)
    keep = tmp_path / "creatives" / "square" / "notes.txt"
    keep.write_text("mine", encoding="utf-8")
    render_outputs([Creative("B", tag="b")], tmp_path, rc)
    assert keep.read_text(encoding="utf-8") == "mine"


def test_templates_accept_comma_string(tmp_path):
    rc = RenderConfig(enabled=True, formats="square", templates="bold,glass", workers=1)
    rs = render_outputs([Creative("A"), Creative("B"), Creative("C")], tmp_path, rc)
    assert [i.template for i in rs.items] == ["bold", "glass", "bold"]


def test_case_insensitive_file_names(tmp_path):
    items = render_batch(
        [
            Creative("A", tag="Promo", template="bold"),
            Creative("B", tag="promo", template="bold"),
        ],
        tmp_path,
        formats="square",
        workers=1,
    )
    names = [p.lower() for p in (i.path for i in items)]
    assert len(set(names)) == 2


def test_relative_image_paths_resolve_against_sheet_and_uploads_are_blocked(tmp_path):
    (tmp_path / "img").mkdir()
    Image.new("RGB", (40, 40), (255, 0, 0)).save(tmp_path / "img" / "p.png")
    sheet = tmp_path / "s.csv"
    sheet.write_text("headline,image\nHi,img/p.png\n", encoding="utf-8")
    assert creatives_from_file(sheet)[0].image == str(
        (tmp_path / "img" / "p.png").resolve()
    )
    assert creatives_from_file(sheet, allow_images=False)[0].image is None


def test_cli_rejects_empty_product(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(cli, ["create", "--product", "  "])
    assert res.exit_code != 0 and "--product" in res.output


def test_angles_constant_is_intact():
    assert ANGLES == [
        "benefit",
        "urgency",
        "social_proof",
        "problem_solution",
        "curiosity",
    ]
