"""Drawing primitives on RGBA canvases (gradients, glows, shadows, shapes)."""

from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from gcf.creative.color import RGB

Box = Tuple[float, float, float, float]


def _ibox(box: Box) -> Tuple[int, int, int, int]:
    return tuple(int(round(v)) for v in box)  # type: ignore[return-value]


# ─────────────────────────────────────────────────────────────────────────────
# Backgrounds
# ─────────────────────────────────────────────────────────────────────────────


def linear_gradient(
    size: Tuple[int, int], stops: Sequence[RGB], angle: float = 135.0
) -> Image.Image:
    """Multi-stop linear gradient; *angle* in degrees (CSS convention).

    Computed on a small grid and upscaled — gradients are smooth, so this is
    visually identical and ~50× faster than per-pixel maths at full size.
    """
    w, h = size
    stops = list(stops) or [(0, 0, 0)]
    if len(stops) == 1:
        return Image.new("RGBA", size, (*stops[0], 255))
    k = min(1.0, 384 / max(w, h))
    sw, sh = max(2, int(w * k)), max(2, int(h * k))
    rad = math.radians(angle - 90)
    dx, dy = math.cos(rad), math.sin(rad)
    ys, xs = np.ogrid[0:sh, 0:sw]
    xs = (xs.astype(np.float32) + 0.5) / sw * w
    ys = (ys.astype(np.float32) + 0.5) / sh * h
    proj = (xs - w / 2) * dx + (ys - h / 2) * dy
    half = (abs(w * dx) + abs(h * dy)) / 2 or 1.0
    t = np.clip((proj / half + 1) / 2, 0, 1)
    arr = np.asarray(stops, dtype=np.float32)
    pos = np.linspace(0, 1, len(stops), dtype=np.float32)
    out = np.empty((sh, sw, 3), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, pos, arr[:, c])
    small = Image.fromarray(out.round().astype(np.uint8), "RGB")
    return small.resize((w, h), Image.Resampling.BILINEAR).convert("RGBA")


@lru_cache(maxsize=16)
def _glow_base(strength_q: int) -> Image.Image:
    base = 256
    ys, xs = np.ogrid[0:base, 0:base]
    r = base / 2
    d = np.sqrt((xs + 0.5 - r) ** 2 + (ys + 0.5 - r) ** 2) / r
    a = np.clip(1 - d, 0, 1) ** 2 * (255 * strength_q / 100)
    return Image.fromarray(a.astype(np.uint8), "L")


def radial_glow(
    canvas: Image.Image,
    center: Tuple[float, float],
    radius: float,
    color: RGB,
    strength: float = 0.6,
) -> None:
    """Soft radial light (smooth falloff) composited onto *canvas*.

    Only the visible part of the glow is rasterised, so huge glows are cheap.
    """
    r = max(2, int(radius))
    cx, cy = center
    x0, y0 = int(cx - r), int(cy - r)
    size = 2 * r
    cw, ch = canvas.size
    vx0, vy0 = max(0, x0), max(0, y0)
    vx1, vy1 = min(cw, x0 + size), min(ch, y0 + size)
    if vx1 <= vx0 or vy1 <= vy0:
        return
    base = _glow_base(int(round(strength * 100)))
    k = base.width / size
    box = ((vx0 - x0) * k, (vy0 - y0) * k, (vx1 - x0) * k, (vy1 - y0) * k)
    mask = base.resize((vx1 - vx0, vy1 - vy0), Image.Resampling.BILINEAR, box=box)
    layer = Image.new("RGBA", mask.size, (*color, 0))
    layer.putalpha(mask)
    canvas.alpha_composite(layer, (vx0, vy0))


def fast_blur(img: Image.Image, radius: float) -> Image.Image:
    """Gaussian blur computed at reduced resolution for large radii."""
    f = max(1, min(8, int(radius / 3)))
    if radius <= 6 or f == 1 or img.width < f * 4 or img.height < f * 4:
        return img.filter(ImageFilter.GaussianBlur(radius))
    small = img.reduce(f).filter(ImageFilter.GaussianBlur(radius / f))
    return small.resize(img.size, Image.Resampling.BILINEAR)


@lru_cache(maxsize=8)
def _noise_tile(amount_q: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0, 255 * amount_q / 1000, (256, 256)).astype(np.int16)


