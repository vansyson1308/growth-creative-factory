"""Mock provider for dry-run mode — no API calls, strict JSON responses.

Copy is produced by :mod:`gcf.copywriter`, an offline template engine that
reads the product and language from the prompt, so dry runs yield realistic,
on-topic, policy-safe copy instead of placeholder text.
"""

from __future__ import annotations

import json
import random
import re
import zlib
from typing import List, Optional

from gcf import copywriter
from gcf.providers.base import BaseProvider

# Pools of realistic mock outputs
_HEADLINE_POOL = [
    "Tiết kiệm ngay hôm nay",
    "Ưu đãi có hạn",
    "Mua 1 tặng 1 hot deal",
    "Dùng thử miễn phí 7 ngày",
    "Giảm 30% toàn bộ",
    "Đăng ký nhận quà ngay",
    "Nâng cấp cuộc sống dễ",
    "Trải nghiệm khác biệt",
    "Giải pháp tối ưu chi phí",
    "Xu hướng mới 2026",
    "Ship nhanh trong 24h",
    "Chất lượng vượt mong đợi",
    "Dành riêng cho bạn",
    "Khám phá ngay bây giờ",
    "Sản phẩm hot nhất tuần",
]

_DESC_POOL = [
    "Đăng ký ngay để nhận ưu đãi độc quyền chỉ hôm nay. Số lượng có hạn!",
    "Trải nghiệm dịch vụ chuyên nghiệp với đội ngũ tận tâm. Liên hệ ngay!",
    "Sản phẩm chất lượng cao, giá hợp lý. Mua ngay kẻo lỡ deal hot!",
    "Giải pháp toàn diện cho doanh nghiệp vừa và nhỏ. Tư vấn miễn phí!",
    "Giao hàng miễn phí toàn quốc. Đổi trả dễ dàng trong 30 ngày.",
    "Công nghệ tiên tiến, thiết kế hiện đại. Nâng tầm phong cách. Mua ngay!",
    "Ưu đãi đặc biệt cuối tuần — giảm thêm 15%. Đặt hàng ngay hôm nay!",
    "Tham gia cộng đồng hơn 50K thành viên. Đăng ký nhận tin ưu đãi!",
    "Chất lượng hàng đầu, giá phải chăng. Xem ngay và mua hôm nay!",
]


def _detect_prompt_type(prompt: str) -> str:
    """Detect which agent type this prompt is intended for.

    Returns one of: 'posts', 'selector', 'brand_voice', 'headline', 'description',
    'checker', 'unknown'.
    Uses the first 5 lines (TASK / role declaration) to avoid false positives
    from context fields like 'original_headline' or 'current description'.
    """
    first_lines = "\n".join(prompt.splitlines()[:5]).lower()
    full_lower = prompt.lower()

    # Social post writer (brief → posts)
    if "social post writer" in first_lines:
        return "posts"

    # Checker: reviews existing copy for violations
    if "compliance reviewer" in full_lower or "violations" in first_lines:
        return "checker"

    # Selector: analyses underperforming ads
    if (
        "performance marketing analyst" in full_lower
        or "root-cause" in full_lower
        or ("analyse" in first_lines and "underperforming" in first_lines)
    ):
        return "selector"

    # Brand-voice guidance prompt
    if (
        "brand voice strategist" in full_lower
        or "create a concise brand voice guideline" in full_lower
    ):
        return "brand_voice"

    # Description vs. headline — check TASK line first
    if "generate" in first_lines and "description" in first_lines:
        return "description"
    if "generate" in first_lines and "headline" in first_lines:
        return "headline"

    # Targeted retry prompts (no TASK line)
    if "replacement description" in full_lower or (
        "failed validation" in full_lower and "description" in full_lower
    ):
        return "description"
    if "replacement headline" in full_lower or (
        "failed validation" in full_lower and "headline" in full_lower
    ):
        return "headline"

    return "unknown"


def _field(prompt: str, label: str) -> str:
    m = re.search(rf"(?im)^\s*-?\s*{label}\s*:\s*(.+)$", prompt)
    return m.group(1).strip() if m else ""


def _int(prompt: str, pattern: str, default: int) -> int:
    m = re.search(pattern, prompt, flags=re.IGNORECASE)
    try:
        return int(m.group(1)) if m else default
    except (TypeError, ValueError):
        return default


def _product_from_prompt(prompt: str) -> str:
    campaign = _field(prompt, "Campaign")
    return copywriter.extract_product(
        _field(prompt, "Current headline"),
        campaign.split("/")[0] if campaign else "",
        campaign,
    )


def _language_from_prompt(prompt: str) -> Optional[str]:
    sample = " ".join(
        [
            _field(prompt, "Current headline"),
            _field(prompt, "Current description"),
            _field(prompt, "Campaign"),
        ]
    )
    if not sample.strip():
        # Retry prompts quote the failed copy — use that as the language hint
        sample = " ".join(re.findall(r"^- '(.+?)':", prompt, flags=re.MULTILINE))
    return copywriter.detect_language(sample) if sample.strip() else None


