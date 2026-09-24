"""Creative studio — glue between copy (pipeline / briefs / files) and images.

* :func:`creatives_from_variants` — pipeline rows → :class:`Creative` list
* :func:`creatives_from_file`     — any CSV/TSV (incl. Figma TSV) → creatives
* :func:`render_outputs`          — render + manifest + gallery + contact sheet
* :func:`create_from_brief`       — brief → posts → images, in one call
* :func:`build_showcase`          — the multi-brand demo set used in the README
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Union

import pandas as pd

from gcf.config import AppConfig, RenderConfig
from gcf.copywriter import EYEBROWS, Brief, Post
from gcf.creative import (
    FORMATS,
    Creative,
    RenderedCreative,
    detect_language,
    load_brand,
    parse_formats,
    parse_templates,
    render_batch,
)
from gcf.creative.gallery import contact_sheet, html_gallery
from gcf.dedupe import detect_angle_bucket
from gcf.providers.base import BaseProvider

Progress = Optional[Callable[[int, int], None]]


@dataclass
class RenderSummary:
    items: List[RenderedCreative] = field(default_factory=list)
    creatives_dir: Optional[str] = None
    manifest: Optional[str] = None
    gallery: Optional[str] = None
    contact_sheet: Optional[str] = None

    @property
    def count(self) -> int:
        return len(self.items)

    def to_dict(self) -> Dict:
        return {
            "rendered": self.count,
            "creatives_dir": self.creatives_dir,
            "manifest": self.manifest,
            "gallery": self.gallery,
            "contact_sheet": self.contact_sheet,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Sources → creatives
# ─────────────────────────────────────────────────────────────────────────────


def _eyebrow_for(text: str) -> str:
    lang = detect_language(text)
    return EYEBROWS.get(lang, EYEBROWS["en"]).get(detect_angle_bucket(text), "")


def creatives_from_variants(rows: Sequence[Dict], limit: int = 0) -> List[Creative]:
    """Pipeline ``new_ads`` rows → creatives, spread fairly across ads.

    With a *limit*, variants are picked round-robin per ``ad_id`` so every
    selected ad gets images before any ad gets a second one.
    """
    by_ad: Dict[str, List[Dict]] = {}
    for r in rows:
        by_ad.setdefault(str(r.get("ad_id", "")), []).append(r)
    ordered: List[Dict] = []
    depth = 0
    while any(depth < len(v) for v in by_ad.values()):
        for v in by_ad.values():
            if depth < len(v):
                ordered.append(v[depth])
        depth += 1
    if limit and limit > 0:
        ordered = ordered[:limit]
    out = []
    for r in ordered:
        h = str(r.get("variant_headline", ""))
        out.append(
            Creative(
                headline=h,
                description=str(r.get("variant_description", "")),
                tag=str(r.get("tag", "")),
                eyebrow=_eyebrow_for(h),
            )
        )
    return out


def creatives_from_posts(posts: Sequence[Post], prefix: str = "POST") -> List[Creative]:
    return [
        Creative(
            headline=p.headline,
            description=p.description,
            cta=p.cta,
            eyebrow=p.eyebrow,
            badge=p.badge,
            tag=f"{prefix}-{i + 1:02d}",
        )
        for i, p in enumerate(posts)
    ]


def _guess_delimiter(p: Path) -> str:
    """Pick the delimiter from the header line (never a letter)."""
    if p.suffix.lower() in (".tsv", ".tab"):
        return "\t"
    try:
        with open(p, encoding="utf-8-sig", errors="replace") as fh:
            header = fh.readline()
    except OSError:
        return ","
    counts = {d: header.count(d) for d in (",", "\t", ";", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def creatives_from_file(
    path: Union[str, Path], limit: int = 0, allow_images: bool = True
) -> List[Creative]:
    """Read CSV/TSV copy (Figma TSV, new_ads.csv, or a hand-made sheet).

    Relative ``image`` paths resolve against the sheet's folder. Pass
    ``allow_images=False`` for untrusted uploads so a sheet cannot pull
    arbitrary files from the machine into rendered output.
    """
    p = Path(path)
    try:
        df = pd.read_csv(
            p, sep=_guess_delimiter(p), dtype=str, encoding="utf-8-sig"
        ).fillna("")
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"Could not parse {p.name}: {exc}. Tip: quote cells that contain commas."
        ) from exc
    out: List[Creative] = []
    for i, row in enumerate(df.to_dict("records")):
        c = Creative.from_row(row)
        if not c.headline:
            continue
        if not c.tag:
            c.tag = f"C{i + 1:03d}"
        if c.image:
            if not allow_images:
                c.image = None
            elif not Path(c.image).expanduser().is_absolute():
                c.image = str((p.parent / c.image).resolve())
        out.append(c)
        if limit and len(out) >= limit:
            break
    if not out:
        raise ValueError(
            f"No rows with a headline found in {p}. Expected a column named "
            "headline / H1 / variant_headline / title."
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────


def render_outputs(
    creatives: Sequence[Creative],
    out_dir: Union[str, Path],
    rcfg: Optional[RenderConfig] = None,
    title: str = "Creative batch",
    subtitle: str = "",
    progress: Progress = None,
    creatives_subdir: str = "creatives",
) -> RenderSummary:
    """Render creatives and write manifest, HTML gallery and contact sheet."""
    rcfg = rcfg or RenderConfig(enabled=True)
    out = Path(out_dir)
    cdir = out / creatives_subdir
    brand = load_brand(rcfg.brand)
    _clear_previous_render(out, cdir)
    items = render_batch(
        creatives,
        cdir,
        formats=parse_formats(rcfg.formats),
        templates=parse_templates(rcfg.templates) or None,
        brand=brand,
        image_format=rcfg.image_format,
        workers=rcfg.workers or None,
        progress=progress,
        executor=getattr(rcfg, "executor", "auto"),
    )
    summary = RenderSummary(
        items=items, creatives_dir=str(cdir), manifest=str(cdir / "manifest.csv")
    )
    n_fmt = len(parse_formats(rcfg.formats))
    sub = subtitle or (
        f"{len(creatives)} variant{'s' if len(creatives) != 1 else ''} × "
        f"{n_fmt} format{'s' if n_fmt != 1 else ''} · {brand.name}"
    )
    if rcfg.gallery and items:
        summary.gallery = str(
            html_gallery(items, out / "gallery.html", title=title, subtitle=sub)
        )
    if rcfg.contact_sheet and items:
        first_fmt = parse_formats(rcfg.formats)[0]
        pick = [it.path for it in items if it.format == first_fmt][:24]
        summary.contact_sheet = str(
            contact_sheet(pick, out / "contact_sheet.png", title=title, subtitle=sub)
        )
    return summary


def _clear_previous_render(out: Path, cdir: Path) -> None:
    """Remove images and review files a previous render wrote here, so a
    re-render (or its ZIP) never mixes old and new creatives. Only files this
    module creates are touched."""
    for fk in FORMATS:
        fdir = cdir / fk
        if fdir.is_dir():
            for f in fdir.iterdir():
                if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg"):
                    f.unlink()
            try:
                fdir.rmdir()
            except OSError:
                pass  # contains user files — leave it
    for f in (cdir / "manifest.csv", out / "gallery.html", out / "contact_sheet.png"):
        if f.is_file():
            f.unlink()


def write_posts_csv(posts: Sequence[Post], path: Union[str, Path]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = ["tag", "eyebrow", "headline", "description", "cta", "badge", "angle"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for i, post in enumerate(posts):
            w.writerow({"tag": f"POST-{i + 1:02d}", **post.to_dict()})
    return p


def create_from_brief(
    brief: Brief,
    provider: BaseProvider,
    out_dir: Union[str, Path],
    n: int = 6,
    cfg: Optional[AppConfig] = None,
    rcfg: Optional[RenderConfig] = None,
    progress: Progress = None,
) -> Dict:
    """Brief → posts.csv + rendered images + gallery."""
    from gcf.posts import generate_posts

    cfg = cfg or AppConfig()
    posts = generate_posts(brief, provider, n=n, cfg=cfg)
    out = Path(out_dir)
    posts_csv = write_posts_csv(posts, out / "posts.csv")
    rs = render_outputs(
        creatives_from_posts(posts),
        out,
        rcfg or cfg.render,
        title=brief.product or "Social posts",
        progress=progress,
    )
    return {"posts": posts, "posts_csv": str(posts_csv), "render": rs}


# ─────────────────────────────────────────────────────────────────────────────
# Showcase — a multi-brand demo set (fictional brands, synthetic copy)
# ─────────────────────────────────────────────────────────────────────────────

SHOWCASE: List[Dict] = [
    {
        "brand": "sunset",
        "template": "bold",
        "creative": dict(
            eyebrow="Launch week",
            headline="Run lighter. Go further.",
            description="Featherlight 180g build with cloud-soft cushioning. Free returns for 30 days.",
            cta="Shop the drop",
            badge="-30%",
        ),
    },
    {
        "brand": "noir",
        "template": "editorial",
        "creative": dict(
            eyebrow="The autumn edit",
            headline="Quiet luxury, made to last",
            description="Hand-finished Italian leather in five timeless shades. Complimentary engraving.",
            cta="Explore the collection",
        ),
    },
    {
        "brand": "verde",
        "template": "split",
        "creative": dict(
            eyebrow="Rau sạch mỗi sáng",
            headline="Từ nông trại đến bàn ăn trong 24 giờ",
            description="Rau hữu cơ thu hoạch mỗi sáng, giao tận nhà. Miễn phí vận chuyển đơn đầu tiên.",
            cta="Đặt rau ngay",
        ),
    },
    {
        "brand": "aurora",
        "template": "glass",
        "creative": dict(
            eyebrow="New · AI workspace",
            headline="Ship campaigns 10× faster",
            description="Plan, write and design every ad in one workspace, with your whole team.",
            cta="Start free trial",
        ),
    },
    {
        "brand": "blossom",
        "template": "promo",
        "creative": dict(
            eyebrow="Ưu đãi cuối tuần",
            headline="Serum sáng da, rạng rỡ mỗi ngày",
            description="Chiết xuất hoa anh đào & vitamin C. Mua 1 tặng 1 cho 500 khách đầu tiên.",
            cta="Nhận ưu đãi",
            badge="1+1",
        ),
    },
    {
        "brand": "tide",
        "template": "photo",
        "creative": dict(
            eyebrow="Summer escape",
            headline="Your island weekend awaits",
            description="Oceanfront villas from $129/night. Breakfast and airport transfer included.",
            cta="Book your stay",
            badge="-25%",
        ),
    },
]


def build_showcase(
    out_dir: Union[str, Path],
    formats: Sequence[str] = ("square", "portrait", "story", "landscape"),
    progress: Progress = None,
) -> Dict[str, str]:
    """Render the showcase set: every brand/template across *formats*."""
    from gcf.creative import render_creative

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: Dict[str, str] = {}
    total = len(SHOWCASE) * len(formats)
    done = 0
    for item in SHOWCASE:
        c = Creative(**item["creative"], tag=item["brand"])
        for fk in formats:
            img = render_creative(c, item["template"], fk, item["brand"])
            path = out / f"{item['brand']}-{item['template']}-{fk}.png"
            img.save(path, "PNG", optimize=True)
            written[f"{item['brand']}/{fk}"] = str(path)
            done += 1
            if progress:
                progress(done, total)
    return written


def build_showcase_assets(
    out_dir: Union[str, Path], progress: Progress = None
) -> List[str]:
    """Hero composites for the README (JPEG to keep the repo light).

    The proof images live in ``docs/demo`` and come from ``gcf demo``.
    """
    from gcf.creative import TEMPLATES, render_creative
    from gcf.creative.gallery import contact_sheet, strip

    out = Path(out_dir)
    tmp = out / "_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    written = build_showcase(
        tmp, ("square", "portrait", "story", "landscape"), progress
    )
    files: List[str] = []

    grid = [written[f"{i['brand']}/square"] for i in SHOWCASE]
    files.append(
        str(
            contact_sheet(
                grid,
                out / "showcase-grid.jpg",
                width=2400,
                row_height=560,
                title="Growth Creative Factory",
                subtitle="6 fictional brands · 6 templates · rendered offline in seconds",
            )
        )
    )

    # Same copy, every template
    same = Creative(
        eyebrow="New collection",
        headline="Comfort you can feel from step one",
        description="Featherlight knit, cloud-soft sole. Free returns within 30 days.",
        cta="Shop now",
        badge="-20%",
        tag="tpl",
    )
    tpl_paths = []
    for key in TEMPLATES:
        p = tmp / f"tpl-{key}.png"
        render_creative(same, key, "portrait", "aurora").save(p)
        tpl_paths.append(str(p))
    files.append(
        str(
            strip(
                tpl_paths,
                out / "templates.jpg",
                height=700,
                labels=[TEMPLATES[k].name for k in TEMPLATES],
            )
        )
    )

    import shutil

    shutil.rmtree(tmp, ignore_errors=True)
    return files
