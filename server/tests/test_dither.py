import time

import numpy as np
import pytest
from PIL import Image

from inka_server.dither import METHODS, dither
from inka_server.settings import DEFAULT_PALETTE

PAL = [DEFAULT_PALETTE[n] for n in ("black", "white", "yellow", "red", "blue", "green")]


def gradient(w=400, h=60):
    row = np.linspace(0, 255, w)
    return Image.fromarray(np.repeat(np.stack([row] * 3, axis=-1)[None], h, axis=0).astype(np.uint8))


@pytest.mark.parametrize("method", METHODS)
def test_shape_range_and_determinism(method):
    rng = np.random.default_rng(0)
    im = Image.fromarray(rng.integers(0, 256, (48, 80, 3), dtype=np.uint8))
    a = dither(im, PAL, method, strength=1.0, grain=0.5)
    b = dither(im, PAL, method, strength=1.0, grain=0.5)
    assert a.shape == (48, 80) and a.dtype == np.uint8
    assert a.max() < len(PAL)
    assert np.array_equal(a, b)  # zrno s pevným semínkem → stejný ETag i náhled


@pytest.mark.parametrize("method", METHODS)
def test_solid_palette_color_stays_pure(method):
    im = Image.new("RGB", (64, 32), DEFAULT_PALETTE["red"])
    out = dither(im, PAL, method, strength=1.0, grain=0.0)
    assert (out == 3).all()


@pytest.mark.parametrize("method", METHODS)
def test_gradient_brightness_is_monotonic(method):
    out = dither(gradient(), PAL, method, strength=1.0, grain=0.3)
    lum = np.array(PAL, dtype=float).mean(axis=1)[out]
    blocks = lum.reshape(lum.shape[0], 8, -1).mean(axis=(0, 2))
    assert all(b2 >= b1 - 4 for b1, b2 in zip(blocks, blocks[1:]))
    assert blocks[-1] - blocks[0] > 100


@pytest.mark.parametrize("method", ["fs-serpentine", "fs-grain", "jjn"])
def test_error_diffusion_preserves_mean(method):
    im = Image.new("RGB", (200, 100), (120, 120, 120))
    out = dither(im, PAL, method, strength=1.0, grain=0.3)
    mean = np.array(PAL, dtype=float)[out].mean()
    assert abs(mean - 120) < 8


def test_unknown_method_falls_back_to_fs():
    im = Image.new("RGB", (16, 8), (100, 100, 100))
    assert np.array_equal(dither(im, PAL, "nope", 1.0, 0.0), dither(im, PAL, "fs", 1.0, 0.0))


def test_full_frame_is_fast_enough():
    rng = np.random.default_rng(1)
    im = Image.fromarray(rng.integers(0, 256, (480, 800, 3), dtype=np.uint8))
    dither(im, PAL, "jjn", 1.0, 0.0)  # JIT zahřátí
    t = time.perf_counter()
    for m in METHODS:
        dither(im, PAL, m, 1.0, 0.4)
    assert (time.perf_counter() - t) / len(METHODS) < 0.5


@pytest.mark.parametrize("method", ["fs", "fs-serpentine", "fs-grain", "blue-noise", "jjn"])
def test_neutral_gray_stays_neutral_on_average(method):
    # Šedá vzniká mícháním barev palety; průměr musí zůstat neutrální (ne zelený nádech).
    im = Image.new("RGB", (160, 96), (90, 90, 90))
    out = dither(im, PAL, method, 1.0, 0.5)
    mean = np.array(PAL, dtype=float)[out].reshape(-1, 3).mean(axis=0)
    assert np.ptp(mean) < 12, mean
    assert abs(mean.mean() - 90) < 10, mean

