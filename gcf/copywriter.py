"""Offline copywriter — context-aware ad & social copy with zero API calls.

Powers dry-run mode so that a fresh clone produces *usable* creatives, not
lorem ipsum. It extracts the product from the original ad (or a brief),
detects English/Vietnamese, and fills angle-specific templates that respect
character limits and the policy blocklist.

Every template carries a keyword recognised by :mod:`gcf.dedupe`, so the
diversity engine sees genuinely different creative angles.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from gcf.creative.model import detect_language, extract_badge

ANGLES = ["benefit", "urgency", "social_proof", "problem_solution", "curiosity"]

_PROMO_WORDS = re.compile(
    r"(?i)\b(offer|offers|deal|deals|sale|sales|promo|promotion|discount|picks|"
    r"special|hot|new|now|today|ưu đãi|khuyến mãi|giảm giá|sale off)\b"
)
_VI_CONNECTORS = {"giao", "cho", "tại", "với", "dành", "từ", "của"}
_NOISE = re.compile(r"(?i)\b(synth|synthetic|test|sample|group|campaign)\w*\b")

# ─────────────────────────────────────────────────────────────────────────────
# Template banks  ({p} = product, {P} = Product capitalised)
# ─────────────────────────────────────────────────────────────────────────────

# Templates never invent facts: no review counts, ratings, prices, delivery or
# return policies. Put real claims in live mode or in your own copy sheet.
HEADLINES: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "benefit": [
            "Save time with {p}",
            "{P}, made easy",
            "Better days with {p}",
            "Easy {p}, real value",
            "{P}: the easy way",
        ],
        "urgency": [
            "Get {p} today",
            "Try {p} now",
            "Last call for {p}",
            "Hurry, see {p} now",
            "Your {p}, today",
        ],
        "social_proof": [
            "See why customers love {p}",
            "Why customers choose {p}",
            "{P}, trusted by customers",
            "Read the {p} reviews",
        ],
        "problem_solution": [
            "{P}, problem solved",
            "The simple {p} solution",
            "Solve it with {p}",
            "Fix the hassle: {p}",
        ],
        "curiosity": [
            "Discover new {p}",
            "What makes {p} different?",
            "The secret behind {p}",
            "Why {p}? Discover it",
        ],
    },
    "vi": {
        "benefit": [
            "Tiết kiệm hơn với {p}",
            "{P} dễ dàng hơn",
            "Dễ dàng hơn với {p}",
            "{P} hiệu quả mỗi ngày",
        ],
        "urgency": [
            "Đặt {p} ngay hôm nay",
            "Thử {p} ngay",
            "Đừng bỏ lỡ {p} hôm nay",
            "{P}: mua ngay hôm nay",
        ],
        "social_proof": [
            "Vì sao khách hàng chọn {p}",
            "{P} được khách hàng tin chọn",
            "Đọc đánh giá về {p}",
        ],
        "problem_solution": [
            "Giải pháp {p} gọn nhẹ",
            "{P}: giải pháp cho bạn",
            "Khắc phục phiền toái với {p}",
        ],
        "curiosity": [
            "Khám phá {p} mới",
            "Bí mật của {p}",
            "Vì sao ai cũng mê {p}?",
        ],
    },
}

GENERIC_HEADLINES: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "benefit": ["Save time, stress less", "Easy value, every day"],
        "urgency": ["Start today", "Don't wait, try it now"],
        "social_proof": ["See why customers switch", "Read what customers say"],
        "problem_solution": ["The simple solution", "Problem? Solved."],
        "curiosity": ["Discover something new", "The secret is out"],
    },
    "vi": {
        "benefit": ["Tiết kiệm hơn mỗi ngày", "Dễ dàng và hiệu quả"],
        "urgency": ["Bắt đầu ngay hôm nay", "Đừng chờ, thử ngay"],
        "social_proof": ["Vì sao khách hàng tin chọn", "Xem khách hàng đánh giá"],
        "problem_solution": ["Giải pháp gọn nhẹ", "Khắc phục thật dễ"],
        "curiosity": ["Khám phá điều mới", "Bí mật đã lộ diện"],
    },
}

DESCRIPTIONS: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "benefit": [
            "Make every day easier with {p}. Simple to start, easy to love. Learn more!",
            "Get more value from {p}, without the hassle. Take a look today!",
        ],
        "urgency": [
            "Don't wait: discover {p} today and see the difference. Shop now!",
            "Now is the time to try {p}. Take the first step today!",
        ],
        "social_proof": [
            "See why customers choose {p}. Read the reviews and decide for yourself!",
            "Trusted by customers who wanted better. Try {p} today!",
        ],
        "problem_solution": [
            "Tired of the usual hassle? Try {p} and keep it simple. Learn more!",
            "The easy fix you have been looking for: {p}. Get started today!",
        ],
        "curiosity": [
            "Discover what makes {p} different. Take a look inside!",
            "Curious about {p}? Find out why people are talking. See more!",
        ],
    },
    "vi": {
        "benefit": [
            "Tiết kiệm thời gian mỗi ngày cùng {p}. Dễ bắt đầu, dễ yêu thích. Xem ngay!",
            "{P} giúp mọi việc nhẹ nhàng hơn. Tìm hiểu ngay hôm nay!",
        ],
        "urgency": [
            "Đừng chờ nữa, trải nghiệm {p} ngay hôm nay. Mua ngay!",
            "Bắt đầu với {p} ngay hôm nay. Đặt hàng ngay!",
        ],
        "social_proof": [
            "Xem vì sao khách hàng chọn {p}. Đọc đánh giá và tự trải nghiệm!",
            "Được khách hàng tin chọn mỗi ngày. Thử {p} ngay!",
        ],
        "problem_solution": [
            "Hết lo phiền phức với {p}: gọn nhẹ, dễ dùng. Tìm hiểu ngay!",
            "Giải pháp dễ dàng cho mỗi ngày: {p}. Bắt đầu ngay hôm nay!",
        ],
        "curiosity": [
            "Khám phá điều khiến {p} khác biệt. Xem ngay!",
            "Tò mò về {p}? Khám phá ngay hôm nay!",
        ],
    },
}

EYEBROWS: Dict[str, Dict[str, str]] = {
    "en": {
        "benefit": "Everyday value",
        "urgency": "Limited time",
        "social_proof": "Customer favourite",
        "problem_solution": "The easy fix",
        "curiosity": "Just dropped",
    },
    "vi": {
        "benefit": "Giá tốt mỗi ngày",
        "urgency": "Ưu đãi có hạn",
        "social_proof": "Khách hàng yêu thích",
        "problem_solution": "Giải pháp dễ dàng",
        "curiosity": "Mới ra mắt",
    },
}

CTAS: Dict[str, Dict[str, str]] = {
    "en": {
        "benefit": "Shop now",
        "urgency": "Get the deal",
        "social_proof": "See why",
        "problem_solution": "Learn more",
        "curiosity": "Discover",
    },
    "vi": {
        "benefit": "Mua ngay",
        "urgency": "Nhận ưu đãi",
        "social_proof": "Xem ngay",
        "problem_solution": "Tìm hiểu",
        "curiosity": "Khám phá",
    },
}

_BLOCKED = re.compile(
    r"(?i)(\bbest\b|\bguarantee[d]?\b|(?<!\w)#1\b|\bno\.?\s*1\b|100%|"
    r"cam\s*k[eế]t|tuy[eệ]t\s*[dđ][oố]i)"
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def extract_product(*sources: str) -> str:
    """Best-effort product/subject phrase from an ad headline or campaign name."""
    for src in sources:
        if not src:
            continue
        s = re.sub(r"[_|/]+", " ", str(src))
        s = _NOISE.sub(" ", s)
        s = _PROMO_WORDS.sub(" ", s)
        s = re.sub(r"[^\w\s&'’-]", " ", s)
        s = re.sub(r"\s+", " ", s).strip(" -")
        # "Rau hữu cơ giao tận nhà" → "Rau hữu cơ": drop the service clause
        words = s.split()
        for i, w in enumerate(words):
            if i >= 2 and w.lower() in _VI_CONNECTORS:
                s = " ".join(words[:i])
                break
        if len(s) >= 3:
            return s
    return ""


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _lower_first(s: str) -> str:
    """Lower-case a Title-Cased phrase for mid-sentence use (acronyms kept)."""
    return " ".join(w if w.isupper() else w.lower() for w in s.split())


def _fill(tpl: str, product: str, keep_case: bool = False) -> str:
    p = product if keep_case else _lower_first(product)
    out = tpl.replace("{P}", _cap(p)).replace("{p}", p)
    out = re.sub(r"\s+", " ", out).strip()
    return _cap(out)


def _shorten(product: str, language: str = "en") -> List[str]:
    """Progressively shorter variants of the product phrase (min. 2 words).

    English noun phrases keep their head noun at the end ("Spring *Shoes*"),
    Vietnamese at the start ("*Giày* chạy bộ"), so we trim accordingly. We
    stop at two words: a lone "app" or "getaway" reads worse than a generic
    headline, which is used instead.
    """
    words = product.split()
    if len(words) <= 2 or language == "vi":
        # Vietnamese modifiers carry meaning ("serum vitamin C"); cutting them
        # produces fragments, so VI uses the full phrase or a generic line.
        return [product] if product else []
    else:
        variants = [" ".join(words[-n:]) for n in range(len(words), 1, -1)]
    return [v for v in variants if v]


def _ok(text: str, max_chars: Optional[int]) -> bool:
    if max_chars and len(text) > max_chars:
        return False
    return not _BLOCKED.search(text)


# ─────────────────────────────────────────────────────────────────────────────
# Public API — ad copy
# ─────────────────────────────────────────────────────────────────────────────


def write_headlines(
    product: str,
    n: int = 10,
    max_chars: Optional[int] = 30,
    language: Optional[str] = None,
    seed: int = 0,
    angles: Sequence[str] = ANGLES,
) -> List[str]:
    """Return up to *n* distinct headlines, round-robin across *angles*."""
    lang = language or detect_language(product)
    lang = lang if lang in HEADLINES else "en"
    rng = random.Random(seed)
    candidates = _shorten(product, lang) if product else []
    per_angle: Dict[str, List[str]] = {}
    for angle in angles:
        pool: List[str] = []
        templates = list(HEADLINES[lang].get(angle, []))
        rng.shuffle(templates)
        for tpl in templates:
            for prod in candidates:
                text = _fill(tpl, prod)
                if _ok(text, max_chars):
                    pool.append(text)
                    break
        generic = list(GENERIC_HEADLINES[lang].get(angle, []))
        rng.shuffle(generic)
        pool += [g for g in generic if _ok(g, max_chars)]
        per_angle[angle] = pool
    return _round_robin(per_angle, angles, n)


def write_descriptions(
    product: str,
    n: int = 6,
    max_chars: Optional[int] = 90,
    language: Optional[str] = None,
    seed: int = 0,
    angles: Sequence[str] = ANGLES,
) -> List[str]:
    lang = language or detect_language(product)
    lang = lang if lang in DESCRIPTIONS else "en"
    rng = random.Random(seed + 1)
    candidates = (_shorten(product, lang) if product else []) + [
        "sản phẩm" if lang == "vi" else "our range"
    ]
    per_angle: Dict[str, List[str]] = {}
    for angle in angles:
        templates = list(DESCRIPTIONS[lang].get(angle, []))
        rng.shuffle(templates)
        pool = []
        for tpl in templates:
            for prod in candidates:
                text = _fill(tpl, prod)
                if _ok(text, max_chars):
                    pool.append(text)
                    break
        per_angle[angle] = pool
    return _round_robin(per_angle, angles, n)


def _round_robin(
    per_angle: Dict[str, List[str]], angles: Sequence[str], n: int
) -> List[str]:
    out: List[str] = []
    seen = set()
    depth = 0
    while len(out) < n and any(len(per_angle.get(a, [])) > depth for a in angles):
        for a in angles:
            pool = per_angle.get(a, [])
            if depth < len(pool) and pool[depth].lower() not in seen:
                out.append(pool[depth])
                seen.add(pool[depth].lower())
                if len(out) >= n:
                    break
        depth += 1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Public API — social posts from a brief
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Brief:
    """A product brief for generating a batch of social posts."""

    product: str
    audience: str = ""
    offer: str = ""
    benefits: List[str] = field(default_factory=list)
    tone: str = ""
    language: Optional[str] = None  # "en" | "vi" | None → auto
    pain: str = ""  # the problem the product solves, e.g. "sore feet"
    extra: str = ""

    def lang(self) -> str:
        if self.language in ("en", "vi"):
            return self.language  # type: ignore[return-value]
        return detect_language(" ".join([self.product, self.offer, *self.benefits]))


@dataclass
class Post:
    headline: str
    description: str
    cta: str = ""
    eyebrow: str = ""
    badge: str = ""
    angle: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "eyebrow": self.eyebrow,
            "headline": self.headline,
            "description": self.description,
            "cta": self.cta,
            "badge": self.badge,
            "angle": self.angle,
        }


_POST_HEAD = {
    "en": {
        "benefit": [
            "{P}, made effortless",
            "More joy, less effort: {p}",
            "Everyday {p}, upgraded",
        ],
        "urgency": ["{O} — don't miss it", "Last call for {p}", "It's time to try {p}"],
        "social_proof": [
            "Why people love {p}",
            "The {p} everyone is talking about",
        ],
        "problem_solution": ["Say goodbye to {pain}", "The easy fix for {pain}"],
        "curiosity": ["Meet the new {p}", "What makes {p} different?"],
    },
    "vi": {
        "benefit": [
            "{P} — nhẹ nhàng mỗi ngày",
            "Nâng cấp {p} của bạn",
            "{P} cho mọi khoảnh khắc",
        ],
        "urgency": [
            "{O} — đừng bỏ lỡ",
            "Cơ hội cuối cho {p}",
            "Đến lúc thử {p} rồi",
        ],
        "social_proof": ["Vì sao mọi người chọn {p}?", "{P} ai cũng đang nhắc đến"],
        "problem_solution": ["Tạm biệt {pain}", "Giải pháp dễ dàng cho {pain}"],
        "curiosity": ["Gặp gỡ {p} phiên bản mới", "Điều gì khiến {p} khác biệt?"],
    },
}

_POST_BODY = {
    "en": {
        "benefit": "{B1}. {B2}. Made for {A}.",
        "urgency": "{O} on {p}. {B1}. {B2}.",
        "social_proof": "Made for {A} who want more. {B1}, and {b2}.",
        "problem_solution": "{B1}. {B2}. No more compromises.",
        "curiosity": "{B1}. {B2}. Swipe to see it in action.",
    },
    "vi": {
        "benefit": "{B1}. {B2}. Dành riêng cho {A}.",
        "urgency": "{O} cho {p}. {B1}. {B2}.",
        "social_proof": "Dành cho {A} muốn nhiều hơn. {B1}, {b2}.",
        "problem_solution": "{B1}. {B2}. Không còn phải đánh đổi.",
        "curiosity": "{B1}. {B2}. Lướt để khám phá ngay.",
    },
}

_DEFAULTS = {
    "en": {
        "A": "people like you",
        "B": ["Thoughtfully designed", "Built to last"],
        "pain": "everyday hassle",
    },
    "vi": {
        "A": "khách hàng như bạn",
        "B": ["Thiết kế tinh tế", "Bền bỉ theo thời gian"],
        "pain": "những phiền toái",
    },
}


def write_posts(
    brief: Brief, n: int = 6, seed: int = 0, angles: Sequence[str] = ANGLES
) -> List[Post]:
    """Generate *n* social posts (headline/body/eyebrow/CTA/badge) offline."""
    lang = brief.lang()
    rng = random.Random(seed)
    d = _DEFAULTS[lang]
    angles = [a for a in (angles or ANGLES) if a in _POST_HEAD[lang]] or list(ANGLES)
    product = brief.product.strip() or ("sản phẩm" if lang == "vi" else "our product")
    benefits = [b.strip().rstrip(".") for b in brief.benefits if b.strip()] or list(
        d["B"]
    )
    while len(benefits) < 2:
        benefits.append(d["B"][len(benefits) % 2])
    audience = brief.audience.strip() or d["A"]
    offer = brief.offer.strip()
    badge = extract_badge(offer) if offer else ""
    pain = brief.pain.strip() or d["pain"]

    posts: List[Post] = []
    order = list(angles)
    if not offer and "urgency" in order:
        order.remove("urgency")
        order.append("urgency")  # urgency without an offer is weaker; do it last
    i = 0
    while len(posts) < n:
        angle = order[i % len(order)]
        variant = i // len(order)
        heads = _POST_HEAD[lang][angle]
        head_tpl = heads[(variant + rng.randrange(len(heads))) % len(heads)]
        if "{O}" in head_tpl and not offer:
            head_tpl = heads[-1] if heads[-1] != head_tpl else heads[0]
        b1, b2 = (
            benefits[variant % len(benefits)],
            benefits[(variant + 1) % len(benefits)],
        )
        p = product  # user-typed brief: keep their casing (brand names!)
        subs = {
            "{P}": _cap(p),
            "{p}": p,
            "{O}": offer,
            "{A}": audience,
            "{B1}": _cap(b1),
            "{B2}": _cap(b2),
            "{b2}": _lower_first(b2),
            "{pain}": pain,
        }
        head = head_tpl
        body = _POST_BODY[lang][angle]
        if "{O}" in body and not offer:
            body = _POST_BODY[lang]["benefit"]
        for k, v in subs.items():
            head = head.replace(k, v)
            body = body.replace(k, v)
        head, body = _cap(re.sub(r"\s+", " ", head).strip()), _cap(
            re.sub(r"\s+", " ", body).strip()
        )
        if _BLOCKED.search(head) or _BLOCKED.search(body):
            i += 1
            if i > n * 10:
                break
            continue
        posts.append(
            Post(
                headline=head,
                description=body,
                cta=CTAS[lang][angle],
                eyebrow=EYEBROWS[lang][angle],
                badge=badge if angle in ("urgency", "benefit") else "",
                angle=angle,
            )
        )
        i += 1
    return posts