def add_grain(canvas: Image.Image, amount: float = 0.035, seed: int = 0) -> None:
    """Subtle film grain — makes flat digital gradients feel premium."""
    if amount <= 0:
        return
    w, h = canvas.size
    tile = _noise_tile(int(round(amount * 1000)), seed % 4)
    noise = np.tile(tile, (h // 256 + 1, w // 256 + 1))[:h, :w]
    arr = np.asarray(canvas.convert("RGB"), dtype=np.int16)
    arr += noise[..., None]
    np.clip(arr, 0, 255, out=arr)
    canvas.paste(Image.fromarray(arr.astype(np.uint8), "RGB").convert(canvas.mode))


def _composite_clipped(
    canvas: Image.Image, layer: Image.Image, dest: Tuple[int, int]
) -> None:
    """alpha_composite that tolerates layers partially outside the canvas."""
    x, y = dest
    cw, ch = canvas.size
    lw, lh = layer.size
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(lw, cw - x), min(lh, ch - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    part = layer.crop((sx0, sy0, sx1, sy1))
    canvas.alpha_composite(part, (x + sx0, y + sy0))


# ─────────────────────────────────────────────────────────────────────────────
# Shapes
# ─────────────────────────────────────────────────────────────────────────────


def shape_layer(size: Tuple[int, int]) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    return layer, ImageDraw.Draw(layer)


def rounded_rect(
    canvas: Image.Image,
    box: Box,
    radius: float,
    fill=None,
    outline=None,
    width: int = 0,
) -> None:
    x0, y0, x1, y1 = _ibox(box)
    pad = width + 2
    layer, d = shape_layer((x1 - x0 + 2 * pad, y1 - y0 + 2 * pad))
    d.rounded_rectangle(
        (pad, pad, pad + x1 - x0, pad + y1 - y0),
        radius=int(radius),
        fill=fill,
        outline=outline,
        width=int(width),
    )
    _composite_clipped(canvas, layer, (x0 - pad, y0 - pad))


def ellipse(canvas: Image.Image, box: Box, fill=None, outline=None, width=0) -> None:
    x0, y0, x1, y1 = _ibox(box)
    pad = int(width) + 2
    layer, d = shape_layer((x1 - x0 + 2 * pad, y1 - y0 + 2 * pad))
    d.ellipse(
        (pad, pad, pad + x1 - x0, pad + y1 - y0),
        fill=fill,
        outline=outline,
        width=int(width),
    )
    _composite_clipped(canvas, layer, (x0 - pad, y0 - pad))


def drop_shadow(
    canvas: Image.Image,
    box: Box,
    radius: float,
    blur: float,
    offset: Tuple[float, float] = (0, 0),
    color: RGB = (0, 0, 0),
    opacity: float = 0.35,
) -> None:
    """Blurred rounded-rect shadow drawn *below* whatever is painted next."""
    x0, y0, x1, y1 = _ibox(box)
    b = int(blur * 2.5) + 2
    w, h = x1 - x0 + 2 * b, y1 - y0 + 2 * b
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (b, b, b + x1 - x0, b + y1 - y0),
        radius=int(radius),
        fill=int(255 * opacity),
    )
    mask = fast_blur(mask, blur)
    layer = Image.new("RGBA", (w, h), (*color, 0))
    layer.putalpha(mask)
    _composite_clipped(
        canvas, layer, (x0 - b + int(offset[0]), y0 - b + int(offset[1]))
    )


def dot_grid(
    canvas: Image.Image,
    box: Box,
    spacing: float,
    radius: float,
    color,
) -> None:
    x0, y0, x1, y1 = _ibox(box)
    layer, d = shape_layer((x1 - x0, y1 - y0))
    y = spacing / 2
    while y < y1 - y0:
        x = spacing / 2
        while x < x1 - x0:
            d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
            x += spacing
        y += spacing
    _composite_clipped(canvas, layer, (x0, y0))


def dashed_line(
    canvas: Image.Image,
    start: Tuple[float, float],
    end: Tuple[float, float],
    dash: float,
    gap: float,
    width: float,
    color,
) -> None:
    (sx, sy), (ex, ey) = start, end
    length = math.hypot(ex - sx, ey - sy)
    if length == 0:
        return
    pad = int(width) + 2
    x0, y0 = int(min(sx, ex)) - pad, int(min(sy, ey)) - pad
    layer, d = shape_layer(
        (int(abs(ex - sx)) + 2 * pad + 1, int(abs(ey - sy)) + 2 * pad + 1)
    )
    ux, uy = (ex - sx) / length, (ey - sy) / length
    pos = 0.0
    while pos < length:
        a = pos
        b = min(pos + dash, length)
        d.line(
            (sx - x0 + ux * a, sy - y0 + uy * a, sx - x0 + ux * b, sy - y0 + uy * b),
            fill=color,
            width=int(width),
        )
        pos += dash + gap
    _composite_clipped(canvas, layer, (x0, y0))


# ─────────────────────────────────────────────────────────────────────────────
# Images
# ─────────────────────────────────────────────────────────────────────────────


def load_image(path: Optional[str]) -> Optional[Image.Image]:
    """Load a local image (returns ``None`` if missing/unreadable)."""
    if not path:
        return None
    p = Path(str(path)).expanduser()
    if not p.is_file():
        return None
    try:
        with Image.open(p) as im:
            im = ImageOps.exif_transpose(im)
            return im.convert("RGBA")
    except Exception:
        return None


def paste_cover(
    canvas: Image.Image,
    image: Image.Image,
    box: Box,
    radius: float = 0,
    focus: Tuple[float, float] = (0.5, 0.5),
) -> None:
    """Paste *image* cropped to cover *box*, optionally with rounded corners."""
    x0, y0, x1, y1 = _ibox(box)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    if image.size == (w, h):
        fitted = image.copy() if image.mode == "RGBA" else image.convert("RGBA")
    else:
        fitted = ImageOps.fit(
            image, (w, h), Image.Resampling.BICUBIC, centering=focus
        ).convert("RGBA")
    if radius > 0:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, w, h), radius=int(radius), fill=255
        )
        alpha = fitted.getchannel("A")
        fitted.putalpha(
            Image.fromarray(np.minimum(np.asarray(alpha), np.asarray(mask)))
        )
    _composite_clipped(canvas, fitted, (x0, y0))