class MockProvider(BaseProvider):
    """Deterministic offline provider that returns strict JSON responses.

    All agent types (selector, brand voice, headline, description, checker,
    posts) return valid JSON so that the real parsers are exercised in dry-run
    mode.
    """

    def __init__(self, seed: int = 42, **kwargs):
        """Initialise with an optional RNG seed.

        Extra keyword arguments (e.g. a ``ProviderConfig``) are silently
        ignored so that callers can pass the same kwargs used for the real
        provider without crashing.
        """
        if not isinstance(seed, int):
            seed = 42
        self._seed = seed
        self._rng = random.Random(seed)
        # Track the call sequence for test assertions
        self._call_log: List[str] = []

    def _seed_for(self, prompt: str) -> int:
        return (
            self._seed * 1_000_003 + zlib.crc32(prompt.encode("utf-8"))
        ) & 0x7FFFFFFF

    def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        """Detect prompt type and return valid JSON mock response."""
        ptype = _detect_prompt_type(prompt)
        self._call_log.append(ptype)

        if ptype == "posts":
            return self._mock_posts(prompt)
        if ptype == "selector":
            return self._mock_strategy(prompt)
        elif ptype == "brand_voice":
            return self._mock_brand_voice()
        elif ptype == "headline":
            return self._mock_headlines(prompt=prompt)
        elif ptype == "description":
            return self._mock_descriptions(prompt=prompt)
        elif ptype == "checker":
            return self._mock_checker()
        else:
            # Generic fallback — return headlines JSON so pipeline doesn't break
            return self._mock_headlines(prompt=prompt)

    # ── Mock response builders ────────────────────────────────────────────────

    def _mock_strategy(self, prompt: str = "") -> str:
        """Return a selector-style strategy JSON grounded in the ad's metrics."""
        ad_id = _field(prompt, "AD ID") or "mock_ad"
        issues = _field(prompt, "Issues detected").lower()
        product = (
            copywriter.extract_product(_field(prompt, "Current headline"))
            or "the offer"
        )
        if "ctr" in issues:
            analysis = (
                f"Low CTR suggests the headline for {product} blends in with "
                "competitors and gives no concrete reason to click."
            )
            strategy = "Lead with a concrete benefit plus a time-bound hook"
        elif "roas" in issues:
            analysis = (
                f"Clicks are not converting into revenue — the copy for {product} "
                "attracts browsers rather than buyers."
            )
            strategy = "Qualify intent with social proof and a clear value anchor"
        elif "cpa" in issues:
            analysis = f"Acquisition cost is high; the {product} message lacks urgency."
            strategy = "Add urgency and a problem-solution framing to lift conversion"
        else:
            analysis = f"Engagement on {product} is flat versus account benchmarks."
            strategy = "Test curiosity and social-proof angles against the control"
        return json.dumps({"ad_id": ad_id, "analysis": analysis, "strategy": strategy})

    def _mock_brand_voice(self) -> str:
        return json.dumps(
            {
                "guideline": "Use a clear, helpful, action-focused tone for value-aware buyers.",
                "examples": [
                    "Save time with practical features. Try it today.",
                    "Straightforward value for busy teams. Get started now.",
                ],
            }
        )

    def _mock_headlines(self, n: int = 10, prompt: str = "") -> str:
        """Return a headlines JSON array written by the offline copywriter."""
        n = _int(prompt, r"exactly\s+(\d+)\s+headline", 0) or _int(
            prompt, r"provide\s+(\d+)\s+replacement", n
        )
        max_chars = _int(prompt, r"<=\s*(\d+)\s*char", 30)
        product = _product_from_prompt(prompt)
        lines = copywriter.write_headlines(
            product,
            n=n,
            max_chars=max_chars,
            language=_language_from_prompt(prompt),
            seed=self._seed_for(prompt),
        )
        if not lines:
            pool = list(_HEADLINE_POOL)
            lines = self._rng.sample(pool, min(n, len(pool)))
        return json.dumps({"headlines": lines}, ensure_ascii=False)

    def _mock_descriptions(self, n: int = 6, prompt: str = "") -> str:
        """Return a descriptions JSON array written by the offline copywriter."""
        n = _int(prompt, r"exactly\s+(\d+)\s+description", 0) or _int(
            prompt, r"provide\s+(\d+)\s+replacement", n
        )
        max_chars = _int(prompt, r"<=\s*(\d+)\s*char", 90)
        product = _product_from_prompt(prompt)
        lines = copywriter.write_descriptions(
            product,
            n=n,
            max_chars=max_chars,
            language=_language_from_prompt(prompt),
            seed=self._seed_for(prompt),
        )
        if not lines:
            pool = list(_DESC_POOL)
            lines = self._rng.sample(pool, min(n, len(pool)))
        return json.dumps({"descriptions": lines}, ensure_ascii=False)

    def _mock_posts(self, prompt: str) -> str:
        m = re.search(r"(?m)^BRIEF_JSON:\s*(\{.*\})\s*$", prompt)
        data = {}
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                data = {}
        n = int(data.pop("n", 0) or _int(prompt, r"exactly\s+(\d+)\s+post", 6))
        allowed = set(copywriter.Brief.__dataclass_fields__)
        brief = copywriter.Brief(
            **{k: v for k, v in data.items() if k in allowed and v not in (None, "")}
            or {"product": ""}
        )
        posts = copywriter.write_posts(brief, n=n, seed=self._seed_for(prompt))
        return json.dumps({"posts": [p.to_dict() for p in posts]}, ensure_ascii=False)

    def _mock_checker(self) -> str:
        """Return an empty violations list — offline copy is policy-safe."""
        return json.dumps({"violations": []})

    # ── Stats helper (mirrors AnthropicProvider interface) ────────────────────

    def stats(self) -> dict:
        return {
            "call_count": len(self._call_log),
            "call_log": list(self._call_log),
            "retry_count": 0,
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "last_error": None,
        }
