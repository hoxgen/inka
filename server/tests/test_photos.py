from inka_server.photos import list_photos, order_photos


def touch(d, name):
    p = d / name
    p.write_bytes(b"x")
    return p


def test_list_photos_ignores_hidden_and_non_images(tmp_path):
    touch(tmp_path, "b.JPG")
    touch(tmp_path, "a.png")
    touch(tmp_path, ".syncthing.c.jpg.tmp")
    touch(tmp_path, ".hidden.jpg")
    touch(tmp_path, "notes.txt")
    (tmp_path / ".stfolder").mkdir()
    (tmp_path / "sub").mkdir()
    touch(tmp_path / "sub", "nested.jpg")
    assert [p.name for p in list_photos(tmp_path)] == ["a.png", "b.JPG"]


def test_list_photos_missing_dir(tmp_path):
    assert list_photos(tmp_path / "nope") == []


def test_order_name_keeps_input(tmp_path):
    photos = [tmp_path / n for n in ["a.jpg", "b.jpg", "c.jpg"]]
    assert order_photos(photos, "name") == photos


def test_order_shuffle_is_deterministic_permutation(tmp_path):
    photos = [tmp_path / f"{i:02}.jpg" for i in range(20)]
    first = order_photos(photos, "shuffle")
    assert first == order_photos(list(photos), "shuffle")
    assert sorted(first) == sorted(photos)
    assert first != photos
