"""Mock provider for dry-run mode — no API calls."""
from __future__ import annotations

import hashlib
import random
from typing import List

from gcf.providers.base import BaseProvider

# Pools of realistic mock outputs
_HEADLINE_POOL = [
    "Tiết kiệm ngay hôm nay",
    "Ưu đãi có hạn",
    "Mua 1 tặng 1 hot deal",
    "Dùng thử miễn phí 7 ngày",
    "Giảm 30% toàn bộ sản phẩm",
    "Đăng ký nhận quà ngay",
    "Nâng cấp cuộc sống dễ dàng",
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
    "Hơn 10.000 khách hàng tin dùng. Bạn sẽ là người tiếp theo? Thử ngay!",
    "Giao hàng miễn phí toàn quốc. Đổi trả dễ dàng trong 30 ngày.",
    "Công nghệ tiên tiến, thiết kế hiện đại. Nâng tầm phong cách. Mua ngay!",
    "Ưu đãi đặc biệt cuối tuần — giảm thêm 15%. Đặt hàng ngay hôm nay!",
    "Tham gia cộng đồng hơn 50K thành viên. Đăng ký nhận tin ưu đãi!",
]


class MockProvider(BaseProvider):
    """Deterministic-ish mock that returns plausible ad copy."""

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        """Parse what the prompt is asking for and return mock data.

        Detection priority: check the TASK line first to avoid false
        matches from context fields like 'original_headline'.
        """
        # Look at the first ~200 chars (the TASK line) for the primary intent
        task_line = prompt[:250].lower()

        if "description variation" in task_line or "description" in task_line.split("task")[0] if "task" in task_line else False:
            pass  # fall through to full check below

        # More robust: count keyword occurrences in TASK line only
        first_lines = "\n".join(prompt.splitlines()[:5]).lower()
        if "generate" in first_lines and "description" in first_lines:
            return self._mock_descriptions()
        elif "generate" in first_lines and "headline" in first_lines:
            return self._mock_headlines()
        # Fallback: check whole prompt
        elif "description variation" in prompt.lower():
            return self._mock_descriptions()
        elif "headline variation" in prompt.lower():
            return self._mock_headlines()
        else:
            return "MOCK_RESPONSE: No specific type detected."

    def _mock_headlines(self, n: int = 10) -> str:
        chosen = self._rng.sample(_HEADLINE_POOL, min(n, len(_HEADLINE_POOL)))
        lines = [f"{i+1}. {h}" for i, h in enumerate(chosen)]
        return "\n".join(lines)

    def _mock_descriptions(self, n: int = 6) -> str:
        chosen = self._rng.sample(_DESC_POOL, min(n, len(_DESC_POOL)))
        lines = [f"{i+1}. {d}" for i, d in enumerate(chosen)]
        return "\n".join(lines)
