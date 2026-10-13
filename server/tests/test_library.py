import json

from inka_server.library import load_hidden, set_hidden, visible_photos


def test_hide_and_unhide(tmp_path):
    assert load_hidden(tmp_path) == set()
    set_hidden(tmp_path, "b.jpg", True)
    set_hidden(tmp_path, "a.jpg", True)
    assert load_hidden(tmp_path) == {"a.jpg", "b.jpg"}
    assert json.loads((tmp_path / "library.json").read_text()) == {"hidden": ["a.jpg", "b.jpg"]}
    set_hidden(tmp_path, "a.jpg", False)
    assert load_hidden(tmp_path) == {"b.jpg"}


def test_visible_photos_excludes_hidden(tmp_path):
    photos = tmp_path / "p"
    photos.mkdir()
    for n in ("a.jpg", "b.jpg"):
        (photos / n).write_bytes(b"x")
    set_hidden(tmp_path, "a.jpg", True)
    assert [p.name for p in visible_photos(photos, tmp_path)] == ["b.jpg"]


def test_corrupt_library_means_nothing_hidden(tmp_path):
    (tmp_path / "library.json").write_text('{"hidden": "oops"}')
    assert load_hidden(tmp_path) == set()
