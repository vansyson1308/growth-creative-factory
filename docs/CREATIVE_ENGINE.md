# Creative Engine Reference

`gcf.creative` turns copy into finished social images. It is pure Python (Pillow + NumPy),
deterministic, and ships its own fonts, so the same input renders identically on macOS,
Windows, Linux and CI.

## Concepts

| Concept | Where | Summary |
|---|---|---|
| `Creative` | `gcf/creative/model.py` | One piece of copy: `headline`, `description`, `cta`, `eyebrow`, `badge`, `tag`, `image`, `template`. |
| `Format` | `gcf/creative/formats.py` | Canvas size + safe-zone insets for a placement. |
| `BrandKit` | `gcf/creative/brand.py` | Colours, logo, fonts, default CTA, grain, corner radius. |
| Template | `gcf/creative/templates.py` | A layout function that draws a `Creative` on a canvas for any `Format`. |

## Rendering

```python
from gcf.creative import Creative, render_creative, render_batch

c = Creative(
    headline="Run lighter. Go further.",
    description="Featherlight 180g build. Free returns for 30 days.",
    eyebrow="Launch week",
    cta="Shop the drop",       # optional — defaults to "Shop now" / "Mua ngay"
    badge="-30%",              # optional — auto-detected from "30% off", "Mua 1 tặng 1", "free shipping"
    image="photos/shoe.jpg",   # optional — otherwise brand-coloured generative art
)

render_creative(c, template="bold", fmt="story", brand="sunset").save("story.png")

items = render_batch(
    [c, ...],
    out_dir="out/creatives",
    formats=["square", "portrait", "story"],   # or "all"
    templates=None,                            # None = rotate through all six
    brand="brand_kit.yaml",
    image_format="png",                        # or "jpg"
    executor="auto",                           # auto | process | thread
)
```

`render_batch` writes `out_dir/<format>/<tag>_<template>.png` plus `manifest.csv`, never
overwrites duplicates, and uses a process pool for large batches (falling back to threads
where processes are unavailable). Use `executor="thread"` inside web servers.

Review surfaces:

```python
from gcf.creative.gallery import html_gallery, contact_sheet
html_gallery(items, "out/gallery.html", title="Spring launch")
contact_sheet([i.path for i in items], "out/contact_sheet.png", title="Spring launch")
```

## Copy sheets

`gcf render --input sheet.csv` (and `gcf.studio.creatives_from_file`) accept CSV or TSV with
flexible column names:

| Field | Accepted column names |
|---|---|
| headline | `headline`, `H1`, `variant_headline`, `title` |
| description | `description`, `DESC`, `variant_description`, `body`, `primary_text`, `text` |
| cta | `cta`, `call_to_action`, `button` |
| eyebrow | `eyebrow`, `kicker`, `label`, `H2` |
| badge | `badge`, `offer_badge`, `discount` |
| tag | `tag`, `id`, `name` |
| image | `image`, `image_path`, `photo`, `product_image` |
| template | `template` |

Rows without a headline are skipped. A UTF-8 BOM is tolerated.

## Brand kit YAML

```yaml
preset: aurora          # optional base preset
name: Acme Outdoor
primary: "#0F766E"
secondary: "#155E75"
accent: "#F59E0B"
dark: "#042F2E"
paper: "#F3F7F4"
ink: "#0B2A26"
handle: "@acmeoutdoor"
cta: ""
logo: logo.png          # relative to this YAML
fonts:
  display: fonts/Brand-Black.ttf   # roles: display, heading, body, serif
grain: 0.02
radius: 1.0
```

Colours are validated on load; unknown keys are ignored so kits stay forward-compatible.

## Typography rules

- Text is NFC-normalised and whitespace-collapsed.
- Headlines use balanced wrapping (no lonely last word) and the largest size that fits the
  layout box; words are never split across lines unless a single word is wider than the box.
- If copy cannot fit at the minimum size it is truncated with an ellipsis — nothing ever
  overflows the canvas.
- Tall formats (Stories) use a 1.22× type scale for supporting text.

## Design safeguards

- Story layouts keep key content out of the top 12.5% and bottom 19% (platform UI).
- CTAs switch to the accent colour if the brand gradient would lack contrast on dark stages.
- The promo template never invents a discount: without a real badge it shows "NEW" /
  "LAST CALL" (or "MỚI" / "SẮP HẾT").
- Internal IDs (tags) are never printed on the creative.

## Performance

Rendering is supersampled 2× for crisp shapes. Typical timings on a 4-core laptop: ~0.3 s for
a 1080×1080 image, ~0.6 s for a 1080×1920 story; batches parallelise across cores.

## Adding a template

1. Write `def _mytemplate(ctx: Ctx) -> None` in `gcf/creative/templates.py`. Paint the
   background onto `ctx.canvas`, then use `brand_mark`, `draw_column`, `sticker`,
   `cta_button` from `gcf/creative/components.py`. Respect `ctx.safe`, `ctx.is_wide`,
   `ctx.is_tall` and scale sizes by `ctx.u`.
2. Register it in `TEMPLATES`.
3. The parametrised test in `tests/test_creative.py` automatically renders it in every
   format; add a visual check with `gcf showcase`.
