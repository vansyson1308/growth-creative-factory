"""Reusable design components shared by all templates."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image, ImageDraw

from gcf.creative import draw as D
from gcf.creative.brand import BrandKit
from gcf.creative.color import RGB, contrast_ratio, mix, readable_on
from gcf.creative.fonts import font_path, load_font
from gcf.creative.formats import Format
from gcf.creative.model import Creative
from gcf.creative.text import TextBlock, draw_block, fit_text, layout, text_width

Box = Tuple[float, float, float, float]


class Ctx:
    """Render context: canvas, scale unit, brand colours and safe area.

    Everything is drawn at ``ss``× super-sampling and downscaled at the end for
    crisp anti-aliased shapes. ``u`` is one design pixel on a 1080px short side.
    """

    def __init__(self, creative: Creative, fmt: Format, brand: BrandKit, ss: int = 2):
        self.c = creative
        self.fmt = fmt
        self.brand = brand
        self.ss = ss
        self.W, self.H = fmt.width * ss, fmt.height * ss
        self.u = ss * min(fmt.width, fmt.height) / 1080.0
        self.rng = random.Random(creative.seed)
        self.canvas = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 255))
        top, right, bottom, left = fmt.safe
        self.safe: Box = (
            left * self.W,
            top * self.H,
            self.W - right * self.W,
            self.H - bottom * self.H,
        )
        self.aspect = fmt.aspect
        self.is_wide = self.aspect > 1.3
        self.is_tall = self.aspect < 0.7
        # Type scale: tall canvases have room for larger supporting type.
        self.k = 1.22 if self.is_tall else 1.0
        self.primary = brand.rgb("primary")
        self.secondary = brand.rgb("secondary")
        self.accent = brand.rgb("accent")
        self.dark = brand.rgb("dark")
        self.paper = brand.rgb("paper")
        self.ink = brand.rgb("ink")
        self.cta_text = creative.resolved_cta(brand.cta)
        self.badge = creative.resolved_badge()
        self.image = D.load_image(creative.image)

    def font(self, role: str) -> str:
        return font_path(role, self.brand.fonts)

    def r(self, v: float) -> float:
        """Corner radius scaled by the brand's roundness preference."""
        return v * self.u * self.brand.radius

    def visual(
        self,
        size: Tuple[int, int],
        style: Optional[str] = None,
        focus: Tuple[float, float, float, float] = (0.1, 0.1, 0.9, 0.9),
    ) -> Image.Image:
        """Product photo if provided, otherwise brand-coloured generative art."""
        if self.image is not None:
            from PIL import ImageOps

            return ImageOps.fit(self.image, size, Image.Resampling.LANCZOS)
        palette = [self.dark, self.primary, self.secondary, self.accent]
        return D.generative_art(size, palette, self.c.seed, style, focus)


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────


def paint_text(
    ctx: Ctx,
    block: TextBlock,
    xy: Tuple[float, float],
    fill,
    align: str = "left",
    box_width: Optional[float] = None,
) -> Box:
    """Draw a text block through a transparent layer so alpha fills blend."""
    bw = box_width if box_width is not None else block.width
    pad = int(block.size * 0.6) + 4
    lw = int(bw + 2 * pad)
    lh = int(block.height + 2 * pad)
    layer = Image.new("RGBA", (max(1, lw), max(1, lh)), (0, 0, 0, 0))
    fill = fill if len(fill) == 4 else (*fill, 255)
    box = draw_block(ImageDraw.Draw(layer), block, (pad, pad), fill, align, bw)
    ox, oy = int(xy[0]) - pad, int(xy[1]) - pad
    D._composite_clipped(ctx.canvas, layer, (ox, oy))
    return (box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy)


def line_block(ctx: Ctx, text: str, role: str, size: float, tracking: float = 0.0):
    block = layout(text, ctx.font(role), int(size), 10**6, 1.2)
    block.tracking = tracking
    return block


