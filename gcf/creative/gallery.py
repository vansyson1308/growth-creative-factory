"""Review surfaces for a batch: an HTML gallery and a PNG contact sheet."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from gcf.creative.engine import RenderedCreative
from gcf.creative.fonts import font_path, load_font
from gcf.creative.formats import FORMATS
from gcf.creative.templates import TEMPLATES


def contact_sheet(
    image_paths: Sequence[str],
    out_path: str | Path,
    width: int = 2400,
    row_height: int = 520,
    gap: int = 28,
    margin: int = 64,
    background: Tuple[int, int, int] = (14, 14, 20),
    title: str = "",
    subtitle: str = "",
) -> Path:
    """Justified-row contact sheet (like a photo wall) of mixed aspect ratios."""
    ims: List[Image.Image] = []
    for p in image_paths:
        try:
            with Image.open(p) as im:
                ims.append(im.convert("RGB"))
        except Exception:
            continue
    inner = width - 2 * margin
    rows: List[List[Image.Image]] = []
    cur: List[Image.Image] = []
    cur_w = 0.0
    for im in ims:
        w = im.width * row_height / im.height
        if cur and cur_w + w + gap * len(cur) > inner:
            rows.append(cur)
            cur, cur_w = [], 0.0
        cur.append(im)
        cur_w += w
    if cur:
        rows.append(cur)

    header = 0
    if title:
        header = 170 if subtitle else 120
    layout = []
    y = margin + header
    for i, row in enumerate(rows):
        natural = sum(im.width * row_height / im.height for im in row)
        avail = inner - gap * (len(row) - 1)
        scale = (
            avail / natural if (i < len(rows) - 1 or natural > avail * 0.75) else 1.0
        )
        h = int(row_height * scale)
        x = margin
        for im in row:
            w = int(im.width * h / im.height)
            layout.append((im, x, y, w, h))
            x += w + gap
        y += h + gap
    height = y - gap + margin

    sheet = Image.new("RGB", (width, max(height, margin * 2 + header)), background)
    d = ImageDraw.Draw(sheet)
    if title:
        f1 = load_font(font_path("display"), 64)
        d.text((margin, margin), title, font=f1, fill=(255, 255, 255))
        if subtitle:
            f2 = load_font(font_path("body"), 30)
            d.text((margin, margin + 88), subtitle, font=f2, fill=(170, 170, 190))
    for im, x, yy, w, h in layout:
        thumb = im.resize((w, h), Image.Resampling.LANCZOS)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=14, fill=255)
        sheet.paste(thumb, (x, yy), mask)
    return _save(sheet, out_path)


def _save(img: Image.Image, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img.convert("RGB").save(
            out, "JPEG", quality=88, optimize=True, progressive=True
        )
    else:
        img.save(out, "PNG", optimize=True)
    return out


def strip(
    image_paths: Sequence[str],
    out_path: str | Path,
    height: int = 900,
    gap: int = 36,
    margin: int = 64,
    background: Tuple[int, int, int] = (14, 14, 20),
    labels: Optional[Sequence[str]] = None,
) -> Path:
    """One row of images at equal height, bottom-aligned, optional captions."""
    ims = []
    for p in image_paths:
        with Image.open(p) as im:
            ims.append(im.convert("RGB"))
    tallest = max(im.height for im in ims)
    scale = height / tallest
    sized = [
        im.resize(
            (int(im.width * scale), int(im.height * scale)), Image.Resampling.LANCZOS
        )
        for im in ims
    ]
    label_h = 64 if labels else 0
    width = sum(im.width for im in sized) + gap * (len(sized) - 1) + 2 * margin
    canvas = Image.new("RGB", (width, height + 2 * margin + label_h), background)
    d = ImageDraw.Draw(canvas)
    font = load_font(font_path("heading"), 30)
    x = margin
    for i, im in enumerate(sized):
        y = margin + height - im.height
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *im.size), radius=16, fill=255)
        canvas.paste(im, (x, y), mask)
        if labels and i < len(labels):
            tw = font.getlength(labels[i])
            d.text(
                (x + (im.width - tw) / 2, margin + height + 22),
                labels[i],
                font=font,
                fill=(170, 170, 190),
            )
        x += im.width + gap
    return _save(canvas, out_path)


def html_gallery(
    items: Sequence[RenderedCreative],
    out_path: str | Path,
    title: str = "Creative batch",
    subtitle: str = "",
    relative_to: Optional[str | Path] = None,
) -> Path:
    """Self-contained, filterable review gallery (no external assets)."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    base = Path(relative_to) if relative_to else out.parent
    data = []
    for it in items:
        rel = os.path.relpath(Path(it.path), base).replace(os.sep, "/")
        data.append(
            {
                "src": rel,
                "tag": it.tag,
                "template": it.template,
                "templateName": (
                    TEMPLATES[it.template].name
                    if it.template in TEMPLATES
                    else it.template
                ),
                "format": it.format,
                "formatLabel": (
                    FORMATS[it.format].label if it.format in FORMATS else it.format
                ),
                "w": it.width,
                "h": it.height,
                "headline": it.headline,
                "description": it.description,
                "cta": it.cta,
                "badge": it.badge,
            }
        )
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    doc = (
        _HTML.replace("__TITLE__", html.escape(title))
        .replace("__SUBTITLE__", html.escape(subtitle))
        .replace("__DATA__", payload)
    )
    out.write_text(doc, encoding="utf-8")
    return out


