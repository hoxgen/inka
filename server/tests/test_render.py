import numpy as np

from inka_server import panel
from inka_server.render import render_cached, render_frame, render_indices
from inka_server.settings import DEFAULT_PALETTE, Settings

RED = DEFAULT_PALETTE["red"]
WHITE = DEFAULT_PALETTE["white"]
NO_ROT = Settings(rotate_180=False)


def share(region, color_index):
    return float(np.mean(region == color_index))


def test_output_shape_and_allowed_indices(make_image, tmp_path):
    rng = np.random.default_rng(1)
    from PIL import Image

    noise = Image.fromarray(rng.integers(0, 256, (600, 900, 3), dtype=np.uint8))
    path = tmp_path / "noise.png"
    noise.save(path)
    idx = render_indices(path, NO_ROT)
    assert idx.shape == (480, 800)
    assert set(np.unique(idx).tolist()) <= set(panel.ALLOWED_INDICES)


def test_top_left_block_lands_top_left(make_image):
    path = make_image("a.png", (800, 480), fill=WHITE, blocks=[(0, 0, 100, 100, RED)])
    idx = render_indices(path, NO_ROT)
    assert share(idx[10:90, 10:90], 3) > 0.95
    assert share(idx[390:470, 710:790], 1) > 0.95


def test_rotate_180_moves_block_to_bottom_right(make_image):
    path = make_image("a.png", (800, 480), fill=WHITE, blocks=[(0, 0, 100, 100, RED)])
    idx = render_indices(path, Settings(rotate_180=True))
    assert share(idx[390:470, 710:790], 3) > 0.95


def test_exif_orientation_is_applied(make_image):
    # Uloženo na výšku 480x800, EXIF 6 = zobrazit otočené o 90° doprava.
    # Uložený levý horní roh se zobrazí vpravo nahoře.
    path = make_image("phone.png", (480, 800), fill=WHITE, blocks=[(0, 0, 100, 100, RED)], exif_orientation=6)
    idx = render_indices(path, NO_ROT)
    assert share(idx[10:90, 710:790], 3) > 0.95


def test_cover_crop_keeps_center(make_image):
    blue = DEFAULT_PALETTE["blue"]
    path = make_image(
        "wide.png", (2400, 480), fill=WHITE, blocks=[(0, 0, 700, 480, blue), (1700, 0, 2400, 480, blue)]
    )
    idx = render_indices(path, NO_ROT)
    assert share(idx, 5) < 0.01


def test_portrait_is_rotated_into_native(make_image):
    path = make_image("p.png", (480, 800), fill=WHITE, blocks=[(0, 0, 100, 100, RED)])
    idx = render_indices(path, Settings(orientation="portrait", rotate_180=False))
    assert idx.shape == (480, 800)
    # rot90(k=1): levý horní roh obrazu na výšku → levý dolní roh nativního bufferu
    assert share(idx[390:470, 10:90], 3) > 0.95


def test_render_frame_len(make_image):
    path = make_image("a.png", (800, 480))
    assert len(render_frame(path, NO_ROT)) == panel.FRAME_LEN


def test_render_cached_reuses_and_invalidates(make_image, tmp_path):
    path = make_image("a.png", (800, 480), fill=WHITE, blocks=[(0, 0, 100, 100, RED)])
    cache = tmp_path / "cache"
    first = render_cached(path, NO_ROT, cache)
    assert len(list(cache.iterdir())) == 1
    assert render_cached(path, NO_ROT, cache) == first
    assert len(list(cache.iterdir())) == 1
    render_cached(path, Settings(rotate_180=True), cache)
    assert len(list(cache.iterdir())) == 2

import io
import threading

from PIL import Image

from inka_server.render import preview_cached, preview_png


def test_preview_png_landscape_uses_palette_colors(make_image):
    path = make_image("a.png", (800, 480), fill=WHITE, blocks=[(0, 0, 100, 100, RED)])
    im = Image.open(io.BytesIO(preview_png(path, Settings())))
    assert im.size == (800, 480)
    assert im.getpixel((50, 50))[:3] == RED  # bez rotate_180: levý horní roh
    colors = {c for _, c in im.convert("RGB").getcolors(maxcolors=4096)}
    assert colors <= set(DEFAULT_PALETTE.values())


def test_preview_png_portrait_size(make_image):
    path = make_image("p.png", (480, 800))
    im = Image.open(io.BytesIO(preview_png(path, Settings(orientation="portrait"))))
    assert im.size == (480, 800)


