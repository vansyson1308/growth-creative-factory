"""Social / ad placement formats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Format:
    key: str
    width: int
    height: int
    label: str
    placements: str
    # Safe-zone insets as fractions of (top, right, bottom, left). Key content
    # stays inside so platform UI (profile bar, CTA sheet) never covers it.
    safe: Tuple[float, float, float, float] = (0.065, 0.065, 0.065, 0.065)

    @property
    def size(self) -> Tuple[int, int]:
        return self.width, self.height

    @property
    def aspect(self) -> float:
        return self.width / self.height

    @property
    def ratio_label(self) -> str:
        return self.label.split(" ")[-1]


FORMATS: Dict[str, Format] = {
    "square": Format(
        "square",
        1080,
        1080,
        "Feed 1:1",
        "Facebook & Instagram feed, carousel",
    ),
    "portrait": Format(
        "portrait",
        1080,
        1350,
        "Feed 4:5",
        "Facebook & Instagram feed (max mobile real estate)",
    ),
    "story": Format(
        "story",
        1080,
        1920,
        "Story 9:16",
        "Stories, Reels, TikTok, YouTube Shorts",
        safe=(0.125, 0.07, 0.19, 0.07),
    ),
    "landscape": Format(
        "landscape",
        1200,
        628,
        "Link 1.91:1",
        "Facebook link ads, LinkedIn, Google Display",
        safe=(0.08, 0.05, 0.08, 0.05),
    ),
    "wide": Format(
        "wide",
        1600,
        900,
        "Wide 16:9",
        "X / Twitter, YouTube thumbnails, presentations",
        safe=(0.075, 0.05, 0.075, 0.05),
    ),
}

DEFAULT_FORMATS: List[str] = ["square", "portrait", "story"]


def get_format(key: str) -> Format:
    k = str(key).strip().lower()
    if k not in FORMATS:
        raise KeyError(f"Unknown format {key!r}. Available: {', '.join(FORMATS)}")
    return FORMATS[k]


def parse_formats(value) -> List[str]:
    """Accept ``"square,story"``, a list, or ``"all"``."""
    if value is None or value == "":
        return list(DEFAULT_FORMATS)
    items = value.split(",") if isinstance(value, str) else list(value)
    keys = [str(i).strip().lower() for i in items if str(i).strip()]
    if keys == ["all"]:
        return list(FORMATS)
    for k in keys:
        get_format(k)
    return keys
