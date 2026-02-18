"""Mock provider for dry-run mode — no API calls, strict JSON responses."""

from __future__ import annotations

import json
import random
from typing import List

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

    Returns one of: 'selector', 'brand_voice', 'headline', 'description', 'checker', 'unknown'.
    Uses the first 5 lines (TASK / role declaration) to avoid false positives
    from context fields like 'original_headline' or 'current description'.
    """
    first_lines = "\n".join(prompt.splitlines()[:5]).lower()
    full_lower = prompt.lower()

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


class MockProvider(BaseProvider):
    """Deterministic-ish mock that returns strict JSON responses.

    All four agent types (selector, headline, description, checker) return
    valid JSON so that the real parsers can be exercised in dry-run mode.
    """

    def __init__(self, seed: int = 42, **kwargs):
        """Initialise with an optional RNG seed.

        Extra keyword arguments (e.g. a ``ProviderConfig``) are silently
        ignored so that callers can pass the same kwargs used for the real
        provider without crashing.
        """
        if not isinstance(seed, int):
            seed = 42
        self._rng = random.Random(seed)
        # Track the call sequence for test assertions
        self._call_log: List[str] = []

    def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        """Detect prompt type and return valid JSON mock response."""
        ptype = _detect_prompt_type(prompt)
        self._call_log.append(ptype)

        if ptype == "selector":
            return self._mock_strategy(prompt)
        elif ptype == "brand_voice":
            return self._mock_brand_voice()
        elif ptype == "headline":
            return self._mock_headlines()
        elif ptype == "description":
            return self._mock_descriptions()
        elif ptype == "checker":
            return self._mock_checker()
        else:
            # Generic fallback — return headlines JSON so pipeline doesn't break
            return self._mock_headlines()

    # ── Mock response builders ────────────────────────────────────────────────

    def _mock_strategy(self, prompt: str = "") -> str:
        """Return a selector-style strategy JSON."""
        # Try to extract ad_id from prompt for a realistic response
        ad_id = "mock_ad"
        for line in prompt.splitlines():
            if "ad_id" in line.lower() or "ad id" in line.lower():
                parts = line.split(":")
                if len(parts) > 1:
                    ad_id = parts[-1].strip().strip('"').strip()
                    break
        return json.dumps(
            {
                "ad_id": ad_id,
                "analysis": (
                    "CTR is below threshold likely due to generic headline copy "
                    "that does not differentiate from competitor ads."
                ),
                "strategy": "Test urgency + price-anchor angle to drive immediate clicks",
            }
        )

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

    def _mock_headlines(self, n: int = 10) -> str:
        """Return a headlines JSON array."""
        chosen = self._rng.sample(_HEADLINE_POOL, min(n, len(_HEADLINE_POOL)))
        return json.dumps({"headlines": chosen})

    def _mock_descriptions(self, n: int = 6) -> str:
        """Return a descriptions JSON array."""
        chosen = self._rng.sample(_DESC_POOL, min(n, len(_DESC_POOL)))
        return json.dumps({"descriptions": chosen})

    def _mock_checker(self) -> str:
        """Return an empty violations list — mock copy is always compliant."""
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
