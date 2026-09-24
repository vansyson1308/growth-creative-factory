"""Reproducible proof set for the README — ``gcf demo``.

Every image is produced here from files in ``examples/`` by the same code
paths the CLI uses (selector → strategist → writers → checker → renderer),
in dry mode, so anyone can regenerate the exact set without an API key:

    gcf demo --out docs/demo

A ``demo.json`` manifest records versions, timings and the equivalent CLI
commands for each image.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd
from PIL import Image, ImageDraw

from gcf import __version__
from gcf.config import AppConfig, load_config
from gcf.copywriter import Brief
from gcf.creative import Creative, load_brand, render_batch, render_creative
from gcf.creative.fonts import font_path, load_font
from gcf.creative.gallery import strip
from gcf.creative.text import wrap_text
from gcf.pipeline import run_pipeline
from gcf.providers.mock_provider import MockProvider
from gcf.studio import creatives_from_posts, creatives_from_variants

ROOT = Path(__file__).resolve().parent.parent


def _find_examples(explicit: Optional[Union[str, Path]] = None) -> Path:
    """examples/ from --examples, the working directory, or a source checkout."""
    for cand in (explicit, Path.cwd() / "examples", ROOT / "examples"):
        if cand and (Path(cand) / "demo_ads.csv").is_file():
            return Path(cand)
    raise FileNotFoundError(
        "examples/demo_ads.csv not found. Run `gcf demo` from a clone of the "
        "repository, or pass --examples path/to/examples."
    )


BG = (14, 14, 20)
PANEL = (26, 26, 36)
MUTED = (160, 160, 180)
WHITE = (245, 245, 250)
RED = (248, 113, 113)
GREEN = (74, 222, 128)

# Ad-id prefix → brand kit used for that fictional advertiser
BRAND_BY_PREFIX = {
    "SS": "sunset",
    "VM": "verde",
    "AL": "aurora",
    "TC": "tide",
    "BB": "blossom",
    "MN": "noir",
}

Progress = Optional[Callable[[str], None]]


def _brand_for(ad_id: str) -> str:
    return BRAND_BY_PREFIX.get(str(ad_id).split("-")[0], "aurora")


def _say(progress: Progress, msg: str) -> None:
    if progress:
        progress(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Drawing helpers for the composite boards
# ─────────────────────────────────────────────────────────────────────────────


def _text(d, xy, text, role, size, fill, max_w=None, spacing=1.3) -> int:
    """Draw (wrapped) text, return the height used."""
    font = load_font(font_path(role), size)
    lines = wrap_text(text, font, max_w) if max_w else [text]
    y = xy[1]
    for line in lines:
        d.text((xy[0], y), line, font=font, fill=fill)
        y += int(size * spacing)
    return y - xy[1]


def _chip(d, xy, text, fg, bg, size=24) -> int:
    font = load_font(font_path("heading"), size)
    w = int(font.getlength(text)) + 28
    h = size + 20
    d.rounded_rectangle((xy[0], xy[1], xy[0] + w, xy[1] + h), radius=h // 2, fill=bg)
    d.text((xy[0] + 14, xy[1] + h / 2), text, font=font, fill=fg, anchor="lm")
    return w


def _command_lines(width: int, command: str) -> List[str]:
    font = load_font(font_path("body"), 26)
    max_w = width - 2 * 64 - 40
    lines: List[str] = []
    cur = "$"
    for part in command.replace(" --", "\n--").split("\n"):
        cand = f"{cur} {part}"
        if font.getlength(cand) <= max_w or cur == "$":
            cur = cand
        else:
            lines.append(cur)
            cur = "    " + part
    lines.append(cur)
    return lines


def header_height(width: int, command: str) -> int:
    return 196 + 26 + 38 * len(_command_lines(width, command)) + 44


def _header(canvas: Image.Image, title: str, subtitle: str, command: str) -> int:
    """Title, subtitle and the exact command (wrapped at ``--`` flags)."""
    d = ImageDraw.Draw(canvas)
    x = 64
    _text(d, (x, 56), title, "display", 60, WHITE)
    _text(d, (x, 140), subtitle, "body", 30, MUTED)
    font = load_font(font_path("body"), 26)
    lines = _command_lines(canvas.width, command)
    h = 26 + 38 * len(lines)
    w = max(int(font.getlength(line)) for line in lines) + 40
    d.rounded_rectangle((x, 196, x + w, 196 + h), radius=10, fill=PANEL)
    for i, line in enumerate(lines):
        d.text(
            (x + 20, 196 + 32 + 38 * i),
            line,
            font=font,
            fill=(134, 239, 172),
            anchor="lm",
        )
    return 196 + h + 44


def _paste_rounded(canvas: Image.Image, img: Image.Image, xy, size, radius=18) -> None:
    thumb = img.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *size), radius=radius, fill=255)
    canvas.paste(thumb, xy, mask)


# ─────────────────────────────────────────────────────────────────────────────
# 01 · Before → after (the full pipeline)
# ─────────────────────────────────────────────────────────────────────────────


def _before_card(
    d: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], ad: Dict, detail: Dict
) -> None:
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=24, fill=PANEL)
    pad = 36
    x = x0 + pad
    y = y0 + pad
    w = x1 - x0 - 2 * pad
    _chip(d, (x, y), f"BEFORE · {ad['ad_id']}", (254, 202, 202), (69, 26, 26), 22)
    y += 66
    # The original ad, drawn like a plain text ad
    d.rounded_rectangle((x, y, x1 - pad, y + 170), radius=14, fill=(245, 245, 247))
    _text(
        d,
        (x + 22, y + 18),
        "Sponsored · " + str(ad["campaign"]),
        "body",
        20,
        (110, 110, 120),
    )
    _text(
        d, (x + 22, y + 50), str(ad["headline"]), "heading", 32, (26, 13, 171), w - 44
    )
    _text(
        d, (x + 22, y + 100), str(ad["description"]), "body", 24, (60, 60, 70), w - 44
    )
    y += 196
    # Metrics that got it flagged
    cx = x
    for label, value, bad in (
        ("CTR", f"{ad['ctr'] * 100:.2f}%", ad["ctr"] < 0.02),
        ("CPA", f"${ad['cpa']:.0f}", ad["cpa"] > 50),
        ("ROAS", f"{ad['roas']:.2f}×", ad["roas"] < 2),
    ):
        cx += (
            _chip(
                d,
                (cx, y),
                f"{label} {value}",
                RED if bad else GREEN,
                (48, 22, 26) if bad else (20, 46, 30),
                22,
            )
            + 10
        )
    y += 68
    _text(d, (x, y), "DIAGNOSIS", "heading", 20, MUTED)
    y += 32
    y += _text(d, (x, y), detail.get("analysis", ""), "body", 24, WHITE, w, 1.35) + 18
    _text(d, (x, y), "STRATEGY", "heading", 20, MUTED)
    y += 32
    _text(d, (x, y), detail.get("strategy", ""), "body", 24, (199, 210, 254), w, 1.35)


def _arrow(d, x, cy):
    d.line((x, cy, x + 70, cy), fill=MUTED, width=6)
    d.polygon([(x + 70, cy - 18), (x + 100, cy), (x + 70, cy + 18)], fill=MUTED)


def before_after_board(
    run_dir: Path, rendered: Dict[str, List[str]], out: Path, ad_ids: Sequence[str]
) -> Path:
    ads = pd.read_csv(run_dir / "input_normalized.csv", dtype={"ad_id": str})
    details = {
        d["ad_id"]: d for d in json.loads((run_dir / "details.json").read_text())
    }
    thumbs = 3
    tw = 470
    row_h = 640
    width = 64 + 900 + 140 + thumbs * tw + (thumbs - 1) * 24 + 64
    cmd = "gcf run --input examples/demo_ads.csv --mode dry"
    top_h = header_height(width, cmd)
    canvas = Image.new("RGB", (width, top_h + len(ad_ids) * (row_h + 40) + 40), BG)
    top = _header(
        canvas,
        "From underperforming ad to new creatives",
        "Real pipeline output on examples/demo_ads.csv — dry mode, no API key. "
        "Diagnosis, strategy, copy and images are all generated.",
        cmd,
    )
    d = ImageDraw.Draw(canvas)
    y = top + 10
    for ad_id in ad_ids:
        ad = ads[ads["ad_id"] == ad_id].iloc[0].to_dict()
        _before_card(d, (64, y, 64 + 900, y + row_h), ad, details.get(ad_id, {}))
        _arrow(d, 64 + 900 + 22, y + row_h // 2)
        x = 64 + 900 + 140
        _chip(
            d,
            (x, y + 36),
            f"AFTER · {len(rendered.get(ad_id, []))} new creatives",
            (187, 247, 208),
            (20, 46, 30),
            22,
        )
        for i, p in enumerate(rendered.get(ad_id, [])[:thumbs]):
            with Image.open(p) as im:
                _paste_rounded(canvas, im, (x + i * (tw + 24), y + 110), (tw, tw))
        y += row_h + 40
    return _save(canvas, out)


# ─────────────────────────────────────────────────────────────────────────────
# 02 · Scale mosaic
# ─────────────────────────────────────────────────────────────────────────────


def scale_mosaic(paths: Sequence[str], out: Path, subtitle: str, command: str) -> Path:
    cols = 12
    tile = 180
    gap = 10
    rows = (len(paths) + cols - 1) // cols
    width = 64 * 2 + cols * tile + (cols - 1) * gap
    canvas = Image.new(
        "RGB", (width, header_height(width, command) + rows * (tile + gap) + 54), BG
    )
    top = _header(canvas, f"{len(paths)} creatives from one run", subtitle, command)
    for i, p in enumerate(paths):
        with Image.open(p) as im:
            _paste_rounded(
                canvas,
                im,
                (64 + (i % cols) * (tile + gap), top + (i // cols) * (tile + gap)),
                (tile, tile),
                radius=10,
            )
    return _save(canvas, out)


# ─────────────────────────────────────────────────────────────────────────────
# Composite with header (brief sheets, brand swap)
# ─────────────────────────────────────────────────────────────────────────────


def headed_grid(
    paths: Sequence[str],
    out: Path,
    title: str,
    subtitle: str,
    command: str,
    cols: int = 3,
    tile: int = 700,
    labels: Optional[Sequence[str]] = None,
) -> Path:
    gap = 28
    ims = []
    for p in paths:
        with Image.open(p) as im:
            ims.append(im.convert("RGB"))
    th = int(tile * ims[0].height / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    label_h = 56 if labels else 0
    width = 64 * 2 + cols * tile + (cols - 1) * gap
    canvas = Image.new(
        "RGB",
        (width, header_height(width, command) + rows * (th + gap + label_h) + 40),
        BG,
    )
    top = _header(canvas, title, subtitle, command)
    d = ImageDraw.Draw(canvas)
    font = load_font(font_path("heading"), 28)
    for i, im in enumerate(ims):
        x = 64 + (i % cols) * (tile + gap)
        y = top + (i // cols) * (th + gap + label_h)
        _paste_rounded(canvas, im, (x, y), (tile, th))
        if labels:
            d.text(
                (x + tile / 2, y + th + 30),
                labels[i],
                font=font,
                fill=MUTED,
                anchor="mm",
            )
    return _save(canvas, out)


def _save(img: Image.Image, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=86, optimize=True, progressive=True)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────


def build_demo(
    out_dir: Union[str, Path],
    progress: Progress = None,
    examples_dir: Optional[Union[str, Path]] = None,
) -> Dict:
    examples = _find_examples(examples_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="gcf-demo-"))
    manifest: Dict = {
        "gcf_version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
        "cpu_count": os.cpu_count(),
        "mode": "dry (offline copywriter, no API key)",
        "images": {},
    }
    try:
        cfg_path = examples.parent / "config.yaml"
        cfg = load_config(cfg_path) if cfg_path.exists() else AppConfig()
        cfg.memory.path = str(work / "memory.jsonl")
        cfg.cache.enabled = False

        # 1) Real pipeline run on the demo ads
        _say(progress, "Running the pipeline on examples/demo_ads.csv …")
        run_dir = work / "run"
        t0 = time.perf_counter()
        summary = run_pipeline(
            examples / "demo_ads.csv", run_dir, cfg, MockProvider(), "dry", render=False
        )
        copy_secs = time.perf_counter() - t0
        rows = pd.read_csv(run_dir / "new_ads.csv", dtype={"ad_id": str}).to_dict(
            "records"
        )
        # Persist what the board needs from this run
        from gcf.io_csv import read_ads_csv

        read_ads_csv(examples / "demo_ads.csv").to_csv(
            run_dir / "input_normalized.csv", index=False
        )
        (run_dir / "details.json").write_text(
            json.dumps(summary["details"], ensure_ascii=False), encoding="utf-8"
        )

        # 2) Render every variant in its advertiser's brand kit
        _say(progress, f"Rendering {len(rows)} variants …")
        by_ad: Dict[str, List[Dict]] = {}
        for r in rows:
            by_ad.setdefault(str(r["ad_id"]), []).append(r)
        rendered: Dict[str, List[str]] = {}
        t0 = time.perf_counter()
        n_images = 0
        for ad_id, ad_rows in by_ad.items():
            creatives = creatives_from_variants(ad_rows)
            items = render_batch(
                creatives,
                work / "renders" / ad_id,
                formats=["square"],
                brand=_brand_for(ad_id),
            )
            rendered[ad_id] = [it.path for it in items]
            n_images += len(items)
        render_secs = time.perf_counter() - t0

        # 01 before → after
        picks = [a for a in ("SS-101", "VM-204", "AL-310") if a in rendered]
        board = before_after_board(
            run_dir, rendered, out / "01-before-after.jpg", picks
        )
        manifest["images"][board.name] = {
            "what": "Underperforming ads to diagnosis, strategy and new creatives",
            "command": "gcf run --input examples/demo_ads.csv --mode dry",
            "ads_selected": summary["selected"],
            "variants": summary["variants_generated"],
        }

        # 02 scale mosaic
        all_paths = [p for a in rendered for p in rendered[a]]
        sub = (
            f"{summary['selected']} flagged ads, {len(all_paths)} unique on-brand images · "
            f"copy {copy_secs:.1f}s + render {render_secs:.1f}s on {os.cpu_count()} CPU cores"
        )
        mosaic = scale_mosaic(
            all_paths,
            out / "02-one-run-at-scale.jpg",
            sub,
            "gcf run --input examples/demo_ads.csv --mode dry --max-creatives 0",
        )
        manifest["images"][mosaic.name] = {
            "what": "Every variant from one run, rendered",
            "images": len(all_paths),
            "copy_seconds": round(copy_secs, 2),
            "render_seconds": round(render_secs, 2),
        }

        # 03 / 04 brief → posts (EN + VI)
        from gcf.posts import generate_posts

        briefs = [
            (
                "03-brief-to-posts-en.jpg",
                Brief(
                    product="Cloudstep running shoes",
                    audience="busy city runners",
                    offer="30% off launch week",
                    benefits=["Featherlight 180g build", "Cushioned for 20km runs"],
                    pain="sore feet after long runs",
                ),
                "sunset",
                'gcf create --product "Cloudstep running shoes" --audience "busy city runners" '
                '--offer "30% off launch week" --benefit "Featherlight 180g build" '
                '--benefit "Cushioned for 20km runs" --pain "sore feet after long runs" --brand sunset',
                "One product brief, six social posts",
            ),
            (
                "04-brief-to-posts-vi.jpg",
                Brief(
                    product="Cà phê Arabica Cầu Đất",
                    audience="dân văn phòng",
                    offer="Giảm 25% tuần này",
                    benefits=["Hương thơm đậm đà", "Rang mới mỗi tuần"],
                    pain="cà phê đắng gắt",
                ),
                "noir",
                'gcf create --product "Cà phê Arabica Cầu Đất" --audience "dân văn phòng" '
                '--offer "Giảm 25% tuần này" --benefit "Hương thơm đậm đà" '
                '--benefit "Rang mới mỗi tuần" --pain "cà phê đắng gắt" --brand noir',
                "Một brief, sáu bài đăng tiếng Việt",
            ),
        ]
        for name, brief, brand, cmd, title in briefs:
            _say(progress, f"Brief → posts: {brief.product} …")
            posts = generate_posts(brief, MockProvider(), n=6, cfg=cfg)
            items = render_batch(
                creatives_from_posts(posts),
                work / name,
                formats=["square"],
                brand=brand,
            )
            img = headed_grid(
                [it.path for it in items],
                out / name,
                title,
                "Copy written offline from the brief, then rendered — templates rotate automatically.",
                cmd,
                cols=3,
                tile=720,
            )
            manifest["images"][img.name] = {
                "what": title,
                "command": cmd,
                "posts": [p.to_dict() for p in posts],
            }

        # 05 one copy, any brand (incl. a custom YAML kit with a logo)
        _say(progress, "One copy, every brand kit …")
        kit_path = examples / "demo_brand" / "brand.yaml"
        kits = ["aurora", "sunset", "verde", "noir", "blossom", str(kit_path)]
        c = Creative(
            eyebrow="New collection",
            headline="Built for the long way home",
            description="Weatherproof shell, recycled fabric. Designed to last for years.",
            cta="Explore",
            tag="brand-swap",
        )
        paths, labels = [], []
        for k in kits:
            kit = load_brand(k)
            p = work / f"brand-{kit.name}.png"
            render_creative(c, "bold", "square", kit).save(p)
            paths.append(str(p))
            labels.append(
                kit.name + (" (custom YAML + logo)" if k == str(kit_path) else "")
            )
        img = headed_grid(
            paths,
            out / "05-one-copy-any-brand.jpg",
            "Same copy, six brand kits",
            "Five built-in presets plus a custom kit loaded from YAML with its own logo.",
            "gcf render --input sheet.csv --brand examples/demo_brand/brand.yaml",
            cols=3,
            tile=720,
            labels=labels,
        )
        manifest["images"][img.name] = {"what": "Brand kit swap", "kits": kits}

        # 06 every placement
        _say(progress, "Every placement …")
        fmts = ["story", "portrait", "square", "landscape", "wide"]
        c = Creative(
            eyebrow="Rau sạch mỗi sáng",
            headline="Từ nông trại đến bàn ăn trong 24 giờ",
            description="Rau hữu cơ thu hoạch mỗi sáng, giao tận nhà. Miễn phí vận chuyển đơn đầu tiên.",
            cta="Đặt rau ngay",
            tag="placements",
        )
        paths = []
        for f in fmts:
            p = work / f"fmt-{f}.png"
            render_creative(c, "split", f, "verde").save(p)
            paths.append(str(p))
        img = strip(
            paths,
            out / "06-every-placement.jpg",
            height=900,
            labels=["Story 9:16", "Feed 4:5", "Feed 1:1", "Link 1.91:1", "Wide 16:9"],
        )
        manifest["images"][img.name] = {
            "what": "One creative in every placement",
            "command": "gcf render --input sheet.csv --formats all",
        }

        manifest["totals"] = {
            "demo_images_rendered": n_images + 12 + 6 + len(fmts),
        }
        (out / "demo.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


__all__ = ["build_demo"]