_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f6f9;--panel:#fff;--ink:#14141c;--muted:#6b6b7b;--line:#e6e6ee;--chip:#ececf3;--accent:#5b5bf7}
@media (prefers-color-scheme:dark){:root{--bg:#0d0d13;--panel:#17171f;--ink:#f1f1f6;--muted:#9a9aab;--line:#262631;--chip:#22222c;--accent:#8b8bff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:32px 24px 8px;max-width:1400px;margin:auto}h1{margin:0;font-size:28px;letter-spacing:-.02em}
.sub{color:var(--muted);margin:4px 0 0}
.bar{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.bar-in{max-width:1400px;margin:auto;padding:12px 24px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.group{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.lbl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-right:4px}
button.f{border:1px solid var(--line);background:var(--panel);color:var(--ink);padding:6px 12px;border-radius:999px;cursor:pointer;font:inherit;font-size:13px}
button.f[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
input[type=search]{flex:1;min-width:180px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:999px;padding:7px 14px;font:inherit}
.count{color:var(--muted);font-size:13px;margin-left:auto}
main{max-width:1400px;margin:auto;padding:20px 24px 60px;columns:280px;column-gap:18px}
.card{break-inside:avoid;margin:0 0 18px;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.card img{display:block;width:100%;height:auto;cursor:zoom-in;background:var(--chip)}
.meta{padding:10px 12px 12px}.chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.chip{font-size:11px;background:var(--chip);border-radius:999px;padding:2px 8px;color:var(--muted)}
.h{font-weight:650;margin:0}.d{color:var(--muted);font-size:13px;margin:2px 0 0}
.card a.dl{font-size:12px;color:var(--accent);text-decoration:none}
dialog{border:0;padding:0;background:transparent;max-width:96vw;max-height:96vh}dialog::backdrop{background:rgba(0,0,0,.8)}
dialog img{max-width:96vw;max-height:92vh;display:block;border-radius:10px}
.empty{color:var(--muted);text-align:center;padding:60px 0;column-span:all}
</style>
</head>
<body>
<header><h1>__TITLE__</h1><p class="sub">__SUBTITLE__</p></header>
<div class="bar"><div class="bar-in">
  <div class="group" id="fmt"><span class="lbl">Format</span></div>
  <div class="group" id="tpl"><span class="lbl">Template</span></div>
  <input type="search" id="q" placeholder="Search copy or tag…" aria-label="Search">
  <span class="count" id="count"></span>
</div></div>
<main id="grid"></main>
<dialog id="lb"><img alt=""></dialog>
<script>
const DATA=__DATA__;
const state={format:"all",template:"all",q:""};
function uniq(k,l){const m=new Map();DATA.forEach(d=>m.set(d[k],d[l]));return [...m.entries()]}
function chips(id,key,entries){const g=document.getElementById(id);
  [["all","All"],...entries].forEach(([v,label])=>{const b=document.createElement("button");b.className="f";b.textContent=label;
  b.setAttribute("aria-pressed",v==="all");b.onclick=()=>{state[key]=v;g.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x===b));render()};g.appendChild(b)})}
chips("fmt","format",uniq("format","formatLabel"));chips("tpl","template",uniq("template","templateName"));
document.getElementById("q").oninput=e=>{state.q=e.target.value.toLowerCase();render()};
const lb=document.getElementById("lb");lb.onclick=()=>lb.close();
function esc(s){return String(s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function render(){const g=document.getElementById("grid");
  const rows=DATA.filter(d=>(state.format==="all"||d.format===state.format)&&(state.template==="all"||d.template===state.template)
   &&(!state.q||(d.headline+" "+d.description+" "+d.tag).toLowerCase().includes(state.q)));
  document.getElementById("count").textContent=rows.length+" / "+DATA.length+" creatives";
  g.innerHTML=rows.length?rows.map((d,i)=>`<figure class="card"><img loading="lazy" src="${esc(d.src)}" width="${d.w}" height="${d.h}" alt="${esc(d.headline)}" data-i="${i}">
   <figcaption class="meta"><div class="chips"><span class="chip">${esc(d.formatLabel)}</span><span class="chip">${esc(d.templateName)}</span>${d.tag?`<span class="chip">${esc(d.tag)}</span>`:""}${d.badge?`<span class="chip">${esc(d.badge)}</span>`:""}</div>
   <p class="h">${esc(d.headline)}</p><p class="d">${esc(d.description)}</p><a class="dl" href="${esc(d.src)}" download>Download ${d.w}×${d.h}</a></figcaption></figure>`).join(""):`<p class="empty">No creatives match these filters.</p>`;
  g.querySelectorAll("img").forEach(img=>img.onclick=()=>{lb.querySelector("img").src=img.src;lb.showModal()})}
render();
</script>
</body>
</html>
"""
