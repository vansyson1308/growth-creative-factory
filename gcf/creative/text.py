"""Typography: wrapping, balancing and auto-fitting text into boxes."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PIL import ImageDraw, ImageFont

from gcf.creative.fonts import load_font

_WS = re.compile(r"\s+")


def clean_text(text: object) -> str:
    """NFC-normalise and collapse whitespace (handles NaN/None gracefully)."""
    if text is None:
        return ""
    s = str(text)
    if s.lower() == "nan":
        return ""
    return _WS.sub(" ", unicodedata.normalize("NFC", s)).strip()


def text_width(text: str, font: ImageFont.FreeTypeFont, tracking: float = 0.0) -> float:
    if not text:
        return 0.0
    w = font.getlength(text)
    if tracking:
        w += tracking * (len(text) - 1)
    return w


def _split_long_word(word: str, font, max_width: float) -> List[str]:
    parts: List[str] = []
    cur = ""
    for ch in word:
        if cur and font.getlength(cur + ch) > max_width:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def _word_widths(words: Tuple[str, ...], font) -> Tuple[List[float], float]:
    return [font.getlength(w) for w in words], font.getlength(" ")


def _wrap_measured(
    words: List[str], widths: List[float], space: float, font, max_width: float
) -> List[str]:
    lines: List[str] = []
    cur: List[str] = []
    cur_w = 0.0
    for word, ww in zip(words, widths):
        if not cur:
            if ww <= max_width:
                cur, cur_w = [word], ww
            else:
                pieces = _split_long_word(word, font, max_width)
                lines.extend(pieces[:-1])
                last = pieces[-1] if pieces else ""
                cur, cur_w = ([last], font.getlength(last)) if last else ([], 0.0)
            continue
        if cur_w + space + ww <= max_width:
            cur.append(word)
            cur_w += space + ww
            continue
        lines.append(" ".join(cur))
        cur, cur_w = [], 0.0
        if ww <= max_width:
            cur, cur_w = [word], ww
        else:
            pieces = _split_long_word(word, font, max_width)
            lines.extend(pieces[:-1])
            last = pieces[-1] if pieces else ""
            cur, cur_w = ([last], font.getlength(last)) if last else ([], 0.0)
    if cur:
        lines.append(" ".join(cur))
    return lines


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> List[str]:
    """Greedy word wrap; words longer than a line are split by character."""
    words = [w for w in clean_text(text).split(" ") if w]
    widths, space = _word_widths(tuple(words), font)
    return _wrap_measured(words, widths, space, font, max_width)


def wrap_balanced(
    text: str, font: ImageFont.FreeTypeFont, max_width: float
) -> List[str]:
    """Wrap into the same number of lines as greedy wrap, but as evenly as
    possible — avoids a lonely word on the last line of a headline."""
    words = [w for w in clean_text(text).split(" ") if w]
    widths, space = _word_widths(tuple(words), font)
    greedy = _wrap_measured(words, widths, space, font, max_width)
    n = len(greedy)
    if n <= 1 or any(w > max_width for w in widths):
        return greedy
    lo, hi = max(widths), max_width
    best = greedy
    for _ in range(12):
        mid = (lo + hi) / 2
        attempt = _wrap_measured(words, widths, space, font, mid)
        if len(attempt) <= n:
            best = attempt
            hi = mid
        else:
            lo = mid
    return best


def splits_words(text: str, lines: List[str]) -> bool:
    """True when wrapping had to break a word across lines."""
    return " ".join(lines).split(" ") != [w for w in clean_text(text).split(" ") if w]


@dataclass
class TextBlock:
    lines: List[str]
    font: ImageFont.FreeTypeFont
    size: int
    line_height: float
    ascent: int
    descent: int
    tracking: float = 0.0

    @property
    def width(self) -> float:
        return max(
            (text_width(line, self.font, self.tracking) for line in self.lines),
            default=0.0,
        )

    @property
    def height(self) -> float:
        if not self.lines:
            return 0.0
        return self.ascent + self.descent + (len(self.lines) - 1) * self.line_height


def layout(
    text: str,
    path: str,
    size: int,
    max_width: float,
    line_spacing: float = 1.2,
    balanced: bool = False,
    tracking: float = 0.0,
) -> TextBlock:
    font = load_font(path, size)
    lines = (
        wrap_balanced(text, font, max_width)
        if balanced
        else wrap_text(text, font, max_width)
    )
    ascent, descent = font.getmetrics()
    return TextBlock(lines, font, size, size * line_spacing, ascent, descent, tracking)


def fit_text(
    text: str,
    path: str,
    max_width: float,
    max_height: float,
    max_size: int,
    min_size: int,
    max_lines: Optional[int] = None,
    line_spacing: float = 1.2,
    balanced: bool = False,
) -> TextBlock:
    """Find the largest font size so *text* fits inside the box.

    If the text cannot fit even at *min_size*, it is truncated with an ellipsis
    so nothing ever overflows the design.
    """
    text = clean_text(text)
    min_size = max(1, min(min_size, max_size))

    def fits(block: TextBlock) -> bool:
        if max_lines is not None and len(block.lines) > max_lines:
            return False
        if splits_words(text, block.lines):
            return False
        return block.height <= max_height and block.width <= max_width + 0.5

    lo, hi = min_size, max_size
    best: Optional[TextBlock] = None
    while lo <= hi:
        mid = (lo + hi) // 2
        block = layout(text, path, mid, max_width, line_spacing, balanced)
        if fits(block):
            best = block
            lo = mid + 1
        else:
            hi = mid - 1
    if best is not None:
        return best
    return _truncate(
        text, path, min_size, max_width, max_height, max_lines, line_spacing
    )


def _truncate(
    text: str,
    path: str,
    size: int,
    max_width: float,
    max_height: float,
    max_lines: Optional[int],
    line_spacing: float,
) -> TextBlock:
    block = layout(text, path, size, max_width, line_spacing)
    allowed = len(block.lines)
    if max_lines is not None:
        allowed = min(allowed, max_lines)
    while allowed > 1 and (
        block.ascent + block.descent + (allowed - 1) * block.line_height > max_height
    ):
        allowed -= 1
    allowed = max(1, allowed)
    if allowed >= len(block.lines):
        return block
    lines = block.lines[:allowed]
    last = lines[-1]
    font = block.font
    while last and font.getlength(last + "…") > max_width:
        last = last[:-1].rstrip()
    lines[-1] = (last.rstrip(" ,.;:-–—") + "…") if last else "…"
    block.lines = lines
    return block


def draw_block(
    draw: ImageDraw.ImageDraw,
    block: TextBlock,
    xy: Tuple[float, float],
    fill,
    align: str = "left",
    box_width: Optional[float] = None,
) -> Tuple[float, float, float, float]:
    """Draw a :class:`TextBlock` with its top-left at *xy*.

    ``align`` is ``left`` / ``center`` / ``right`` within *box_width* (defaults
    to the block width). Returns the bounding box actually used.
    """
    x0, y0 = xy
    bw = box_width if box_width is not None else block.width
    baseline = y0 + block.ascent
    min_x = x0 + bw
    max_x = x0
    for line in block.lines:
        lw = text_width(line, block.font, block.tracking)
        if align == "center":
            lx = x0 + (bw - lw) / 2
        elif align == "right":
            lx = x0 + bw - lw
        else:
            lx = x0
        _draw_line(draw, line, (lx, baseline), block.font, fill, block.tracking)
        min_x, max_x = min(min_x, lx), max(max_x, lx + lw)
        baseline += block.line_height
    return min_x, y0, max_x, y0 + block.height


def _draw_line(draw, text, xy, font, fill, tracking: float) -> None:
    x, y = xy
    if not tracking:
        draw.text((x, y), text, font=font, fill=fill, anchor="ls")
        return
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += font.getlength(ch) + tracking
