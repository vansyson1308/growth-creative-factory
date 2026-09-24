"""Creative engine — turn copy into on-brand social images, in bulk.

Quick use::

    from gcf.creative import Creative, render_creative

    img = render_creative(
        Creative(headline="Spring shoes, 30% off", description="Light, comfy, ready."),
        template="bold",
        fmt="story",
        brand="sunset",
    )
    img.save("story.png")
"""

from gcf.creative.brand import PRESETS, BrandKit, load_brand
from gcf.creative.engine import RenderedCreative, render_batch, render_creative
from gcf.creative.formats import DEFAULT_FORMATS, FORMATS, Format, parse_formats
from gcf.creative.model import Creative, detect_language, extract_badge
from gcf.creative.templates import TEMPLATE_ORDER, TEMPLATES, parse_templates

__all__ = [
    "BrandKit",
    "Creative",
    "DEFAULT_FORMATS",
    "FORMATS",
    "Format",
    "PRESETS",
    "RenderedCreative",
    "TEMPLATES",
    "TEMPLATE_ORDER",
    "detect_language",
    "extract_badge",
    "load_brand",
    "parse_formats",
    "parse_templates",
    "render_batch",
    "render_creative",
]
