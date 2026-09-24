"""The :class:`Creative` data model and copy-derived helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from gcf.creative.text import clean_text

_VI_CHARS = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")

_PERCENT = re.compile(r"(?<![\d.,])(\d{1,2})\s?%")
_BOGO = re.compile(
    r"(?i)\b(mua\s*1\s*tặng\s*1|buy\s*one\s*get\s*one|buy\s*1\s*get\s*1|bogo)\b"
)
_FREE_SHIP = re.compile(
    r"(?i)(free\s*ship(ping)?|miễn\s*phí\s*(vận\s*chuyển|giao\s*hàng|ship))"
)

DEFAULT_CTA = {"en": "Shop now", "vi": "Mua ngay"}


def detect_language(text: str) -> str:
    """Very small heuristic: ``vi`` if Vietnamese diacritics are present."""
    lowered = clean_text(text).lower()
    return "vi" if any(c in _VI_CHARS for c in lowered) else "en"


def extract_badge(*texts: str) -> str:
    """Pull a punchy badge (e.g. ``-30%``, ``1+1``, ``FREE SHIP``) from copy."""
    joined = " ".join(clean_text(t) for t in texts if t)
    m = _PERCENT.search(joined)
    if m and 5 <= int(m.group(1)) <= 90:
        return f"-{int(m.group(1))}%"
    if _BOGO.search(joined):
        return "1+1"
    m = _FREE_SHIP.search(joined)
    if m:
        return "FREESHIP" if detect_language(joined) == "vi" else "FREE SHIP"
    return ""


@dataclass
class Creative:
    """One piece of social/ad creative copy to be rendered."""

    headline: str
    description: str = ""
    cta: str = ""
    eyebrow: str = ""
    badge: str = ""
    tag: str = ""
    image: Optional[str] = None
    template: Optional[str] = None
    language: Optional[str] = None

    def __post_init__(self) -> None:
        self.headline = clean_text(self.headline)
        self.description = clean_text(self.description)
        self.cta = clean_text(self.cta)
        self.eyebrow = clean_text(self.eyebrow)
        self.badge = clean_text(self.badge)
        self.tag = clean_text(self.tag)
        self.image = clean_text(self.image) or None
        self.template = clean_text(self.template).lower() or None
        if not self.language:
            self.language = detect_language(f"{self.headline} {self.description}")

    @property
    def seed(self) -> int:
        """Stable per-creative seed so decorations are reproducible."""
        key = f"{self.tag}|{self.headline}|{self.description}"
        return int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:8], 16)

    def resolved_cta(self, brand_cta: str = "") -> str:
        return (
            self.cta or brand_cta or DEFAULT_CTA.get(self.language or "en", "Shop now")
        )

    def resolved_badge(self, auto: bool = True) -> str:
        if self.badge:
            return self.badge
        return extract_badge(self.headline, self.description) if auto else ""

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Creative":
        """Build from a CSV/TSV row. Accepts Figma-style (H1/DESC/TAG) or
        friendly column names (headline/description/body/primary_text…)."""
        low = {str(k).strip().lower(): v for k, v in row.items()}

        def pick(*names: str) -> str:
            for n in names:
                v = low.get(n)
                if v is not None and clean_text(v):
                    return clean_text(v)
            return ""

        return cls(
            headline=pick("headline", "h1", "variant_headline", "title"),
            description=pick(
                "description",
                "desc",
                "variant_description",
                "body",
                "primary_text",
                "text",
            ),
            cta=pick("cta", "call_to_action", "button"),
            eyebrow=pick("eyebrow", "kicker", "label", "h2"),
            badge=pick("badge", "offer_badge", "discount"),
            tag=pick("tag", "id", "name"),
            image=pick("image", "image_path", "photo", "product_image") or None,
            template=pick("template") or None,
        )
