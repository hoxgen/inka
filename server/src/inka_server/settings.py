import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .dither import METHODS as DITHER_METHODS
from .panel import PANEL_COLORS
from .storage import read_json, write_json_atomic

# Barvy panelu naměřené kamerou vyváženou podle papíru Pantone proužku (docs/hw-notes.md).
DEFAULT_PALETTE: dict[str, tuple[int, int, int]] = {
    "black": (37, 33, 47),
    "white": (175, 185, 188),
    "yellow": (196, 170, 53),
    "red": (128, 17, 23),
    "blue": (9, 69, 133),
    "green": (64, 89, 74),
}

ORDERS = ("shuffle", "name")
ORIENTATIONS = ("landscape", "portrait")
SLEEP_MODES = ("auto", "light", "deep")  # auto: podle napájení z USB, které hlásí rámeček
RENDER_FIELDS = (
    "orientation", "rotate_180", "brightness", "contrast", "saturation", "gamma", "palette",
    "dither", "dither_strength", "grain", "warmth", "tint",
)


@dataclass(frozen=True)
class Settings:
    interval_s: int = 3600
    order: str = "shuffle"
    orientation: str = "landscape"
    rotate_180: bool = True
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0
    sleep_mode: str = "auto"
    dither: str = "fs"
    dither_strength: float = 1.0  # podíl rozptýlené chyby
    grain: float = 0.4  # síla zrna (FS + zrno, modrý šum)
    warmth: float = 0.0  # -1 chladnější … +1 teplejší; kompenzuje chladnou bílou panelu
    tint: float = 0.0  # -1 zelenější … +1 purpurovější; kompenzuje zelené střední tóny panelu
    palette: dict = field(default_factory=lambda: dict(DEFAULT_PALETTE))

    def render_hash(self) -> str:
        d = asdict(self)
        payload = json.dumps({k: d[k] for k in RENDER_FIELDS}, sort_keys=True, default=list)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _choice(value, options):
    return value if value in options else options[0]


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _factor(value) -> float:
    if not _number(value):
        return 1.0
    return min(3.0, max(0.1, float(value)))


def _unit(value, default: float) -> float:
    if not _number(value):
        return default
    return min(1.0, max(0.0, float(value)))


def _palette(value) -> dict:
    result = dict(DEFAULT_PALETTE)
    if not isinstance(value, dict):
        return result
    for name, _ in PANEL_COLORS:
        rgb = value.get(name)
        if (
            isinstance(rgb, (list, tuple))
            and len(rgb) == 3
            and all(isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255 for c in rgb)
        ):
            result[name] = tuple(rgb)
    return result


def settings_from_dict(d: dict) -> Settings:
    interval = d.get("interval_s", 3600)
    if not _number(interval):
        interval = 3600
    rotate = d.get("rotate_180", True)
    return Settings(
        interval_s=max(60, int(interval)),
        order=_choice(d.get("order"), ORDERS),
        orientation=_choice(d.get("orientation"), ORIENTATIONS),
        rotate_180=rotate if isinstance(rotate, bool) else True,
        brightness=_factor(d.get("brightness", 1.0)),
        contrast=_factor(d.get("contrast", 1.0)),
        saturation=_factor(d.get("saturation", 1.0)),
        gamma=_factor(d.get("gamma", 1.0)),
        sleep_mode=_choice(d.get("sleep_mode"), SLEEP_MODES),
        palette=_palette(d.get("palette")),
        dither=_choice(d.get("dither"), DITHER_METHODS),
        dither_strength=_unit(d.get("dither_strength", 1.0), 1.0),
        grain=_unit(d.get("grain", 0.4), 0.4),
        warmth=min(1.0, max(-1.0, float(d["warmth"]))) if _number(d.get("warmth")) else 0.0,
        tint=min(1.0, max(-1.0, float(d["tint"]))) if _number(d.get("tint")) else 0.0,
    )


def load_settings(data_dir: Path) -> Settings:
    return settings_from_dict(read_json(data_dir / "settings.json") or {})


def save_settings(data_dir: Path, s: Settings) -> None:
    d = asdict(s)
    d["palette"] = {k: list(v) for k, v in s.palette.items()}
    write_json_atomic(data_dir / "settings.json", d)