def fit_label(
    ctx: Ctx,
    text: str,
    role: str,
    size: float,
    max_width: Optional[float],
    tracking_frac: float = 0.0,
) -> Tuple[TextBlock, float]:
    """Single-line label (eyebrow, button) that never exceeds *max_width*:
    shrinks down to 75% of *size*, then truncates with an ellipsis."""
    s = size
    block = line_block(ctx, text, role, s, tracking=s * tracking_frac)
    if not max_width or block.width <= max_width:
        return block, s
    while s > size * 0.75 and block.width > max_width:
        s *= 0.94
        block = line_block(ctx, text, role, s, tracking=s * tracking_frac)
    cut = text
    while block.width > max_width and len(cut) > 1:
        cut = cut[:-1].rstrip()
        block = line_block(ctx, cut + "…", role, s, tracking=s * tracking_frac)
    return block, s


# ─────────────────────────────────────────────────────────────────────────────
# Brand mark
# ─────────────────────────────────────────────────────────────────────────────


def brand_mark(
    ctx: Ctx,
    xy: Tuple[float, float],
    color: RGB,
    height: float = 46,
    align: str = "left",
    mono_bg: Optional[RGB] = None,
    chip: bool = False,
) -> Box:
    """Logo (if supplied) or monogram + wordmark. Returns the used box.

    ``chip=True`` puts a translucent dark capsule behind the mark so it stays
    legible on busy photos.
    """
    if chip:
        probe = brand_mark_width(ctx, height)
        u = ctx.u
        x, y = xy
        if align == "center":
            x -= probe / 2
        elif align == "right":
            x -= probe
        pad = height * u * 0.28
        D.rounded_rect(
            ctx.canvas,
            (x - pad, y - pad, x + probe + pad * 1.6, y + height * u + pad),
            (height * u + 2 * pad) / 2,
            fill=(0, 0, 0, 70),
        )
        return brand_mark(ctx, (x, y), color, height, "left", mono_bg, False)
    u = ctx.u
    h = height * u
    x, y = xy
    logo = _logo_for(ctx, color)
    if logo is not None:
        ratio = logo.width / max(1, logo.height)
        w = min(h * ratio, h * 6)
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        return D.paste_contain(ctx.canvas, logo, (x, y, x + w, y + h))

    name = ctx.brand.name or ""
    word = line_block(ctx, name, "heading", h * 0.56)
    gap = h * 0.32
    total = h + gap + word.width
    if align == "center":
        x -= total / 2
    elif align == "right":
        x -= total
    bg = mono_bg or color
    D.ellipse(ctx.canvas, (x, y, x + h, y + h), fill=(*bg, 255))
    initial = (name.strip()[:1] or "•").upper()
    ib = line_block(ctx, initial, "display", h * 0.52)
    fg = readable_on(bg, (255, 255, 255), ctx.ink)
    paint_text(ctx, ib, (x + (h - ib.width) / 2, y + (h - ib.height) / 2), fg)
    paint_text(ctx, word, (x + h + gap, y + (h - word.height) / 2), color)
    return (x, y, x + total, y + h)


def _logo_for(ctx: Ctx, fg: RGB) -> Optional[Image.Image]:
    """Pick the logo variant that stays visible where it is placed.

    *fg* is the foreground colour the layout uses at that spot (white on dark
    canvases, ink on light ones). ``logo_dark`` is preferred on light spots;
    a monochrome logo that would vanish is re-tinted to *fg* (alpha kept).
    """
    import numpy as np

    from gcf.creative.color import luminance

    on_light = luminance(fg) < 0.4
    path = ctx.brand.logo_dark if (on_light and ctx.brand.logo_dark) else ctx.brand.logo
    logo = D.load_image(path)
    if logo is None:
        return None
    arr = np.asarray(logo, dtype=np.float32)
    alpha = arr[..., 3]
    opaque = alpha > 32
    if not opaque.any():
        return logo
    rgb = arr[..., :3][opaque]
    spread = float((rgb.max(axis=1) - rgb.min(axis=1)).mean())  # ~saturation
    mean = tuple(int(v) for v in rgb.mean(axis=0))
    if spread < 24 and contrast_ratio(mean, fg) > 3:
        tinted = Image.new("RGBA", logo.size, (*fg, 0))
        tinted.putalpha(logo.getchannel("A"))
        return tinted
    return logo


def brand_mark_width(ctx: Ctx, height: float = 46) -> float:
    h = height * ctx.u
    logo = D.load_image(ctx.brand.logo)
    if logo is not None:
        return min(h * logo.width / max(1, logo.height), h * 6)
    word = line_block(ctx, ctx.brand.name or "", "heading", h * 0.56)
    return h + h * 0.32 + word.width