def paste_contain(canvas: Image.Image, image: Image.Image, box: Box) -> Box:
    """Paste *image* scaled to fit inside *box* (centered). Returns used box."""
    x0, y0, x1, y1 = _ibox(box)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    im = image.copy()
    im.thumbnail((w, h), Image.Resampling.LANCZOS)
    ox = x0 + (w - im.width) // 2
    oy = y0 + (h - im.height) // 2
    _composite_clipped(canvas, im, (ox, oy))
    return (ox, oy, ox + im.width, oy + im.height)


# ─────────────────────────────────────────────────────────────────────────────
# Generative art (used when no product photo is supplied)
# ─────────────────────────────────────────────────────────────────────────────


def generative_art(
    size: Tuple[int, int],
    palette: Sequence[RGB],
    seed: int,
    style: Optional[str] = None,
    focus: Tuple[float, float, float, float] = (0.1, 0.1, 0.9, 0.9),
) -> Image.Image:
    """Deterministic abstract composition in brand colours.

    Styles: ``orbs`` (soft spheres), ``arcs`` (concentric rainbow arcs),
    ``blocks`` (Bauhaus-like geometry). The *seed* makes every creative unique
    yet reproducible.
    """
    rng = random.Random(seed)
    w, h = size
    style = style or rng.choice(["orbs", "arcs", "blocks"])
    base, c1, c2, c3 = (list(palette) + list(palette) * 3)[:4]
    img = linear_gradient(size, [base, c1], angle=rng.choice([120, 150, 200, 240]))
    s = min(w, h)

    if style == "orbs":
        for _ in range(3):
            r = rng.uniform(0.25, 0.45) * s
            cx, cy = rng.uniform(0.1, 0.9) * w, rng.uniform(0.1, 0.9) * h
            radial_glow(img, (cx, cy), r * 1.6, rng.choice([c2, c3]), 0.55)
        fx0, fy0, fx1, fy1 = focus
        span = min(fx1 - fx0, fy1 - fy0)
        rmax = 0.26 if span >= 0.7 else 0.17
        for i in range(3):
            r = rng.uniform(rmax * 0.5, rmax) * s
            cx = rng.uniform(fx0 + 0.1, fx1 - 0.1) * w
            cy = rng.uniform(fy0 + 0.1, fy1 - 0.1) * h
            sphere = _sphere(int(2 * r), [c1, c2, c3][i % 3])
            _composite_clipped(img, sphere, (int(cx - r), int(cy - r)))
    elif style == "arcs":
        cx = rng.choice([0, w])
        cy = rng.choice([h, h * 0.8])
        colors = [c2, c3, c1, (255, 255, 255)]
        band = s * rng.uniform(0.09, 0.13)
        r = s * 1.05
        i = 0
        while r > band:
            ellipse(img, (cx - r, cy - r, cx + r, cy + r), fill=(*colors[i % 4], 255))
            r -= band
            i += 1
    else:  # blocks
        cols, rows = rng.choice([(2, 2), (3, 2), (2, 3), (3, 3)])
        cw, ch = w / cols, h / rows
        for cxi in range(cols):
            for ryi in range(rows):
                bx, by = cxi * cw, ryi * ch
                col = rng.choice([c1, c2, c3, base])
                kind = rng.choice(["circle", "quarter", "half", "square"])
                layer, d = shape_layer((int(cw) + 1, int(ch) + 1))
                d.rectangle((0, 0, cw, ch), fill=(*rng.choice([base, c1]), 255))
                m = min(cw, ch)
                if kind == "circle":
                    d.ellipse(
                        (
                            (cw - m * 0.8) / 2,
                            (ch - m * 0.8) / 2,
                            (cw + m * 0.8) / 2,
                            (ch + m * 0.8) / 2,
                        ),
                        fill=(*col, 255),
                    )
                elif kind == "quarter":
                    ox, oy = rng.choice([(0, 0), (cw, 0), (0, ch), (cw, ch)])
                    d.ellipse((ox - m, oy - m, ox + m, oy + m), fill=(*col, 255))
                elif kind == "half":
                    d.pieslice(
                        (0, ch / 2 - cw / 2, cw, ch / 2 + cw / 2),
                        rng.choice([0, 90, 180, 270]),
                        rng.choice([0, 90, 180, 270]) + 180,
                        fill=(*col, 255),
                    )
                else:
                    d.rounded_rectangle(
                        (cw * 0.2, ch * 0.2, cw * 0.8, ch * 0.8),
                        radius=int(m * 0.12),
                        fill=(*col, 255),
                    )
                _composite_clipped(img, layer, (int(bx), int(by)))
    return img


