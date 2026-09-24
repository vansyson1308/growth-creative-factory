"""Brief → social posts. Uses the LLM when live, the offline copywriter when dry.

Every post is validated (length + policy) and anything missing or invalid is
back-filled offline, so a batch never comes back short.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from jinja2 import Template

from gcf import copywriter
from gcf.config import AppConfig, PolicyConfig
from gcf.copywriter import ANGLES, Brief, Post
from gcf.providers.base import BaseProvider
from gcf.validator import check_not_all_caps, check_policy

_PROMPT_PATH = Path(__file__).parent / "prompts" / "post_prompt.txt"

MAX_POST_HEADLINE = 60
MAX_POST_DESCRIPTION = 140
_LANG_NAMES = {"en": "English", "vi": "Vietnamese"}


def _parse_posts(raw: str) -> List[dict]:
    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", raw.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    posts = data.get("posts", []) if isinstance(data, dict) else []
    return [p for p in posts if isinstance(p, dict)]


def _valid(post: Post, policy: PolicyConfig) -> bool:
    if not post.headline or len(post.headline) > MAX_POST_HEADLINE:
        return False
    if len(post.description) > MAX_POST_DESCRIPTION:
        return False
    if not check_not_all_caps(post.headline):
        return False
    text = f"{post.headline} {post.description} {post.eyebrow} {post.cta}"
    return check_policy(text, policy.blocked_patterns)


def generate_posts(
    brief: Brief,
    provider: BaseProvider,
    n: int = 6,
    cfg: Optional[AppConfig] = None,
    seed: int = 0,
) -> List[Post]:
    """Return exactly *n* validated posts for *brief*."""
    cfg = cfg or AppConfig()
    lang = brief.lang()
    payload = {k: v for k, v in asdict(brief).items() if v}
    payload["n"] = n
    prompt = Template(_PROMPT_PATH.read_text(encoding="utf-8")).render(
        n=n,
        product=brief.product,
        audience=brief.audience,
        offer=brief.offer,
        benefits=brief.benefits,
        pain=brief.pain,
        tone=brief.tone,
        extra=brief.extra,
        language_name=_LANG_NAMES.get(lang, "English"),
        angles=ANGLES,
        max_headline_chars=MAX_POST_HEADLINE,
        max_description_chars=MAX_POST_DESCRIPTION,
        brief_json=json.dumps(payload, ensure_ascii=False),
    )
    raw = provider.generate(
        prompt,
        system="You write high-converting social media copy. Return ONLY valid JSON.",
    )

    posts: List[Post] = []
    seen = set()
    for item in _parse_posts(raw):
        post = Post(
            headline=str(item.get("headline", "")).strip(),
            description=str(item.get("description", "")).strip(),
            cta=str(item.get("cta", "")).strip(),
            eyebrow=str(item.get("eyebrow", "")).strip(),
            badge=str(item.get("badge", "")).strip(),
            angle=str(item.get("angle", "")).strip(),
        )
        key = post.headline.lower()
        if key in seen or not _valid(post, cfg.policy):
            continue
        seen.add(key)
        posts.append(post)
        if len(posts) >= n:
            break

    if len(posts) < n:  # back-fill offline so the batch is always complete
        for post in copywriter.write_posts(brief, n=n * 2, seed=seed):
            if len(posts) >= n:
                break
            if post.headline.lower() in seen or not _valid(post, cfg.policy):
                continue
            seen.add(post.headline.lower())
            posts.append(post)
    return posts[:n]
