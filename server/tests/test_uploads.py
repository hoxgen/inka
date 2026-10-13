import io

import pytest
from PIL import Image

from inka_server.uploads import MAX_UPLOAD_BYTES, safe_name, save_upload


def png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (200, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def test_safe_name_strips_paths_and_leading_dots():
    assert safe_name("../../etc/passwd.JPG") == "passwd.jpg"
    assert safe_name("C:\\Users\\x\\Dovolená 2026.HEIC") == "Dovolená 2026.heic"
    assert safe_name(".hidden.jpg") == "hidden.jpg"
    assert safe_name("...") == "foto"
    assert safe_name("a\x00b.png") == "ab.png"


def test_save_upload_writes_and_does_not_overwrite(tmp_path):
    first = save_upload(tmp_path, "pes.png", png_bytes())
    second = save_upload(tmp_path, "pes.png", png_bytes())
    assert first.name == "pes.png"
    assert second.name == "pes-2.png"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pes-2.png", "pes.png"]


def test_save_upload_rejects_non_image(tmp_path):
    with pytest.raises(ValueError):
        save_upload(tmp_path, "x.jpg", b"not an image")
    assert list(tmp_path.iterdir()) == []


def test_save_upload_rejects_extension(tmp_path):
    with pytest.raises(ValueError):
        save_upload(tmp_path, "x.gif", png_bytes())


def test_save_upload_rejects_too_big(tmp_path):
    with pytest.raises(ValueError):
        save_upload(tmp_path, "x.png", b"0" * (MAX_UPLOAD_BYTES + 1))


def test_uploaded_file_is_readable_by_others(tmp_path):
    # Syncthing může běžet pod jiným uživatelem než server.
    path = save_upload(tmp_path, "pes.png", png_bytes())
    assert path.stat().st_mode & 0o044 == 0o044
