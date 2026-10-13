import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def make_image(tmp_path):
    """Uloží obrázek a vrátí cestu. `fill` je RGB, `blocks` je [(x0,y0,x1,y1,rgb)]."""

    def _make(name, size, fill=(255, 255, 255), blocks=(), exif_orientation=None):
        im = Image.new("RGB", size, fill)
        px = np.array(im)
        for x0, y0, x1, y1, rgb in blocks:
            px[y0:y1, x0:x1] = rgb
        im = Image.fromarray(px)
        path = tmp_path / name
        kwargs = {}
        if exif_orientation is not None:
            exif = Image.Exif()
            exif[0x0112] = exif_orientation
            kwargs["exif"] = exif.tobytes()
        im.save(path, **kwargs)
        return path

    return _make
