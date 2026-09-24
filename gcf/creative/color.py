"""Colour helpers: parsing, mixing and WCAG contrast."""

from __future__ import annotations

from typing import Tuple

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]


def hex_to_rgb(value: str) -> RGB:
    """Parse ``#RGB`` / ``#RRGGBB`` (with or without ``#``) into an RGB tuple."""
    v = str(value).strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError(f"Invalid hex colour: {value!r}")
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"Invalid hex colour: {value!r}") from exc


def rgb_to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def with_alpha(rgb: RGB, alpha: float) -> RGBA:
    """Return an RGBA tuple with *alpha* in [0, 1]."""
    a = max(0, min(255, round(alpha * 255)))
    return rgb[0], rgb[1], rgb[2], a


def mix(a: RGB, b: RGB, t: float) -> RGB:
    """Linear interpolation between two colours (t=0 → a, t=1 → b)."""
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def lighten(c: RGB, t: float) -> RGB:
    return mix(c, (255, 255, 255), t)


def darken(c: RGB, t: float) -> RGB:
    return mix(c, (0, 0, 0), t)


def _channel(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(c: RGB) -> float:
    """WCAG relative luminance."""
    return 0.2126 * _channel(c[0]) + 0.7152 * _channel(c[1]) + 0.0722 * _channel(c[2])


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_on(bg: RGB, light: RGB = (255, 255, 255), dark: RGB = (17, 17, 17)) -> RGB:
    """Pick whichever of *light* / *dark* has the better contrast on *bg*."""
    return light if contrast_ratio(bg, light) >= contrast_ratio(bg, dark) else dark