# ─────────────────────────────────────────────────────────────────────────────
# Pills, buttons, arrows, stickers
# ─────────────────────────────────────────────────────────────────────────────


def pill(
    ctx: Ctx,
    text: str,
    xy: Tuple[float, float],
    size: float,
    bg,
    fg,
    align: str = "left",
    role: str = "heading",
    tracking: float = 0.08,
    outline=None,
    max_width: Optional[float] = None,
) -> Box:
    u = ctx.u
    s0 = size * u
    px, h = s0 * 0.95, s0 * 2.05
    limit = (max_width if max_width else ctx.safe[2] - ctx.safe[0]) - 2 * px
    block, s = fit_label(ctx, text, role, s0, limit, tracking)
    w = block.width + 2 * px
    x, y = xy
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    D.rounded_rect(
        ctx.canvas,
        (x, y, x + w, y + h),
        radius=min(h / 2, ctx.r(h / 2 / u)),
        fill=bg,
        outline=outline,
        width=int(max(1, 1.5 * u)) if outline else 0,
    )
    paint_text(ctx, block, (x + px, y + (h - block.height) / 2), fg)
    return (x, y, x + w, y + h)


def arrow(ctx: Ctx, x: float, cy: float, length: float, color, width: float) -> None:
    head = length * 0.42
    pad = int(width * 2 + 4)
    x0, y0 = int(x) - pad, int(cy - head) - pad
    lw, lh = int(length) + 2 * pad + 2, int(2 * head) + 2 * pad + 2
    layer, d = D.shape_layer((lw, lh))
    ox, oy = x - x0, cy - y0
    d.line((ox, oy, ox + length, oy), fill=color, width=int(width))
    d.line(
        (ox + length - head, oy - head, ox + length, oy, ox + length - head, oy + head),
        fill=color,
        width=int(width),
        joint="curve",
    )
    for px, py in (
        (ox, oy),
        (ox + length - head, oy - head),
        (ox + length - head, oy + head),
    ):
        rr = width / 2
        d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=color)
    D._composite_clipped(ctx.canvas, layer, (x0, y0))


def cta_button_size(ctx: Ctx, size: float) -> Tuple[float, float]:
    s = size * ctx.u
    block = line_block(ctx, ctx.cta_text, "heading", s)
    px, h = s * 1.25, s * 2.55
    return block.width + 2 * px + s * 1.5, h


def cta_button(
    ctx: Ctx,
    xy: Tuple[float, float],
    size: float,
    bg: RGB,
    fg: Optional[RGB] = None,
    align: str = "left",
    shadow: bool = True,
    gradient: Optional[Tuple[RGB, RGB]] = None,
    max_width: Optional[float] = None,
) -> Box:
    u = ctx.u
    s = size * u
    fg = fg or readable_on(bg, (255, 255, 255), ctx.ink)
    px, h = s * 1.25, s * 2.55
    arrow_w = s * 0.95
    extra = 2 * px + arrow_w + s * 0.55
    limit = (max_width if max_width else ctx.safe[2] - ctx.safe[0]) - extra
    block, _ = fit_label(ctx, ctx.cta_text, "heading", s, limit)
    w = block.width + extra
    x, y = xy
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    radius = min(h / 2, ctx.r(h / 2 / u))
    if shadow:
        D.drop_shadow(
            ctx.canvas,
            (x, y, x + w, y + h),
            radius,
            blur=18 * u,
            offset=(0, 10 * u),
            color=mix(bg, (0, 0, 0), 0.6),
            opacity=0.45,
        )
    if gradient:
        grad = D.linear_gradient((int(w), int(h)), list(gradient), angle=90)
        D.paste_cover(ctx.canvas, grad, (x, y, x + w, y + h), radius=radius)
    else:
        D.rounded_rect(ctx.canvas, (x, y, x + w, y + h), radius=radius, fill=(*bg, 255))
    paint_text(ctx, block, (x + px, y + (h - block.height) / 2), fg)
    arrow(
        ctx, x + px + block.width + s * 0.55, y + h / 2, arrow_w, (*fg, 255), s * 0.14
    )
    return (x, y, x + w, y + h)


