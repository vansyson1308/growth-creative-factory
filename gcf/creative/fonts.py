"""Bundled font resolution.

The package ships a small set of SIL-OFL fonts with full Vietnamese and
Latin coverage so renders look identical on every machine:

* ``display`` — Be Vietnam Pro ExtraBold (headlines)
* ``heading`` — Be Vietnam Pro SemiBold (eyebrows, buttons)
* ``body``    — Be Vietnam Pro Regular (body copy)
* ``serif``   — Playfair Display Bold (editorial headlines)

A brand kit can override any role with a path to its own ``.ttf``/``.otf``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

from PIL import ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

BUNDLED_FONTS: Dict[str, str] = {
    "display": "BeVietnamPro-ExtraBold.ttf",
    "heading": "BeVietnamPro-SemiBold.ttf",
    "body": "BeVietnamPro-Regular.ttf",
    "serif": "PlayfairDisplay-Bold.ttf",
}


def font_path(role: str, overrides: Optional[Dict[str, str]] = None) -> str:
    """Return the font file for *role*, honouring brand-kit overrides."""
    if overrides and overrides.get(role):
        p = Path(overrides[role]).expanduser()
        if p.is_file():
            return str(p)
    name = BUNDLED_FONTS.get(role, BUNDLED_FONTS["body"])
    return str(FONT_DIR / name)


@lru_cache(maxsize=512)
def load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load (and cache) a font at an integer pixel size.

    Basic layout is used on purpose: it needs no libraqm, renders precomposed
    Vietnamese glyphs correctly, and keeps output identical across platforms.
    """
    return ImageFont.truetype(
        path, max(1, int(size)), layout_engine=ImageFont.Layout.BASIC
    )
