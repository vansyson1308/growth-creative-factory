"""Designer templates. Each adapts its layout to square, portrait, story and
landscape canvases and draws entirely from the brand kit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from PIL import Image, ImageDraw

from gcf.creative import draw as D
from gcf.creative.color import contrast_ratio, darken, lighten, mix
from gcf.creative.components import (
    ColumnStyle,
    Ctx,
    brand_mark,
    draw_column,
    paint_text,
    sticker,
    text_on,
)
from gcf.creative.text import fit_text


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    description: str
    render: Callable[[Ctx], None]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Bold gradient
# ─────────────────────────────────────────────────────────────────────────────


def _bold(ctx: Ctx) -> None:
    W, H, u = ctx.W, ctx.H, ctx.u
    rng = ctx.rng
    ctx.canvas = D.linear_gradient(
        (W, H),
        [ctx.primary, mix(ctx.primary, ctx.secondary, 0.55), ctx.secondary],
        angle=rng.choice([135, 150, 160]),
    )
    cv = ctx.canvas
    big = max(W, H)
    D.radial_glow(cv, (W * 0.88, H * 0.08), big * 0.55, lighten(ctx.accent, 0.1), 0.42)
    D.radial_glow(cv, (W * 0.05, H * 0.98), big * 0.6, darken(ctx.secondary, 0.35), 0.5)

    if ctx.is_wide:
        rc, R = (W * 0.84, H * 0.5), H * 0.62
    else:
        rc, R = (W * 0.98, H * 0.16 if ctx.is_tall else H * 0.1), min(W, H) * 0.58
    for k, a in ((1.0, 46), (0.74, 30), (1.3, 20)):
        r = R * k
        D.ellipse(
            cv,
            (rc[0] - r, rc[1] - r, rc[0] + r, rc[1] + r),
            outline=(255, 255, 255, a),
            width=int(3 * u),
        )
    sx0, sy0, sx1, sy1 = ctx.safe
    deco_bottom = 0.0

    if ctx.is_wide:
        s = H * 0.3
        if ctx.image is None:
            for dx, dy, k, col in (
                (0.0, 0.0, 1.0, ctx.accent),
                (-0.62, 0.55, 0.52, lighten(ctx.secondary, 0.25)),
                (0.55, -0.62, 0.38, lighten(ctx.primary, 0.35)),
            ):
                r = s * k
                sp = D._sphere(int(2 * r), col)
                D._composite_clipped(
                    cv, sp, (int(rc[0] + dx * s - r), int(rc[1] + dy * s - r))
                )
        else:
            ph = H * 0.72
            box = (rc[0] - ph * 0.5, H / 2 - ph / 2, rc[0] + ph * 0.5, H / 2 + ph / 2)
            D.drop_shadow(
                cv, box, ctx.r(36), blur=30 * u, offset=(0, 18 * u), opacity=0.4
            )
            D.paste_cover(cv, ctx.image, box, radius=ctx.r(36))
    elif ctx.image is None:
        r = min(W, H) * (0.15 if ctx.is_tall else 0.12)
        if not ctx.badge:
            sp = D._sphere(int(2 * r), lighten(ctx.accent, 0.05))
            D._composite_clipped(cv, sp, (int(sx1 - r * 1.7), int(sy0 - r * 0.25)))
            deco_bottom = sy0 + r * 1.75
    else:
        ph = (sy1 - sy0) * (0.42 if ctx.is_tall else 0.36)
        box = (sx1 - ph, sy0 + 90 * u, sx1, sy0 + 90 * u + ph)
        D.drop_shadow(cv, box, ctx.r(32), blur=28 * u, offset=(0, 16 * u), opacity=0.4)
        D.paste_cover(cv, ctx.image, box, radius=ctx.r(32))
        deco_bottom = box[3]

    mark = brand_mark(ctx, (sx0, sy0), (255, 255, 255), 46, mono_bg=ctx.accent)

    if ctx.badge:
        br = 118 if not ctx.is_wide else 96
        if not ctx.is_wide:
            deco_bottom = max(deco_bottom, sy0 + br * u * 1.95)
        bx = sx1 - br * u * 0.95 if not ctx.is_wide else W * 0.84 + H * 0.22
        by = sy0 + br * u * 0.95
        if ctx.is_wide:
            bx, by = rc[0] + H * 0.26, H * 0.24
        sticker(ctx, ctx.badge, (bx, by), br, ctx.accent)

    col_right = sx0 + (sx1 - sx0) * 0.6 if ctx.is_wide else sx1
    style = ColumnStyle(
        head_color=(255, 255, 255),
        desc_color=(255, 255, 255, 222),
        eyebrow_bg=(255, 255, 255, 44),
        eyebrow_fg=(255, 255, 255),
        cta_bg=ctx.accent,
        head_max=96 if ctx.is_wide else 124,
    )
    top = max(mark[3] + 60 * u, deco_bottom + 36 * u)
    draw_column(
        ctx,
        (sx0, top, col_right, sy1),
        style,
        valign="center" if ctx.is_wide else "bottom",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Editorial (serif, paper, circle window)
# ─────────────────────────────────────────────────────────────────────────────


def _circle_window(ctx: Ctx, center, r: float) -> None:
    cx, cy = center
    size = int(2 * r)
    vis = ctx.visual((size, size), style="orbs")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    vis.putalpha(mask)
    D._composite_clipped(ctx.canvas, vis, (int(cx - r), int(cy - r)))


def _editorial(ctx: Ctx) -> None:
    W, H, u = ctx.W, ctx.H, ctx.u
    ctx.canvas = Image.new("RGBA", (W, H), (*ctx.paper, 255))
    cv = ctx.canvas
    D.radial_glow(
        cv, (W * 0.9, H * 0.95), max(W, H) * 0.7, lighten(ctx.primary, 0.75), 0.35
    )
    sx0, sy0, sx1, sy1 = ctx.safe
    muted = mix(ctx.ink, ctx.paper, 0.38)

    # Frame
    inset = 26 * u
    D.rounded_rect(
        cv,
        (inset, inset, W - inset, H - inset),
        ctx.r(18),
        outline=(*ctx.ink, 38),
        width=int(2 * u),
    )

    mark = brand_mark(ctx, (sx0, sy0), ctx.ink, 42, mono_bg=ctx.primary)
    meta = ctx.brand.handle
    if meta:
        from gcf.creative.components import line_block

        s = 20 * u
        b = line_block(ctx, meta.upper(), "heading", s, tracking=s * 0.14)
        paint_text(
            ctx, b, (sx1 - b.width, mark[1] + (mark[3] - mark[1] - b.height) / 2), muted
        )
    rule_y = mark[3] + 34 * u
    D.rounded_rect(cv, (sx0, rule_y, sx1, rule_y + 2 * u), 0, fill=(*ctx.ink, 60))

    style = ColumnStyle(
        head_role="serif",
        head_color=ctx.ink,
        head_spacing=1.12,
        head_max=112 if not ctx.is_wide else 88,
        head_min=40,
        desc_color=muted,
        eyebrow_mode="text",
        eyebrow_fg=ctx.primary,
        eyebrow_size=21,
        cta_mode="link",
        cta_bg=ctx.primary,
        cta_size=28,
    )

    if ctx.is_wide:
        r = (sy1 - rule_y) * 0.5
        center = (sx1 - r, (rule_y + sy1) / 2 + 10 * u)
        D.ellipse(
            cv,
            (
                center[0] - r * 1.1,
                center[1] - r * 1.1,
                center[0] + r * 1.1,
                center[1] + r * 1.1,
            ),
            outline=(*ctx.primary, 90),
            width=int(2 * u),
        )
        _circle_window(ctx, center, r)
        box = (sx0, rule_y + 40 * u, center[0] - r * 1.25, sy1)
        draw_column(ctx, box, style, valign="center")
        badge_c = (center[0] - r * 0.78, center[1] - r * 0.72)
    else:
        r = min(W, H) * (0.3 if ctx.is_tall else 0.235)
        center = (
            (sx1 - r * 0.5, sy1 - r * 0.5)
            if not ctx.is_tall
            else (sx1 - r * 0.7, sy1 - r * 0.75)
        )
        D.ellipse(
            cv,
            (
                center[0] - r * 1.12,
                center[1] - r * 1.12,
                center[0] + r * 1.12,
                center[1] + r * 1.12,
            ),
            outline=(*ctx.primary, 90),
            width=int(2 * u),
        )
        _circle_window(ctx, center, r)
        col_bottom = center[1] - r * 1.22
        box = (sx0, rule_y + 60 * u, sx1 - (0 if ctx.is_tall else 20 * u), col_bottom)
        cta_style = ColumnStyle(
            **{**style.__dict__, "cta_mode": "none", "desc_share": 0.22}
        )
        draw_column(ctx, box, cta_style, valign="top")
        from gcf.creative.components import cta_link

        cta_link(ctx, (sx0, sy1 - 40 * u), 28, ctx.primary)
        badge_c = (center[0] - r * 0.85, center[1] - r * 0.8)
    if ctx.badge:
        sticker(ctx, ctx.badge, badge_c, 84, ctx.accent, rotate=10)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Split (visual panel + copy panel)
# ─────────────────────────────────────────────────────────────────────────────


def _split(ctx: Ctx) -> None:
    W, H, u = ctx.W, ctx.H, ctx.u
    ctx.canvas = Image.new("RGBA", (W, H), (*ctx.paper, 255))
    cv = ctx.canvas
    sx0, sy0, sx1, sy1 = ctx.safe
    muted = mix(ctx.ink, ctx.paper, 0.35)
    style = ColumnStyle(
        head_color=ctx.ink,
        desc_color=muted,
        eyebrow_mode="pill",
        eyebrow_bg=(*lighten(ctx.primary, 0.85), 255),
        eyebrow_fg=darken(ctx.primary, 0.1),
        cta_bg=ctx.primary,
        head_max=104,
        head_min=38,
    )

    if not ctx.is_wide:
        split = H * (0.5 if ctx.is_tall else 0.47 if ctx.aspect < 0.95 else 0.43)
        cv.alpha_composite(ctx.visual((W, int(split + 80 * u))), (0, 0))
        scrim = D.linear_gradient((W, int(260 * u)), [(0, 0, 0), (0, 0, 0)], 180)
        a = (
            Image.linear_gradient("L")
            .resize((W, int(260 * u)))
            .point(lambda v: int((255 - v) * 0.45))
        )
        scrim.putalpha(a)
        cv.alpha_composite(scrim, (0, 0))
        brand_mark(ctx, (sx0, sy0), (255, 255, 255), 44, mono_bg=ctx.accent, chip=True)
        panel_top = split
        D.drop_shadow(
            cv,
            (0, panel_top, W, H + 200 * u),
            ctx.r(56),
            blur=30 * u,
            offset=(0, -6 * u),
            opacity=0.25,
        )
        D.rounded_rect(
            cv, (0, panel_top, W, H + 200 * u), ctx.r(56), fill=(*ctx.paper, 255)
        )
        if ctx.badge:
            sticker(
                ctx, ctx.badge, (sx1 - 110 * u, panel_top - 10 * u), 100, ctx.accent
            )
        # Stories: Meta keeps ~13% at the bottom for its UI; the default 19%
        # safe inset would leave the copy panel half empty.
        bottom = max(sy1, H * 0.87) if ctx.is_tall else sy1
        draw_column(
            ctx,
            (sx0, panel_top + 64 * u, sx1, bottom),
            style,
            valign="center",
        )
        return

    # Side-by-side (square / landscape / wide)
    vis_w = W * (0.46 if not ctx.is_wide else 0.44)
    left_visual = not ctx.is_wide
    vx0 = 0 if left_visual else W - vis_w
    cv.alpha_composite(ctx.visual((int(vis_w), H)), (int(vx0), 0))
    # Soft edge between panels
    edge_x = vis_w if left_visual else W - vis_w
    D.drop_shadow(
        cv,
        (edge_x - 4 * u, -50 * u, edge_x + 4 * u, H + 50 * u),
        0,
        blur=24 * u,
        opacity=0.25,
    )
    if left_visual:
        D.rounded_rect(cv, (edge_x, -10, W + 10, H + 10), 0, fill=(*ctx.paper, 255))
        tx0, tx1 = edge_x + 64 * u, sx1
    else:
        D.rounded_rect(cv, (-10, -10, edge_x, H + 10), 0, fill=(*ctx.paper, 255))
        tx0, tx1 = sx0, edge_x - 64 * u
    mark = brand_mark(ctx, (tx0, sy0), ctx.ink, 40, mono_bg=ctx.primary)
    if ctx.badge:
        sticker(
            ctx,
            ctx.badge,
            (edge_x, sy1 - 100 * u) if left_visual else (edge_x, sy0 + 100 * u),
            92,
            ctx.accent,
        )
    draw_column(ctx, (tx0, mark[3] + 50 * u, tx1, sy1), style, valign="center")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Glass spotlight
# ─────────────────────────────────────────────────────────────────────────────


def _glass(ctx: Ctx) -> None:
    W, H, u = ctx.W, ctx.H, ctx.u
    rng = ctx.rng
    ctx.canvas = D.linear_gradient(
        (W, H), [ctx.dark, darken(ctx.secondary, 0.7)], angle=160
    )
    cv = ctx.canvas
    big = max(W, H)
    spots = [
        ((rng.uniform(0.05, 0.3) * W, rng.uniform(0.05, 0.3) * H), ctx.primary, 0.9),
        ((rng.uniform(0.7, 0.95) * W, rng.uniform(0.6, 0.95) * H), ctx.secondary, 0.85),
        ((rng.uniform(0.6, 0.9) * W, rng.uniform(0.05, 0.25) * H), ctx.accent, 0.45),
    ]
    for c, col, st in spots:
        D.radial_glow(cv, c, big * 0.55, col, st)
    if ctx.image is not None:
        cv.alpha_composite(
            Image.blend(ctx.visual((W, H)).convert("RGBA"), cv, 0.55), (0, 0)
        )
    else:
        for px, py, k, col in (
            (0.16, 0.2, 0.13, ctx.accent),
            (0.86, 0.8, 0.17, ctx.primary),
        ):
            r = min(W, H) * k
            sp = D._sphere(int(2 * r), lighten(col, 0.1))
            D._composite_clipped(cv, sp, (int(px * W - r), int(py * H - r)))
    D.dot_grid(cv, (0, 0, W, H), 36 * u, 1.6 * u, (255, 255, 255, 22))

    sx0, sy0, sx1, sy1 = ctx.safe
    mark = brand_mark(
        ctx, (W / 2, sy0), (255, 255, 255), 44, align="center", mono_bg=ctx.primary
    )

    if ctx.is_wide:
        cw, chh = (sx1 - sx0) * 0.78, (sy1 - mark[3]) * 0.86
    elif ctx.is_tall:
        cw, chh = (sx1 - sx0), (sy1 - mark[3]) * 0.8
    else:
        cw, chh = (sx1 - sx0) * 0.94, (sy1 - mark[3]) * 0.86
    cx0 = (W - cw) / 2
    cy0 = mark[3] + ((sy1 - mark[3]) - chh) / 2 + 12 * u
    card = (cx0, cy0, cx0 + cw, cy0 + chh)
    rad = ctx.r(44)
    D.drop_shadow(cv, card, rad, blur=40 * u, offset=(0, 24 * u), opacity=0.45)
    region = D.fast_blur(cv.crop(tuple(int(v) for v in card)), 34 * u)
    D.paste_cover(cv, region, card, radius=rad)
    D.rounded_rect(
        cv,
        card,
        rad,
        fill=(255, 255, 255, 30),
        outline=(255, 255, 255, 80),
        width=int(2 * u),
    )
    # Specular sheen along the top edge of the glass
    sheen = D.linear_gradient(
        (int(cw), int(chh * 0.5)), [(255, 255, 255), (255, 255, 255)], 180
    )
    sheen.putalpha(
        Image.linear_gradient("L")
        .resize((int(cw), int(chh * 0.5)))
        .point(lambda v: int((255 - v) * 0.1))
    )
    D.paste_cover(cv, sheen, (cx0, cy0, cx0 + cw, cy0 + chh * 0.5), radius=rad)

    pad = 64 * u if not ctx.is_wide else 56 * u
    style = ColumnStyle(
        align="center",
        head_color=(255, 255, 255),
        desc_color=(255, 255, 255, 210),
        eyebrow_bg=(255, 255, 255, 36),
        eyebrow_fg=(255, 255, 255),
        cta_bg=ctx.primary,
        cta_gradient=(ctx.primary, ctx.secondary),
        cta_fg=(255, 255, 255),
        head_max=112 if not ctx.is_wide else 84,
    )
    if contrast_ratio(mix(ctx.primary, ctx.secondary, 0.5), ctx.dark) < 2.2:
        # Brand gradient would vanish on the dark stage (e.g. monochrome kits)
        style.cta_gradient = None
        style.cta_bg = ctx.accent
        style.cta_fg = text_on(ctx.accent)
    draw_column(
        ctx,
        (cx0 + pad, cy0 + pad, cx0 + cw - pad, cy0 + chh - pad),
        style,
        valign="center",
    )
    if ctx.badge:
        sticker(
            ctx, ctx.badge, (cx0 + cw - 30 * u, cy0 + 20 * u), 88, ctx.accent, rotate=12
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Promo ticket
# ─────────────────────────────────────────────────────────────────────────────


def _ticket_layer(
    w: int, h: int, radius: float, notch: float, split: float, vertical: bool, fill
):
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w, h), radius=int(radius), fill=fill)
    clear = (0, 0, 0, 0)
    if vertical:  # notches on the left/right edges at y=split
        d.ellipse((-notch, split - notch, notch, split + notch), fill=clear)
        d.ellipse((w - notch, split - notch, w + notch, split + notch), fill=clear)
    else:  # notches on the top/bottom edges at x=split
        d.ellipse((split - notch, -notch, split + notch, notch), fill=clear)
        d.ellipse((split - notch, h - notch, split + notch, h + notch), fill=clear)
    return layer


def _promo(ctx: Ctx) -> None:
    W, H, u = ctx.W, ctx.H, ctx.u
    rng = ctx.rng
    ctx.canvas = D.linear_gradient(
        (W, H), [ctx.primary, ctx.secondary], angle=rng.choice([120, 200])
    )
    cv = ctx.canvas
    # Diagonal stripes
    stripes, sd = D.shape_layer((W, H))
    step = 70 * u
    x = -H
    while x < W + H:
        sd.line((x, 0, x + H, H), fill=(255, 255, 255, 16), width=int(22 * u))
        x += step
    cv.alpha_composite(stripes)
    # Confetti (kept clear of the brand mark)
    sx0, sy0, sx1, sy1 = ctx.safe
    for _ in range(26):
        px, py = rng.uniform(0, W), rng.uniform(0, H)
        if abs(px - W / 2) < 330 * u and py < sy0 + 110 * u:
            continue
        s = rng.uniform(8, 20) * u
        col = rng.choice([ctx.accent, (255, 255, 255), lighten(ctx.secondary, 0.4)])
        kind = rng.random()
        if kind < 0.45:
            D.ellipse(cv, (px - s, py - s, px + s, py + s), fill=(*col, 200))
        elif kind < 0.75:
            D.ellipse(
                cv,
                (px - s, py - s, px + s, py + s),
                outline=(*col, 200),
                width=int(4 * u),
            )
        else:
            D.rounded_rect(
                cv,
                (px - s, py - s * 0.45, px + s, py + s * 0.45),
                s * 0.4,
                fill=(*col, 210),
            )

    sx0, sy0, sx1, sy1 = ctx.safe
    mark = brand_mark(
        ctx, (W / 2, sy0), (255, 255, 255), 44, align="center", mono_bg=ctx.accent
    )
    lang = ctx.c.language or "en"
    if ctx.badge:
        value = ctx.badge
    else:
        # Never imply a discount that the copy does not state.
        from gcf.dedupe import detect_angle_bucket

        urgent = detect_angle_bucket(ctx.c.headline) == "urgency"
        value = {
            ("en", True): "LAST CALL",
            ("en", False): "NEW",
            ("vi", True): "SẮP HẾT",
            ("vi", False): "MỚI",
        }[(lang if lang in ("en", "vi") else "en", urgent)]
    eyebrow = ctx.c.eyebrow
    if not eyebrow:
        if ctx.badge:
            eyebrow = "Limited-time offer" if lang == "en" else "Ưu đãi có hạn"
        else:
            eyebrow = ctx.brand.name
    white = (255, 255, 255)
    muted = mix(ctx.ink, (255, 255, 255), 0.35)

    top = mark[3] + 48 * u
    vertical = not ctx.is_wide
    tw = (sx1 - sx0) * (1.0 if ctx.is_tall else 0.94 if not ctx.is_wide else 0.9)
    th = (sy1 - top) * (0.94 if not ctx.is_wide else 0.92)
    tx0 = (W - tw) / 2
    ty0 = top + ((sy1 - top) - th) / 2
    split = th * (0.4 if vertical else 0) if vertical else tw * 0.36
    notch = 34 * u
    layer = _ticket_layer(
        int(tw), int(th), ctx.r(36), notch, split, vertical, (*white, 255)
    )
    shadow = D.fast_blur(layer.getchannel("A"), 26 * u).point(lambda v: int(v * 0.35))
    sh = Image.new("RGBA", layer.size, (*darken(ctx.secondary, 0.6), 0))
    sh.putalpha(shadow)
    D._composite_clipped(cv, sh, (int(tx0), int(ty0 + 20 * u)))
    D._composite_clipped(cv, layer, (int(tx0), int(ty0)))

    dash_col = (*mix(ctx.ink, white, 0.7), 255)
    pad = 56 * u
    from gcf.creative.components import line_block

    if vertical:
        D.dashed_line(
            cv,
            (tx0 + notch + 12 * u, ty0 + split),
            (tx0 + tw - notch - 12 * u, ty0 + split),
            16 * u,
            12 * u,
            3 * u,
            dash_col,
        )
        stub = (tx0 + pad, ty0 + pad * 0.8, tx0 + tw - pad, ty0 + split - pad * 0.6)
        body = (tx0 + pad, ty0 + split + pad * 0.8, tx0 + tw - pad, ty0 + th - pad)
    else:
        D.dashed_line(
            cv,
            (tx0 + split, ty0 + notch + 12 * u),
            (tx0 + split, ty0 + th - notch - 12 * u),
            16 * u,
            12 * u,
            3 * u,
            dash_col,
        )
        stub = (tx0 + pad * 0.7, ty0 + pad, tx0 + split - pad * 0.7, ty0 + th - pad)
        body = (tx0 + split + pad, ty0 + pad, tx0 + tw - pad, ty0 + th - pad)

    # Stub: eyebrow + giant value
    s = 22 * u
    eb = line_block(ctx, eyebrow.upper(), "heading", s, tracking=s * 0.16)
    sw = stub[2] - stub[0]
    vb = fit_text(
        value,
        ctx.font("display"),
        sw,
        (stub[3] - stub[1]) - eb.height - 24 * u,
        int(260 * u),
        int(60 * u),
        2,
        0.98,
        True,
    )
    total = eb.height + 24 * u + vb.height
    y = stub[1] + ((stub[3] - stub[1]) - total) / 2
    paint_text(ctx, eb, (stub[0], y), ctx.primary, "center", sw)
    grad_text = vb
    y += eb.height + 24 * u
    # Value in a primary→secondary gradient fill
    tmp = Image.new("L", (int(sw), int(grad_text.height + 20 * u)), 0)
    from gcf.creative.text import draw_block

    draw_block(ImageDraw.Draw(tmp), grad_text, (0, 0), 255, "center", sw)
    fillimg = D.linear_gradient(tmp.size, [ctx.primary, ctx.secondary], angle=90)
    fillimg.putalpha(tmp)
    D._composite_clipped(cv, fillimg, (int(stub[0]), int(y)))

    style = ColumnStyle(
        align="center",
        head_color=ctx.ink,
        desc_color=muted,
        eyebrow_mode="none",
        cta_bg=ctx.primary,
        cta_gradient=(ctx.primary, ctx.secondary),
        cta_fg=(255, 255, 255),
        head_max=84,
        head_min=34,
        desc_max=32,
        desc_share=0.3,
    )
    draw_column(ctx, body, style, valign="center")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Photo overlay
# ─────────────────────────────────────────────────────────────────────────────


def _photo(ctx: Ctx) -> None:
    W, H, u = ctx.W, ctx.H, ctx.u
    focus = (0.5, 0.0, 1.0, 1.0) if ctx.is_wide else (0.3, 0.0, 1.0, 0.42)
    ctx.canvas = ctx.visual((W, H), style="orbs", focus=focus).convert("RGBA")
    cv = ctx.canvas
    # Bottom scrim for legibility (and left scrim for wide formats)
    if ctx.is_wide:
        g = Image.linear_gradient("L").rotate(90, expand=True).resize((W, H))
        alpha = g.point(lambda v: int(min(255, v * 1.05) * 0.86))
    else:
        g = Image.linear_gradient("L").resize((W, H))
        alpha = g.point(lambda v: int(max(0, (v - 70)) / 185 * 235))
    scrim = Image.new("RGBA", (W, H), (*darken(ctx.dark, 0.2), 0))
    scrim.putalpha(alpha)
    cv.alpha_composite(scrim)
    top_scrim = Image.new("RGBA", (W, int(220 * u)), (0, 0, 0, 0))
    top_scrim.putalpha(
        Image.linear_gradient("L")
        .resize((W, int(220 * u)))
        .point(lambda v: int((255 - v) * 0.35))
    )
    cv.alpha_composite(top_scrim)

    sx0, sy0, sx1, sy1 = ctx.safe
    mark = brand_mark(
        ctx, (sx0, sy0), (255, 255, 255), 44, mono_bg=ctx.primary, chip=True
    )
    if ctx.badge:
        sticker(ctx, ctx.badge, (sx1 - 100 * u, sy0 + 90 * u), 100, ctx.accent)
    style = ColumnStyle(
        head_color=(255, 255, 255),
        desc_color=(255, 255, 255, 225),
        eyebrow_bg=(*ctx.accent, 255),
        eyebrow_fg=text_on(ctx.accent),
        cta_bg=(255, 255, 255),
        cta_fg=ctx.ink,
        head_max=112 if not ctx.is_wide else 84,
    )
    right = sx0 + (sx1 - sx0) * 0.58 if ctx.is_wide else sx1
    top = mark[3] + (H * 0.3 if not ctx.is_wide else 50 * u)
    draw_column(ctx, (sx0, top, right, sy1), style, valign="bottom")


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: Dict[str, Template] = {
    t.key: t
    for t in [
        Template(
            "bold",
            "Bold Gradient",
            "Punchy gradient, big type, glowing CTA — scroll-stopper for feeds.",
            _bold,
        ),
        Template(
            "editorial",
            "Editorial",
            "Paper texture, serif headline, circle window — premium & calm.",
            _editorial,
        ),
        Template(
            "split",
            "Split Panel",
            "Visual panel + clean copy panel — product-first storytelling.",
            _split,
        ),
        Template(
            "glass",
            "Glass Spotlight",
            "Dark stage, neon glows, frosted-glass card — modern tech vibe.",
            _glass,
        ),
        Template(
            "promo",
            "Promo Ticket",
            "Coupon ticket with giant offer value — built for sales & launches.",
            _promo,
        ),
        Template(
            "photo",
            "Photo Overlay",
            "Full-bleed photo (or art) with cinematic scrim — lifestyle posts.",
            _photo,
        ),
    ]
}

TEMPLATE_ORDER: List[str] = list(TEMPLATES)


def get_template(key: str) -> Template:
    k = str(key).strip().lower()
    if k not in TEMPLATES:
        raise KeyError(f"Unknown template {key!r}. Available: {', '.join(TEMPLATES)}")
    return TEMPLATES[k]


def parse_templates(value) -> List[str]:
    """Accept ``"bold,glass"``, a list, ``"all"`` or empty (→ ``[]`` = rotate)."""
    if value is None or value == "":
        return []
    items = value.split(",") if isinstance(value, str) else list(value)
    keys = [str(i).strip().lower() for i in items if str(i).strip()]
    if keys == ["all"]:
        return list(TEMPLATE_ORDER)
    for k in keys:
        get_template(k)
    return keys