def cta_link(
    ctx: Ctx,
    xy: Tuple[float, float],
    size: float,
    color: RGB,
    align: str = "left",
    max_width: Optional[float] = None,
) -> Box:
    u = ctx.u
    s = size * u
    limit = (max_width if max_width else ctx.safe[2] - ctx.safe[0]) - s * 1.6
    block, _ = fit_label(ctx, ctx.cta_text, "heading", s, limit)
    arrow_w = s * 1.0
    w = block.width + s * 0.6 + arrow_w
    x, y = xy
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    paint_text(ctx, block, (x, y), color)
    uy = y + block.height + s * 0.35
    D.rounded_rect(
        ctx.canvas, (x, uy, x + w, uy + max(2, s * 0.09)), 0, fill=(*color, 255)
    )
    arrow(
        ctx,
        x + block.width + s * 0.6,
        y + block.height * 0.55,
        arrow_w,
        (*color, 255),
        s * 0.1,
    )
    return (x, y, x + w, uy + s * 0.09)


def sticker(
    ctx: Ctx,
    text: str,
    center: Tuple[float, float],
    radius: float,
    bg: RGB,
    fg: Optional[RGB] = None,
    rotate: float = -12,
    points: int = 20,
) -> None:
    """Starburst 'sale' sticker with fitted text, slightly rotated."""
    u = ctx.u
    r = radius * u
    size = int(r * 2.4)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = size / 2
    poly = []
    for i in range(points * 2):
        ang = math.pi * i / points
        rr = r if i % 2 == 0 else r * 0.88
        poly.append((c + rr * math.cos(ang), c + rr * math.sin(ang)))
    d.polygon(poly, fill=(*bg, 255))
    fg = fg or readable_on(bg, (255, 255, 255), ctx.ink)
    ring = r * 0.74
    d.ellipse(
        (c - ring, c - ring, c + ring, c + ring),
        outline=(*fg, 70),
        width=max(1, int(2 * u)),
    )
    n_words = max(1, len(text.split()))
    block = fit_text(
        text,
        ctx.font("display"),
        r * 1.25,
        r * 1.0,
        int(r * 0.62),
        int(r * 0.16),
        min(2, n_words),
        1.0,
        True,
    )
    draw_block(
        d, block, (c - r * 0.625, c - block.height / 2), (*fg, 255), "center", r * 1.25
    )
    layer = layer.rotate(rotate, resample=Image.Resampling.BICUBIC)
    cx, cy = center
    # Keep the sticker fully on-canvas (a little overhang past the safe area is ok)
    cx = min(max(cx, r * 1.05), ctx.W - r * 1.05)
    cy = min(max(cy, r * 1.05), ctx.H - r * 1.05)
    D.drop_shadow(
        ctx.canvas,
        (cx - r * 0.9, cy - r * 0.9, cx + r * 0.9, cy + r * 0.9),
        r * 0.9,
        blur=16 * u,
        offset=(0, 10 * u),
        opacity=0.3,
    )
    D._composite_clipped(ctx.canvas, layer, (int(cx - c), int(cy - c)))


# ─────────────────────────────────────────────────────────────────────────────
# The copy column: eyebrow → headline → description → CTA
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ColumnStyle:
    align: str = "left"
    head_role: str = "display"
    head_color: tuple = (255, 255, 255)
    head_max: float = 118
    head_min: float = 44
    head_spacing: float = 1.1
    head_max_lines: int = 5
    desc_color: tuple = (255, 255, 255, 220)
    desc_max: float = 38
    desc_min: float = 25
    desc_max_lines: int = 3
    desc_share: float = 0.26
    eyebrow_mode: str = "pill"  # pill | text | none
    eyebrow_bg: tuple = (255, 255, 255, 46)
    eyebrow_fg: tuple = (255, 255, 255)
    eyebrow_size: float = 22
    cta_mode: str = "button"  # button | link | none
    cta_bg: tuple = (255, 255, 255)
    cta_fg: Optional[tuple] = None
    cta_size: float = 27
    cta_gradient: Optional[Tuple[RGB, RGB]] = None


def _eyebrow_height(ctx: Ctx, style: ColumnStyle) -> float:
    s = style.eyebrow_size * ctx.u
    return s * 2.05 if style.eyebrow_mode == "pill" else s * 1.25


