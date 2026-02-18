"""Tests for deduplication/diversity module."""

from gcf.dedupe import (
    dedupe,
    dedupe_texts,
    detect_angle_bucket,
    enforce_diversity,
)


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


class TestDiversityEngine:
    def test_detect_angle_bucket(self):
        assert detect_angle_bucket("Limited offer today") == "urgency"
        assert detect_angle_bucket("Trusted by 10k users") == "social_proof"
        assert (
            detect_angle_bucket("Solve your daily workflow pain") == "problem_solution"
        )
        assert detect_angle_bucket("Discover the secret trick") == "curiosity"

    def test_enforce_diversity_reports_missing(self):
        texts = [
            "Save money now",  # benefit/urgency overlap
            "Save money now!",  # near duplicate
            "Save more today",  # similar benefit
        ]
        selected, missing, dist = enforce_diversity(
            texts,
            similarity_threshold=85,
            min_distinct_angles=2,
            target_count=3,
            angle_buckets=["benefit", "urgency", "social_proof"],
        )
        assert len(selected) >= 1
        assert len(missing) == 1
        assert sum(dist.values()) == len(selected)

    def test_enforce_diversity_keeps_multiple_angles(self):
        texts = [
            "Limited offer today",  # urgency
            "Trusted by 50k customers",  # social proof
            "Discover the hidden feature",  # curiosity
            "Solve your bottleneck quickly",  # problem/solution
        ]
        selected, missing, _ = enforce_diversity(
            texts,
            similarity_threshold=85,
            min_distinct_angles=3,
            target_count=4,
        )
        assert len(selected) >= 3
        assert missing == []


class TestDedupeAlias:
    def test_alias_produces_same_result(self):
        texts = ["Hello World", "Hello World", "Foo"]
        assert dedupe(texts) == dedupe_texts(texts)

    def test_empty_list(self):
        assert dedupe([]) == []
