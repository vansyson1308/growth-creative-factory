"""Tests for deduplication module."""
import pytest
from gcf.dedupe import dedupe, dedupe_texts


class TestDedupe:
    def test_no_duplicates(self):
        texts = ["Hello", "World", "Foo"]
        result = dedupe_texts(texts, threshold=85)
        assert result == ["Hello", "World", "Foo"]

    def test_exact_duplicate(self):
        texts = ["Hello World", "Hello World", "Foo"]
        result = dedupe_texts(texts, threshold=85)
        assert result == ["Hello World", "Foo"]

    def test_near_duplicate(self):
        texts = ["Tiết kiệm ngay", "Tiết kiệm ngay!", "Khác biệt hoàn toàn"]
        result = dedupe_texts(texts, threshold=85)
        assert len(result) == 2
        assert result[0] == "Tiết kiệm ngay"
        assert result[1] == "Khác biệt hoàn toàn"

    def test_empty_input(self):
        assert dedupe_texts([], threshold=85) == []

    def test_blank_strings_removed(self):
        texts = ["Hello", "", "  ", "World"]
        result = dedupe_texts(texts, threshold=85)
        assert result == ["Hello", "World"]

    def test_low_threshold_removes_more(self):
        texts = ["Buy now sale", "Buy now deals", "Completely different"]
        result_strict = dedupe_texts(texts, threshold=50)
        result_loose = dedupe_texts(texts, threshold=90)
        assert len(result_strict) <= len(result_loose)


class TestDedupeAlias:
    """Verify that dedupe() is a fully-functional alias for dedupe_texts()."""

    def test_alias_produces_same_result(self):
        texts = ["Hello World", "Hello World", "Foo"]
        assert dedupe(texts) == dedupe_texts(texts)

    def test_no_duplicates(self):
        texts = ["Tiết kiệm", "Ưu đãi lớn", "Mua ngay"]
        assert dedupe(texts) == texts

    def test_exact_duplicate_removed(self):
        texts = ["Ưu đãi có hạn", "Ưu đãi có hạn", "Khác biệt"]
        result = dedupe(texts)
        assert len(result) == 2
        assert result[0] == "Ưu đãi có hạn"

    def test_near_duplicate_removed(self):
        # trailing punctuation variant
        texts = ["Tiết kiệm ngay", "Tiết kiệm ngay!", "Hoàn toàn khác"]
        result = dedupe(texts)
        assert len(result) == 2
        assert result[-1] == "Hoàn toàn khác"

    def test_empty_strings_skipped(self):
        assert dedupe(["Hello", "", "  ", "World"]) == ["Hello", "World"]

    def test_custom_threshold(self):
        texts = ["Buy shoes now", "Buy boots now", "Completely different text"]
        # High threshold → fewer removals
        result_strict = dedupe(texts, threshold=99)
        result_loose = dedupe(texts, threshold=40)
        assert len(result_strict) >= len(result_loose)

    def test_single_item_unchanged(self):
        assert dedupe(["Duy nhất"]) == ["Duy nhất"]

    def test_empty_list(self):
        assert dedupe([]) == []