def test_preview_cached_reuses(make_image, tmp_path):
    path = make_image("a.png", (800, 480))
    cache = tmp_path / "cache"
    first = preview_cached(path, NO_ROT, cache)
    assert preview_cached(path, NO_ROT, cache) == first
    assert [p.suffix for p in cache.iterdir()] == [".png"]


def test_render_cached_concurrent_writers(make_image, tmp_path):
    path = make_image("a.png", (800, 480), fill=WHITE, blocks=[(0, 0, 100, 100, RED)])
    cache = tmp_path / "cache"
    results, errors = [], []

    def work():
        try:
            results.append(render_cached(path, NO_ROT, cache))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(set(results)) == 1
    assert [p.name for p in cache.iterdir() if p.suffix != ".bin"] == []


from inka_server.render import color_stats, source_png


def test_source_png_is_cropped_original_without_tone(make_image):
    path = make_image("g.png", (1600, 960), fill=(120, 120, 120))
    plain = Image.open(io.BytesIO(source_png(path, Settings(brightness=2.0), tone=False)))
    assert plain.size == (800, 480)
    assert plain.getpixel((400, 240))[:3] == (120, 120, 120)
    toned = Image.open(io.BytesIO(source_png(path, Settings(brightness=2.0), tone=True)))
    assert toned.getpixel((400, 240))[:3] == (240, 240, 240)


def test_source_png_portrait(make_image):
    path = make_image("p.png", (480, 800))
    assert Image.open(io.BytesIO(source_png(path, Settings(orientation="portrait"), tone=False))).size == (480, 800)


def test_color_stats(make_image):
    path = make_image("a.png", (800, 480), fill=WHITE, blocks=[(0, 0, 100, 100, RED)])
    stats = color_stats(path, NO_ROT)
    assert set(stats) == {"black", "white", "yellow", "red", "blue", "green"}
    assert abs(sum(stats.values()) - 100.0) < 0.01
    assert 2.4 < stats["red"] < 2.8  # 100×100 z 800×480 = 2,6 %


def test_cropped_view_is_cached_until_file_changes(make_image, monkeypatch):
    import os

    from inka_server import render

    path = make_image("c.png", (1600, 960), fill=(120, 120, 120))
    calls = []
    real = render._load
    monkeypatch.setattr(render, "_load", lambda p, size: calls.append(p) or real(p, size))
    render.prepare_view(path, Settings(brightness=1.2))
    render.prepare_view(path, Settings(contrast=1.3))
    render.view_indices(path, Settings(saturation=0.8))
    assert len(calls) == 1
    Image.new("RGB", (1600, 960), (10, 200, 10)).save(path)
    os.utime(path, ns=(1, 2_000_000_000_000_000_000))
    green = render.prepare_view(path, Settings(), tone=False)
    assert len(calls) == 2
    assert green.getpixel((10, 10)) == (10, 200, 10)


def test_render_uses_selected_dither(make_image):
    path = make_image("g.png", (800, 480), fill=(120, 120, 120))
    fs = render_indices(path, Settings(rotate_180=False))
    blue = render_indices(path, Settings(rotate_180=False, dither="blue-noise", grain=0.6))
    assert fs.shape == blue.shape == (480, 800)
    assert set(np.unique(blue).tolist()) <= set(panel.ALLOWED_INDICES)
    assert not np.array_equal(fs, blue)


def test_warmth_shifts_gray_toward_warm(make_image):
    from inka_server.render import prepare_view

    path = make_image("g.png", (800, 480), fill=(128, 128, 128))
    warm = prepare_view(path, Settings(warmth=1.0)).getpixel((400, 240))
    cool = prepare_view(path, Settings(warmth=-1.0)).getpixel((400, 240))
    neutral = prepare_view(path, Settings()).getpixel((400, 240))
    assert neutral == (128, 128, 128)
    assert warm[0] > warm[1] > warm[2]
    assert cool[0] < cool[1] < cool[2]


def test_tint_shifts_gray_toward_magenta(make_image):
    from inka_server.render import prepare_view

    path = make_image("g.png", (800, 480), fill=(128, 128, 128))
    mag = prepare_view(path, Settings(tint=1.0)).getpixel((400, 240))
    grn = prepare_view(path, Settings(tint=-1.0)).getpixel((400, 240))
    assert mag[1] < mag[0] and mag[1] < mag[2]
    assert grn[1] > grn[0] and grn[1] > grn[2]
    assert Settings(tint=0.2).render_hash() != Settings().render_hash()
