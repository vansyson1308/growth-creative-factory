"""Brand kits — colours, fonts, logo and voice defaults for rendering."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from gcf.creative.color import RGB, hex_to_rgb


@dataclass
class BrandKit:
    """Visual identity applied to every rendered creative.

    Colours are hex strings. ``primary``/``secondary`` drive gradients,
    ``accent`` is used for CTAs and badges, ``dark``/``paper`` are the dark and
    light canvas colours and ``ink`` is the text colour on light surfaces.
    """

    name: str = "Aurora Labs"
    primary: str = "#5B5BF7"
    secondary: str = "#A855F7"
    accent: str = "#FBBF24"
    dark: str = "#0B0B1F"
    paper: str = "#F5F3FF"
    ink: str = "#151432"
    logo: Optional[str] = None  # transparent PNG, used on dark/colour canvases
    logo_dark: Optional[str] = None  # optional variant for light canvases
    handle: str = ""  # e.g. "@auroralabs" or "auroralabs.io"
    cta: str = ""  # default CTA; empty → language-aware default
    fonts: Dict[str, str] = field(default_factory=dict)  # role → font path
    grain: float = 0.02  # film-grain amount (0 disables)
    radius: float = 1.0  # corner-radius multiplier (0 = sharp, 2 = very round)

    # ── Colour accessors ────────────────────────────────────────────────────
    def rgb(self, key: str) -> RGB:
        return hex_to_rgb(getattr(self, key))

    def palette(self) -> List[RGB]:
        return [self.rgb(k) for k in ("primary", "secondary", "accent", "dark")]

    def validate(self) -> "BrandKit":
        for key in ("primary", "secondary", "accent", "dark", "paper", "ink"):
            hex_to_rgb(getattr(self, key))  # raises ValueError on bad input
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any], base: Optional["BrandKit"] = None):
        base_data = (base or cls()).to_dict()
        allowed = {f.name for f in fields(cls)}
        merged = {
            **base_data,
            **{k: v for k, v in (data or {}).items() if k in allowed},
        }
        return cls(**merged).validate()


PRESETS: Dict[str, BrandKit] = {
    "aurora": BrandKit(),
    "sunset": BrandKit(
        name="Sunset Supply",
        primary="#FF6B35",
        secondary="#E0245E",
        accent="#FFD166",
        dark="#2A0E1F",
        paper="#FFF4EC",
        ink="#2B1320",
    ),
    "verde": BrandKit(
        name="Verde Market",
        primary="#0F766E",
        secondary="#16A34A",
        accent="#FACC15",
        dark="#052E2B",
        paper="#F1F6EF",
        ink="#0B2A26",
    ),
    "tide": BrandKit(
        name="Tide & Co.",
        primary="#0284C7",
        secondary="#1E3A8A",
        accent="#F472B6",
        dark="#061A33",
        paper="#EEF6FB",
        ink="#0B1B33",
    ),
    "noir": BrandKit(
        name="Maison Noir",
        primary="#27272A",
        secondary="#0A0A0A",
        accent="#D4AF37",
        dark="#0A0A0A",
        paper="#F6F1E7",
        ink="#161616",
        radius=0.4,
    ),
    "blossom": BrandKit(
        name="Blossom Beauty",
        primary="#EC4899",
        secondary="#8B5CF6",
        accent="#FDE68A",
        dark="#3B0A2A",
        paper="#FFF1F7",
        ink="#3B0A2A",
        radius=1.6,
    ),
}

DEFAULT_BRAND = "aurora"


def load_brand(
    value: Any = None, overrides: Optional[Dict[str, Any]] = None
) -> BrandKit:
    """Resolve a brand kit from a preset name, YAML path, dict or BrandKit.

    ``overrides`` (e.g. ``{"name": "Acme"}``) are applied last.
    """
    if isinstance(value, BrandKit):
        kit = value
    elif isinstance(value, dict):
        preset = value.get("preset")
        base = PRESETS.get(str(preset).lower()) if preset else None
        kit = BrandKit.from_dict(value, base=base)
    elif value is None or str(value).strip() == "":
        kit = PRESETS[DEFAULT_BRAND]
    else:
        key = str(value).strip()
        if key.lower() in PRESETS:
            kit = PRESETS[key.lower()]
        else:
            p = Path(key).expanduser()
            if not p.is_file():
                raise ValueError(
                    f"Unknown brand kit {value!r}: not a preset "
                    f"({', '.join(PRESETS)}) and no such YAML file."
                )
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                raise ValueError(f"Brand kit file {p} must contain a mapping.")
            for key in ("logo", "logo_dark"):
                if data.get(key) and not Path(str(data[key])).is_absolute():
                    data[key] = str((p.parent / str(data[key])).resolve())
            fonts = data.get("fonts") or {}
            data["fonts"] = {
                role: (
                    fp
                    if Path(str(fp)).is_absolute()
                    else str((p.parent / str(fp)).resolve())
                )
                for role, fp in fonts.items()
            }
            preset = data.get("preset")
            base = PRESETS.get(str(preset).lower()) if preset else None
            kit = BrandKit.from_dict(data, base=base)
    if overrides:
        kit = BrandKit.from_dict({k: v for k, v in overrides.items() if v}, base=kit)
    return kit
