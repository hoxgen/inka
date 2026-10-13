import functools
import hashlib
import io
import os
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from pillow_heif import register_heif_opener

from .dither import dither
from .panel import HEIGHT, PANEL_COLORS, WIDTH, pack
from .settings import Settings

register_heif_opener()

def _load(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as im:
        im.draft("RGB", (size[0] * 2, size[1] * 2))
        im = ImageOps.exif_transpose(im)
        return im.convert("RGB")


def _warm(im: Image.Image, warmth: float, tint: float = 0.0) -> Image.Image:
    # Zisky v lineárním světle jako vyvážení bílé. Teplota: +1 = červená ×1,25, modrá ×0,75.
    # Odstín: +1 = zelená ×0,75, červená a modrá ×1,1 (purpurová proti zeleným středním tónům).
    gains = (
        (1 + 0.25 * warmth) * (1 + 0.1 * tint),
        (1 + 0.05 * warmth) * (1 - 0.25 * tint),
        (1 - 0.25 * warmth) * (1 + 0.1 * tint),
    )
    lut: list[int] = []
    for g in gains:
        for i in range(256):
            c = i / 255
            lin = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            lin = min(1.0, lin * g)
            out = 12.92 * lin if lin <= 0.0031308 else 1.055 * lin ** (1 / 2.4) - 0.055
            lut.append(round(255 * out))
    return im.point(lut)


def _tone(im: Image.Image, s: Settings) -> Image.Image:
    if s.brightness != 1.0:
        im = ImageEnhance.Brightness(im).enhance(s.brightness)
    if s.contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(s.contrast)
    if s.saturation != 1.0:
        im = ImageEnhance.Color(im).enhance(s.saturation)
    if s.warmth != 0.0 or s.tint != 0.0:
        im = _warm(im, s.warmth, s.tint)
    if s.gamma != 1.0:
        lut = [round(255 * (i / 255) ** (1 / s.gamma)) for i in range(256)]
        im = im.point(lut * 3)
    return im


@functools.lru_cache(maxsize=48)
def _cropped(path: str, mtime_ns: int, file_size: int, size: tuple[int, int]) -> Image.Image:
    # Dekódování velkých JPEG trvá na pomalém serveru ~1 s; živý náhled pak mění jen tón a dithering malého výřezu.
    # mtime a velikost jsou v klíči, aby se změněný soubor načetl znovu.
    return ImageOps.fit(_load(Path(path), size), size, Image.Resampling.LANCZOS)


def prepare_view(path: Path, s: Settings, tone: bool = True) -> Image.Image:
    """Výřez na poměr panelu v orientaci pohledu; volitelně s úpravou tónu (vstup ditheringu)."""
    size = (WIDTH, HEIGHT) if s.orientation == "landscape" else (HEIGHT, WIDTH)
    st = path.stat()
    im = _cropped(str(path), st.st_mtime_ns, st.st_size, size).copy()
    return _tone(im, s) if tone else im


_PANEL_INDEX = np.array([i for _, i in PANEL_COLORS], dtype=np.uint8)


def view_indices(path: Path, s: Settings) -> np.ndarray:
    colors = [s.palette[name] for name, _ in PANEL_COLORS]
    idx = dither(prepare_view(path, s), colors, s.dither, s.dither_strength, s.grain)
    return _PANEL_INDEX[idx]


def source_png(path: Path, s: Settings, tone: bool) -> bytes:
    buf = io.BytesIO()
    prepare_view(path, s, tone).save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


def color_stats(path: Path, s: Settings) -> dict[str, float]:
    idx = view_indices(path, s)
    counts = np.bincount(idx.ravel(), minlength=256)
    return {name: float(counts[i]) * 100 / idx.size for name, i in PANEL_COLORS}


def to_native(idx: np.ndarray, s: Settings) -> np.ndarray:
    if s.orientation == "portrait":
        idx = np.rot90(idx, k=1)
    if s.rotate_180:
        idx = np.rot90(idx, k=2)
    return np.ascontiguousarray(idx)


def render_indices(path: Path, s: Settings) -> np.ndarray:
    return to_native(view_indices(path, s), s)


def render_frame(path: Path, s: Settings) -> bytes:
    return pack(render_indices(path, s))


def preview_png(path: Path, s: Settings) -> bytes:
    idx = view_indices(path, s)
    rgb = np.zeros((256, 3), dtype=np.uint8)
    for name, index in PANEL_COLORS:
        rgb[index] = s.palette[name]
    buf = io.BytesIO()
    Image.fromarray(rgb[idx]).save(buf, format="PNG", compress_level=1)  # rychlost > velikost (tailnet)
    return buf.getvalue()


def _write_atomic(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    except BaseException:
        os.unlink(tmp)
        raise


def _cached(path: Path, s: Settings, cache_dir: Path, suffix: str, produce) -> bytes:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    target = cache_dir / f"{digest}-{s.render_hash()}{suffix}"
    if target.is_file():
        return target.read_bytes()
    data = produce(path, s)
    _write_atomic(target, data)
    return data


def render_cached(path: Path, s: Settings, cache_dir: Path) -> bytes:
    return _cached(path, s, cache_dir, ".bin", render_frame)


def preview_cached(path: Path, s: Settings, cache_dir: Path) -> bytes:
    return _cached(path, s, cache_dir, ".png", preview_png)