def draw_column(ctx: Ctx, box: Box, style: ColumnStyle, valign: str = "bottom") -> Box:
    """Lay out and draw the copy stack inside *box*. Returns the used box."""
    u = ctx.u
    x0, y0, x1, y1 = box
    width = x1 - x0
    avail = y1 - y0
    c = ctx.c
    k = ctx.k
    if k != 1.0:
        style = ColumnStyle(
            **{
                **style.__dict__,
                "head_max": style.head_max * k,
                "desc_max": style.desc_max * k,
                "desc_min": style.desc_min * k,
                "eyebrow_size": style.eyebrow_size * k,
                "cta_size": style.cta_size * k,
            }
        )

    eyebrow = c.eyebrow if style.eyebrow_mode != "none" else ""
    eh = _eyebrow_height(ctx, style) if eyebrow else 0.0
    ge = 30 * u if eyebrow else 0.0

    has_cta = style.cta_mode != "none" and bool(ctx.cta_text)
    ch = (
        (style.cta_size * u * (2.55 if style.cta_mode == "button" else 1.6))
        if has_cta
        else 0.0
    )
    gc = 46 * u if has_cta else 0.0

    desc_block: Optional[TextBlock] = None
    gd = 0.0

    def build_desc():
        if not c.description:
            return None
        return fit_text(
            c.description,
            ctx.font("body"),
            width * (0.94 if style.align == "left" else 0.9),
            max(style.desc_min * u * 1.4, avail * style.desc_share),
            int(style.desc_max * u),
            int(style.desc_min * u),
            style.desc_max_lines,
            1.38,
        )

    desc_block = build_desc()
    if desc_block is not None:
        gd = 26 * u

    def head_room() -> float:
        dh = desc_block.height if desc_block is not None else 0.0
        return avail - eh - ge - dh - gd - ch - gc

    if desc_block is not None and head_room() < style.head_min * u * 1.3:
        desc_block, gd = None, 0.0  # sacrifice body copy before the headline

    head = fit_text(
        c.headline,
        ctx.font(style.head_role),
        width,
        max(style.head_min * u * 1.2, head_room()),
        int(style.head_max * u),
        int(style.head_min * u),
        style.head_max_lines,
        style.head_spacing,
        balanced=True,
    )
    dh = desc_block.height if desc_block is not None else 0.0
    total = eh + ge + head.height + gd + dh + gc + ch
    if valign == "bottom":
        y = y1 - total
    elif valign == "center":
        y = y0 + (avail - total) / 2
    else:
        y = y0
    y = max(y, y0)
    top = y

    ax = {"left": x0, "center": x0 + width / 2, "right": x1}[style.align]
    if eyebrow:
        text = eyebrow.upper()
        if style.eyebrow_mode == "pill":
            pill(
                ctx,
                text,
                (ax, y),
                style.eyebrow_size,
                style.eyebrow_bg,
                style.eyebrow_fg,
                style.align,
                max_width=width,
            )
        else:
            s = style.eyebrow_size * u
            b, _ = fit_label(ctx, text, "heading", s, width, 0.16)
            paint_text(ctx, b, (x0, y), style.eyebrow_fg, style.align, width)
        y += eh + ge

    paint_text(ctx, head, (x0, y), style.head_color, style.align, width)
    y += head.height + gd

    if desc_block is not None:
        paint_text(ctx, desc_block, (x0, y), style.desc_color, style.align, width)
        y += desc_block.height

    if has_cta:
        y += gc
        if style.cta_mode == "button":
            cta_button(
                ctx,
                (ax, y),
                style.cta_size,
                style.cta_bg[:3],
                style.cta_fg,
                style.align,
                gradient=style.cta_gradient,
                max_width=width,
            )
        else:
            cta_link(
                ctx,
                (ax, y),
                style.cta_size,
                style.cta_bg[:3],
                style.align,
                max_width=width,
            )
        y += ch
    return (x0, top, x1, y)


def text_on(bg: RGB) -> RGB:
    return readable_on(bg, (255, 255, 255), (17, 17, 17))


__all__ = [
    "Ctx",
    "ColumnStyle",
    "brand_mark",
    "cta_button",
    "cta_button_size",
    "cta_link",
    "draw_column",
    "paint_text",
    "pill",
    "sticker",
    "text_on",
    "text_width",
    "load_font",
]
