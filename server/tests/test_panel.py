import numpy as np
import pytest

from inka_server import panel


def blank(color=1):
    return np.full((panel.HEIGHT, panel.WIDTH), color, dtype=np.uint8)


def test_frame_len():
    assert panel.FRAME_LEN == 192000
    assert len(panel.pack(blank())) == 192000


def test_fill_packs_two_pixels_per_byte():
    assert panel.pack(blank(3))[:2] == b"\x33\x33"


def test_even_pixel_is_high_nibble():
    idx = blank(1)
    idx[0, 0] = 0
    idx[0, 1] = 6
    assert panel.pack(idx)[0] == 0x06
    idx[0, 1] = 1
    assert panel.pack(idx)[0] == 0x01


def test_row_stride_is_400_bytes():
    idx = blank(1)
    idx[1, 2] = 5
    assert panel.pack(idx)[400 + 1] == 0x51


def test_last_pixel():
    idx = blank(1)
    idx[479, 799] = 2
    assert panel.pack(idx)[-1] == 0x12


def test_rejects_index_4():
    idx = blank(1)
    idx[10, 10] = 4
    with pytest.raises(ValueError):
        panel.pack(idx)


def test_rejects_wrong_shape():
    with pytest.raises(ValueError):
        panel.pack(np.ones((800, 480), dtype=np.uint8))
