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
_NOISE = re.compile(r"(?i)\b(synth|synthetic|test|sample|group|campaign)\w*\b")

# ─────────────────────────────────────────────────────────────────────────────
# Template banks  ({p} = product, {P} = Product capitalised)
# ─────────────────────────────────────────────────────────────────────────────

HEADLINES: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "benefit": [
            "Save more on {p}",
            "{P}, made easy",
            "Better {p} for less",
            "Easy {p}, real value",
            "Save time with {p}",
        ],
        "urgency": [
            "{P}: ends today",
            "Last call: {p} now",
            "Limited {p} drop",
            "Hurry, {p} ends soon",
            "Get {p} today",
        ],
        "social_proof": [
            "10k+ customers love {p}",
            "Trusted {p}, 5k+ reviews",
            "Why 2k+ users pick {p}",
            "{P}, rated by 8k+ users",
        ],
        "problem_solution": [
            "Fix your {p} problem",
            "{P} issues? Solved.",
            "The simple {p} solution",
            "Solve {p} in minutes",
        ],
        "curiosity": [
            "Discover new {p}",
            "The secret of great {p}",
            "What if {p} felt lighter?",
            "Discover what {p} can do",
        ],
    },
    "vi": {
        "benefit": [
            "Tiết kiệm hơn với {p}",
            "{P} dễ dàng hơn",
            "{P} hiệu quả, giá tốt",
            "Tiết kiệm khi mua {p}",
        ],
        "urgency": [
            "{P}: chỉ hôm nay",
            "Ưu đãi {p} có hạn",
            "Mua {p} ngay hôm nay",
            "{P} giảm giá hôm nay",
        ],
        "social_proof": [
            "10K+ khách hàng chọn {p}",
            "{P}: 5K+ đánh giá tốt",
            "Khách hàng yêu {p}",
        ],
        "problem_solution": [
            "Giải pháp {p} gọn nhẹ",
            "Khắc phục lo lắng về {p}",
            "{P}: giải pháp cho bạn",
        ],
        "curiosity": [
            "Khám phá {p} mới",
            "Bí mật của {p}",
            "Vì sao ai cũng mê {p}?",
            "Khám phá {p} ngay",
        ],
    },
}

GENERIC_HEADLINES: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "benefit": ["Save more, stress less", "Easy value, every day"],
        "urgency": ["Ends today — act now", "Limited drop, today"],
        "social_proof": ["Loved by 10k+ customers", "5k+ trusted reviews"],
        "problem_solution": ["The simple solution", "Problem? Solved."],
        "curiosity": ["Discover something new", "The secret is out"],
    },
    "vi": {
        "benefit": ["Tiết kiệm hơn mỗi ngày", "Dễ dàng và hiệu quả"],
        "urgency": ["Chỉ hôm nay thôi", "Ưu đãi có hạn"],
        "social_proof": ["10K+ khách hàng tin chọn", "5K+ đánh giá tốt"],
        "problem_solution": ["Giải pháp gọn nhẹ", "Khắc phục thật dễ"],
        "curiosity": ["Khám phá điều mới", "Bí mật đã lộ diện"],
    },
}

DESCRIPTIONS: Dict[str, Dict[str, List[str]]] = {
    "en": {
        "benefit": [
            "Save time and money with {p}. Free returns within 30 days. Shop now!",
            "Get more value from {p} with fast, free delivery. Order today!",
        ],
        "urgency": [
            "{P} deals end tonight. Stock is limited — grab yours now!",
            "Limited-time pricing on {p}. Don't wait — shop today!",
        ],
        "social_proof": [
            "Join 10k+ happy customers who switched to {p}. Try it today!",
            "Rated 4.9/5 by thousands of shoppers. See why — shop {p} now!",
        ],
        "problem_solution": [
            "Tired of the usual hassle? Meet {p} — sorted in minutes. Learn more!",
            "The easy solution for everyday {p} problems. Get started today!",
        ],
        "curiosity": [
            "Discover what makes our {p} different. Take a look inside!",
            "The secret behind comfy, lasting {p}? Find out now!",
        ],
    },
    "vi": {
        "benefit": [
            "{P} giúp bạn tiết kiệm thời gian và chi phí. Đổi trả 30 ngày. Mua ngay!",
            "Giao nhanh miễn phí, giá tốt mỗi ngày cho {p}. Đặt hàng ngay!",
        ],
        "urgency": [
            "Ưu đãi {p} chỉ trong hôm nay. Số lượng có hạn — mua ngay!",
            "Giá tốt cho {p} sắp kết thúc. Đừng bỏ lỡ, đặt ngay hôm nay!",
        ],
        "social_proof": [
            "Hơn 10K khách hàng đã chọn {p}. Trải nghiệm ngay hôm nay!",
            "Đánh giá 4.9/5 từ hàng nghìn người dùng. Xem ngay {p}!",
        ],
        "problem_solution": [
            "Hết lo phiền phức với {p} — giải pháp gọn nhẹ. Tìm hiểu ngay!",
            "Giải pháp dễ dàng cho mọi vấn đề về {p}. Bắt đầu ngay hôm nay!",
        ],
        "curiosity": [
            "Khám phá điều khiến {p} khác biệt. Xem ngay!",
            "Bí mật đằng sau {p} được yêu thích? Khám phá ngay!",
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
        if len(s) >= 3:
            return s
    return ""


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _lower_first(s: str) -> str:
    """Lower-case a Title-Cased phrase for mid-sentence use (acronyms kept)."""
    return " ".join(w if (w.isupper() and len(w) > 1) else w.lower() for w in s.split())


def _fill(tpl: str, product: str, keep_case: bool = False) -> str:
    p = product if keep_case else _lower_first(product)
    out = tpl.replace("{P}", _cap(p)).replace("{p}", p)
    out = re.sub(r"\s+", " ", out).strip()
    return _cap(out)


def _shorten(product: str, language: str = "en") -> List[str]:
    """Progressively shorter variants of the product phrase.

    English noun phrases keep their head noun at the end ("Spring *Shoes*"),
    Vietnamese at the start ("*Giày* chạy bộ"), so we trim accordingly.
    """
    words = product.split()
    if language == "vi":
        variants = [" ".join(words[: len(words) - i]) for i in range(len(words))]
    else:
        variants = [" ".join(words[i:]) for i in range(len(words))]
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
        "urgency": ["{O} — don't miss it", "Last call for {p}", "{P} drop ends soon"],
        "social_proof": [
            "Why 10k+ people love {p}",
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
            "{P}: ưu đãi sắp kết thúc",
        ],
        "social_proof": ["Vì sao 10K+ người chọn {p}?", "{P} ai cũng đang nhắc đến"],
        "problem_solution": ["Tạm biệt {pain}", "Giải pháp dễ dàng cho {pain}"],
        "curiosity": ["Gặp gỡ {p} phiên bản mới", "Điều gì khiến {p} khác biệt?"],
    },
}

_POST_BODY = {
    "en": {
        "benefit": "{B1}. {B2}. Made for {A}.",
        "urgency": "{O} on {p} — while stock lasts. {B1}.",
        "social_proof": "Thousands of {A} already switched. {B1}, and {b2}.",
        "problem_solution": "{B1}. {B2}. No more compromises.",
        "curiosity": "{B1}. {B2}. Swipe to see it in action.",
    },
    "vi": {
        "benefit": "{B1}. {B2}. Dành riêng cho {A}.",
        "urgency": "{O} cho {p} — số lượng có hạn. {B1}.",
        "social_proof": "Hàng nghìn {A} đã tin chọn. {B1}, {b2}.",
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