def _sphere(d: int, color: RGB) -> Image.Image:
    """Shaded sphere with a specular highlight (fake 3D).

    Only a ≤640px master is cached (a few MB in total); each call returns a
    fresh resize, so callers may mutate the result.
    """
    d = max(4, int(d))
    master = _sphere_master(min(d, 640), tuple(color))
    if master.width == d:
        return master.copy()
    return master.resize((d, d), Image.Resampling.BICUBIC)


@lru_cache(maxsize=24)
def _sphere_master(d: int, color: RGB) -> Image.Image:
    ys, xs = np.mgrid[0:d, 0:d].astype(np.float32) + 0.5
    r = d / 2
    nx, ny = (xs - r) / r, (ys - r) / r
    dist = np.sqrt(nx**2 + ny**2)
    inside = dist <= 1
    lx, ly = -0.45, -0.55  # light from top-left
    nz = np.sqrt(np.clip(1 - nx**2 - ny**2, 0, 1))
    shade = np.clip(nx * lx + ny * ly + nz * 0.7, 0, 1)
    base = np.asarray(color, dtype=np.float32)
    rgb = base[None, None, :] * (0.55 + 0.6 * shade[..., None])
    spec = np.clip(1 - np.sqrt((nx + 0.35) ** 2 + (ny + 0.4) ** 2) / 0.35, 0, 1) ** 2
    rgb = rgb + 255 * 0.55 * spec[..., None]
    rgb = np.clip(rgb, 0, 255)
    edge = np.clip((1 - dist) * r / 1.5, 0, 1)  # anti-aliased rim
    alpha = np.where(inside, 255 * edge, 0)
    arr = np.dstack([rgb, alpha]).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")
