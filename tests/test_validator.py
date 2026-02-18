"""Tests for validator module."""
import pytest
from gcf.validator import (
    char_count,
    check_char_limit,
    check_not_all_caps,
    check_policy,
    validate_headline,
    validate_description,
    validate_limits,
)
from gcf.config import PolicyConfig


class TestCharCount:
    """Tests for the public char_count() helper."""

    def test_ascii(self):
        assert char_count("Hello") == 5

    def test_spaces_included(self):
        # spaces count as characters
        assert char_count("A B") == 3

    def test_unicode_vietnamese(self):
        # each Vietnamese character is 1 code-point
        assert char_count("Tiết kiệm ngay hôm nay") == 22

    def test_empty_string(self):
        assert char_count("") == 0

    def test_exactly_30_chars(self):
        text = "a" * 30
        assert char_count(text) == 30

    def test_exactly_90_chars(self):
        text = "x" * 90
        assert char_count(text) == 90

    def test_emoji_is_one_char(self):
        # emoji is one Unicode code-point
        assert char_count("🚀") == 1

    def test_consistent_with_check_char_limit(self):
        text = "Ưu đãi ngay hôm nay"
        assert (char_count(text) <= 30) == check_char_limit(text, 30)


class TestCharLimit:
    def test_within_limit(self):
        assert check_char_limit("Hello World", 30) is True

    def test_exact_limit(self):
        assert check_char_limit("a" * 30, 30) is True

    def test_over_limit(self):
        assert check_char_limit("a" * 31, 30) is False

    def test_unicode_chars(self):
        # Vietnamese characters count as 1 each
        text = "Tiết kiệm ngay hôm nay"  # 22 chars
        assert check_char_limit(text, 30) is True
        assert check_char_limit(text, 10) is False

    def test_empty_string(self):
        assert check_char_limit("", 30) is True

    def test_spaces_count(self):
        text = "A B C D E"  # 9 chars including spaces
        assert check_char_limit(text, 9) is True
        assert check_char_limit(text, 8) is False


class TestAllCaps:
    def test_normal_text(self):
        assert check_not_all_caps("Hello World") is True

    def test_all_caps(self):
        assert check_not_all_caps("HELLO WORLD") is False

    def test_mixed_case(self):
        assert check_not_all_caps("HELLO world") is True

    def test_no_alpha(self):
        assert check_not_all_caps("123 !@#") is True


class TestPolicy:
    def test_clean_text(self):
        patterns = [r"(?i)cam kết", r"(?i)\bbest\b"]
        assert check_policy("Sản phẩm chất lượng", patterns) is True

    def test_blocked_cam_ket(self):
        patterns = [r"(?i)cam kết"]
        assert check_policy("Cam kết hoàn tiền", patterns) is False

    def test_blocked_best(self):
        patterns = [r"(?i)\bbest\b"]
        assert check_policy("The best product", patterns) is False

    def test_blocked_guarantee(self):
        patterns = [r"(?i)\bguarantee[d]?\b"]
        assert check_policy("Guaranteed results", patterns) is False


class TestValidateHeadline:
    def test_valid(self):
        result = validate_headline("Tiết kiệm ngay", 30, PolicyConfig())
        assert result["valid"] is True
        assert result["errors"] == []

    def test_too_long(self):
        result = validate_headline("A" * 31, 30)
        assert result["valid"] is False
        assert any("Exceeds" in e for e in result["errors"])

    def test_all_caps_rejected(self):
        result = validate_headline("BUY NOW", 30)
        assert result["valid"] is False

    def test_policy_violation(self):
        result = validate_headline("Best product", 30, PolicyConfig())
        assert result["valid"] is False


class TestValidateDescription:
    def test_valid(self):
        result = validate_description("Đăng ký nhận ưu đãi ngay!", 90, PolicyConfig())
        assert result["valid"] is True

    def test_too_long(self):
        result = validate_description("x" * 91, 90)
        assert result["valid"] is False


class TestValidateLimits:
    """Tests for the unified validate_limits() helper.

    Covers:
    - Both fields valid
    - H1 too long
    - DESC too long
    - Both too long simultaneously
    - Exact boundary (H1=30, DESC=90)
    - Policy violation in H1
    - Policy violation in DESC
    - Unicode-safe counting
    """

    def test_both_valid(self):
        result = validate_limits("Sale ngay hôm nay", "Mua ngay để nhận ưu đãi tốt nhất.")
        assert result["valid"] is True
        assert result["h1_errors"] == []
        assert result["desc_errors"] == []

    def test_h1_too_long(self):
        result = validate_limits("A" * 31, "Short desc")
        assert result["valid"] is False
        assert any("Exceeds" in e for e in result["h1_errors"])
        assert result["desc_errors"] == []

    def test_desc_too_long(self):
        # Use mixed-case H1 to avoid triggering the all-caps check
        result = validate_limits("Ok fine H1", "x" * 91)
        assert result["valid"] is False
        assert result["h1_errors"] == [], f"Unexpected h1 errors: {result['h1_errors']}"
        assert any("Exceeds" in e for e in result["desc_errors"])

    def test_both_too_long(self):
        result = validate_limits("A" * 31, "x" * 91)
        assert result["valid"] is False
        assert result["h1_errors"]
        assert result["desc_errors"]

    def test_exact_h1_boundary(self):
        # exactly 30 chars → valid
        result = validate_limits("a" * 30, "Desc fine.")
        assert result["h1_errors"] == []

    def test_exact_desc_boundary(self):
        # exactly 90 chars → valid
        result = validate_limits("H1 fine", "d" * 90)
        assert result["desc_errors"] == []

    def test_policy_violation_h1(self):
        result = validate_limits("Best deal", "Fine desc.", policy_cfg=PolicyConfig())
        assert result["valid"] is False
        assert any("Policy" in e for e in result["h1_errors"])

    def test_policy_violation_desc(self):
        result = validate_limits(
            "H1 ổn", "Cam kết hoàn tiền ngay.", policy_cfg=PolicyConfig()
        )
        assert result["valid"] is False
        assert any("Policy" in e for e in result["desc_errors"])

    def test_unicode_h1_within_limit(self):
        # "Tiết kiệm ngay" = 14 chars → well within 30
        result = validate_limits("Tiết kiệm ngay", "Mua hàng ngay hôm nay.")
        assert result["valid"] is True

    def test_unicode_h1_over_limit(self):
        # 31 Vietnamese characters → should fail
        long_viet = "Ấ" * 31
        result = validate_limits(long_viet, "Fine desc.")
        assert result["valid"] is False
        assert any("Exceeds" in e for e in result["h1_errors"])

    def test_returns_all_keys(self):
        result = validate_limits("H1", "Desc")
        assert set(result.keys()) == {"valid", "h1_errors", "desc_errors"}
