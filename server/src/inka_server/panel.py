"""Formát bufferu panelu Spectra 6 (shodný s firmware/components/fb)."""
import numpy as np

WIDTH = 800
HEIGHT = 480
FRAME_LEN = WIDTH * HEIGHT // 2

PANEL_COLORS: list[tuple[str, int]] = [
    ("black", 0),
    ("white", 1),
    ("yellow", 2),
    ("red", 3),
    ("blue", 5),
    ("green", 6),
]
ALLOWED_INDICES = frozenset(i for _, i in PANEL_COLORS)


def pack(idx: np.ndarray) -> bytes:
    if idx.shape != (HEIGHT, WIDTH):
        raise ValueError(f"expected shape {(HEIGHT, WIDTH)}, got {idx.shape}")
    idx = idx.astype(np.uint8, copy=False)
    bad = np.setdiff1d(np.unique(idx), list(ALLOWED_INDICES))
    if bad.size:
        raise ValueError(f"invalid color indices: {bad.tolist()}")
    return ((idx[:, 0::2] << 4) | idx[:, 1::2]).astype(np.uint8).tobytes()
