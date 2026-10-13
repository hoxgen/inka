#!/usr/bin/env python3
"""Porovná snímek panelu z kamery s originálem fotky (ladění barev).

Snímek se vyváží podle bílého papíru Pantone proužku (lineární RGB, papír = 245),
oba obrazy se zmenší na hrubou mřížku a porovnají v CIELAB.

Výstup na řádek: Δa* a Δb* (posun barvy: záporné = do zelena / do modra), ΔL* a poměr kontrastu.
Počítá zvlášť pro celý obraz a pro neutrální místa originálu (chroma < 12).

Použití (ze server/): uv run python ../tools/panel_metric.py FOTKA SNÍMEK [SNÍMEK …]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server" / "src"))
from inka_server.render import prepare_view  # noqa: E402
from inka_server.settings import Settings  # noqa: E402

PANEL = (322, 622, 1325, 1200)  # oblast obrazu panelu ve snímku (kamera MacBooku, 2026-10-13)
PAPER = (40, 1235, 400, 1305)   # bílý papír Pantone proužku
GRID = (40, 24)


def lin(a):
    a = a / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def lab(linrgb):
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = linrgb @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def grid_lin(im: Image.Image) -> np.ndarray:
    return lin(np.asarray(im.convert("RGB").resize(GRID, Image.Resampling.BOX), dtype=float))


def measure(photo: Path, shot: Path) -> dict:
    cam = Image.open(shot).convert("RGB")
    paper = np.median(np.asarray(cam.crop(PAPER), dtype=float).reshape(-1, 3), axis=0)
    gains = lin(np.full(3, 245.0)) / lin(paper)
    panel = lab(np.clip(grid_lin(cam.crop(PANEL)) * gains, 0, 1))
    orig = lab(grid_lin(prepare_view(photo, Settings(), tone=False)))
    neutral = np.hypot(orig[..., 1], orig[..., 2]) < 12
    d = panel - orig
    return {
        "da": d[..., 1].mean(), "db": d[..., 2].mean(), "dL": d[..., 0].mean(),
        "da_n": d[..., 1][neutral].mean() if neutral.any() else float("nan"),
        "db_n": d[..., 2][neutral].mean() if neutral.any() else float("nan"),
        "contrast": panel[..., 0].std() / max(orig[..., 0].std(), 1e-6),
    }


if __name__ == "__main__":
    photo = Path(sys.argv[1])
    print(f"{'snímek':42} {'Δa*':>6} {'Δb*':>6} {'Δa*n':>6} {'Δb*n':>6} {'ΔL*':>6} {'kontr':>6}")
    for s in sys.argv[2:]:
        r = measure(photo, Path(s))
        print(f"{Path(s).stem[-42:]:42} {r['da']:6.1f} {r['db']:6.1f} {r['da_n']:6.1f} {r['db_n']:6.1f} {r['dL']:6.1f} {r['contrast']:6.2f}")
