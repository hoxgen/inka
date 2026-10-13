"""Algoritmy ditheringu do palety panelu.

Všechny funkce vrací index barvy v předané paletě (0..len-1) pro každý pixel.
Náhodné prvky mají pevné semínko: stejná fotka a nastavení → stejný obraz (náhled = panel, stabilní ETag).
"""
from pathlib import Path

import numpy as np
from numba import njit
from PIL import Image

METHODS = ["fs", "fs-serpentine", "fs-grain", "blue-noise", "atkinson", "jjn"]

LABELS = {
    "fs": "Floyd–Steinberg",
    "fs-serpentine": "FS serpentine",
    "fs-grain": "FS + zrno",
    "blue-noise": "Modrý šum",
    "atkinson": "Atkinson",
    "jjn": "Jarvis–Judice–Ninke",
}

# (dx, dy, váha) – dx ve směru průchodu řádkem
_KERNELS = {
    "fs": [(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)],
    "atkinson": [(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)],
    "jjn": [
        (1, 0, 7), (2, 0, 5),
        (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
        (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1),
    ],
}
_DIVISORS = {"fs": 16.0, "atkinson": 8.0, "jjn": 48.0}  # Atkinson rozptýlí jen 6/8 chyby (záměrně)

_BLUE = np.load(Path(__file__).parent / "assets" / "bluenoise64.npy").astype(np.float32)
_BLUE = (_BLUE + 0.5) / _BLUE.size - 0.5  # práh v rozsahu (-0.5, 0.5)
_SEED = 20261013


@njit(cache=True)
def _diffuse(img, pal, dx, dy, wt, serpentine, strength, noise, noise_amp):
    h, w = img.shape[0], img.shape[1]
    k = pal.shape[0]
    buf = img.copy()
    out = np.zeros((h, w), dtype=np.uint8)
    for y in range(h):
        reverse = serpentine and (y % 2 == 1)
        for i in range(w):
            x = w - 1 - i if reverse else i
            best = 0
            best_d = 1e30
            for c in range(k):
                d = 0.0
                for ch in range(3):
                    v = buf[y, x, ch]
                    if v < 0.0:
                        v = 0.0
                    elif v > 255.0:
                        v = 255.0
                    t = v + noise[y, x] * noise_amp - pal[c, ch]
                    d += t * t
                if d < best_d:
                    best_d = d
                    best = c
            out[y, x] = best
            for ch in range(3):
                v = buf[y, x, ch]
                if v < 0.0:
                    v = 0.0
                elif v > 255.0:
                    v = 255.0
                err = (v - pal[best, ch]) * strength
                for j in range(dx.shape[0]):
                    xx = x - dx[j] if reverse else x + dx[j]
                    yy = y + dy[j]
                    if 0 <= xx < w and yy < h:
                        buf[yy, xx, ch] += err * wt[j]
    return out


def _pillow_fs(im: Image.Image, palette: list) -> np.ndarray:
    flat: list[int] = []
    for i in range(256):
        flat.extend(palette[i % len(palette)])
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat)
    q = im.quantize(palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
    return (np.asarray(q, dtype=np.uint8) % len(palette)).astype(np.uint8)


def dither(im: Image.Image, palette: list, method: str, strength: float, grain: float) -> np.ndarray:
    """`strength` = podíl rozptýlené chyby (difuzní metody), `grain` = síla zrna (fs-grain, blue-noise), obojí 0–1."""
    if method not in METHODS:
        method = "fs"
    if method == "fs":
        return _pillow_fs(im, palette)
    img = np.asarray(im.convert("RGB"), dtype=np.float32)
    pal = np.asarray(palette, dtype=np.float32)
    kernel = method if method in _KERNELS else "fs"  # fs-serpentine, fs-grain, blue-noise používají jádro FS
    taps = _KERNELS[kernel]
    dx = np.array([t[0] for t in taps], dtype=np.int64)
    dy = np.array([t[1] for t in taps], dtype=np.int64)
    wt = np.array([t[2] for t in taps], dtype=np.float32) / _DIVISORS[kernel]
    serpentine = True  # střídání směru řádků potlačí šikmé „červy“ a pruhy
    h, w = img.shape[:2]
    if method == "fs-grain":  # bílý šum v prahu: zrnité, místy shluky
        noise = np.random.default_rng(_SEED).uniform(-0.5, 0.5, (h, w)).astype(np.float32)
        amp = grain * 96.0
    elif method == "blue-noise":  # modrý šum v prahu: rovnoměrné zrno bez shluků, barvy drží difuze
        noise = np.ascontiguousarray(np.tile(_BLUE, (h // 64 + 1, w // 64 + 1))[:h, :w])
        amp = grain * 128.0
    else:
        noise = np.zeros((h, w), dtype=np.float32)
        amp = 0.0
    return _diffuse(img, pal, dx, dy, wt, serpentine, float(strength), noise, float(amp))
