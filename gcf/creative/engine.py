"""Render creatives to images — single or in batch."""

from __future__ import annotations

import csv
import os
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path
from pickle import PicklingError
from typing import Callable, Iterable, List, Optional, Sequence, Union

from PIL import Image

from gcf.creative import draw as D
from gcf.creative.brand import BrandKit, load_brand
from gcf.creative.components import Ctx
from gcf.creative.formats import Format, get_format, parse_formats
from gcf.creative.model import Creative
from gcf.creative.templates import TEMPLATE_ORDER, get_template

SUPERSAMPLE = 2


def render_creative(
    creative: Creative,
    template: Optional[str] = None,
    fmt: Union[str, Format] = "square",
    brand: Union[BrandKit, str, dict, None] = None,
    supersample: int = SUPERSAMPLE,
) -> Image.Image:
    """Render one creative and return an RGB :class:`PIL.Image.Image`."""
    f = fmt if isinstance(fmt, Format) else get_format(fmt)
    kit = load_brand(brand)
    tpl = get_template(template or creative.template or TEMPLATE_ORDER[0])
    ctx = Ctx(creative, f, kit, ss=max(1, int(supersample)))
    tpl.render(ctx)
    img = ctx.canvas
    img = img.convert("RGB")
    if img.size != f.size:
        if ctx.ss > 1 and img.size == (f.width * ctx.ss, f.height * ctx.ss):
            img = img.reduce(ctx.ss)  # box-filter downsample = clean anti-aliasing
        else:
            img = img.resize(f.size, Image.Resampling.LANCZOS)
    D.add_grain(img, kit.grain, seed=creative.seed & 0xFFFF)
    return img


def _render_job(job) -> "RenderedCreative":
    """Module-level so it can run in a worker process."""
    c, tpl, fk, path_str, kit, ext = job
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    img = render_creative(c, tpl, fk, kit)
    if ext == "jpg":
        img.save(path, "JPEG", quality=92, optimize=True, progressive=True)
    else:
        img.save(path, "PNG", compress_level=6)
    return RenderedCreative(
        tag=c.tag,
        template=tpl,
        format=fk,
        path=str(path),
        width=img.width,
        height=img.height,
        headline=c.headline,
        description=c.description,
        cta=c.resolved_cta(kit.cta),
        badge=c.resolved_badge(),
    )


@dataclass
class RenderedCreative:
    tag: str
    template: str
    format: str
    path: str
    width: int
    height: int
    headline: str
    description: str
    cta: str
    badge: str


_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str, fallback: str = "creative") -> str:
    s = _SLUG.sub("-", str(value)).strip("-.")
    return s[:80] or fallback


def assign_templates(
    creatives: Sequence[Creative], templates: Optional[Sequence[str]] = None
) -> List[str]:
    """Pick a template per creative: explicit row value wins, otherwise rotate
    through *templates* (default: all) so a batch looks varied."""
    pool = [get_template(t).key for t in (templates or TEMPLATE_ORDER)]
    return [c.template or pool[i % len(pool)] for i, c in enumerate(creatives)]


def render_batch(
    creatives: Sequence[Creative],
    out_dir: Union[str, Path],
    formats: Union[str, Sequence[str], None] = None,
    templates: Optional[Sequence[str]] = None,
    brand: Union[BrandKit, str, dict, None] = None,
    image_format: str = "png",
    workers: Optional[int] = None,
    progress: Optional[Callable[[int, int], None]] = None,
    executor: str = "auto",
) -> List[RenderedCreative]:
    """Render every creative × format into ``out_dir/<format>/``.

    Writes ``manifest.csv`` and returns the list of rendered files.
    ``executor`` is ``auto`` (processes for big batches), ``process`` or
    ``thread`` — use ``thread`` inside servers that must not fork.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kit = load_brand(brand)
    fmts = parse_formats(formats)
    chosen = assign_templates(creatives, templates)
    ext = "jpg" if image_format.lower() in ("jpg", "jpeg") else "png"

    jobs = []
    seen = set()
    for i, (c, tpl) in enumerate(zip(creatives, chosen)):
        base = slugify(c.tag or f"creative-{i + 1:03d}")
        name = f"{base}_{tpl}"
        n = 2
        while name in seen:
            name = f"{base}_{tpl}-{n}"
            n += 1
        seen.add(name)
        for fk in fmts:
            jobs.append((c, tpl, fk, out / fk / f"{name}.{ext}"))

    total = len(jobs)
    payload = [(c, tpl, fk, str(path), kit, ext) for c, tpl, fk, path in jobs]
    n_workers = workers if workers is not None else min(8, (os.cpu_count() or 2))
    results: List[RenderedCreative] = []

    def _tick() -> None:
        if progress:
            progress(len(results), total)

    if n_workers <= 1 or total <= 2:
        for job in payload:
            results.append(_render_job(job))
            _tick()
    else:
        mode = executor
        if mode == "auto":
            mode = "process" if total >= 8 else "thread"
        done_proc = False
        if mode == "process":
            try:
                with ProcessPoolExecutor(max_workers=n_workers) as pool:
                    for r in pool.map(_render_job, payload, chunksize=2):
                        results.append(r)
                        _tick()
                done_proc = True
            except (BrokenProcessPool, OSError, PicklingError, RuntimeError):
                # Restricted environments (frozen apps, some notebooks/servers)
                # cannot spawn workers — fall back to threads transparently.
                results.clear()
        if not done_proc:
            with ThreadPoolExecutor(max_workers=n_workers) as pool:
                for r in pool.map(_render_job, payload):
                    results.append(r)
                    _tick()

    write_manifest(results, out / "manifest.csv", relative_to=out)
    return results


def write_manifest(
    items: Iterable[RenderedCreative], path: Path, relative_to: Optional[Path] = None
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "tag",
        "template",
        "format",
        "width",
        "height",
        "path",
        "headline",
        "description",
        "cta",
        "badge",
    ]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for it in items:
            p = Path(it.path)
            rel = os.path.relpath(p, relative_to) if relative_to else str(p)
            w.writerow(
                {**{k: getattr(it, k) for k in cols}, "path": rel.replace(os.sep, "/")}
            )
    return path
