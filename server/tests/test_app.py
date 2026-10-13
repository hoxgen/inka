import json

import pytest
from fastapi.testclient import TestClient

from inka_server import panel
from inka_server.app import Config, create_app
from inka_server.settings import DEFAULT_PALETTE

TOKEN = "t0ken"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def env(tmp_path):
    photos = tmp_path / "photos"
    data = tmp_path / "data"
    photos.mkdir()
    data.mkdir()
    (data / "settings.json").write_text(json.dumps({"interval_s": 600, "order": "name"}))
    now = {"t": 1000.0}
    app = create_app(Config(photos, data, TOKEN), clock=lambda: now["t"])
    return TestClient(app), photos, data, now


def add_photo(make_image, photos, name, color):
    path = make_image(name, (800, 480), fill=color)
    path.rename(photos / name)


def test_requires_token(env):
    client, *_ = env
    assert client.get("/api/v1/frame").status_code == 401
    assert client.get("/api/v1/frame", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_empty_folder_gives_204_with_sleep(env):
    client, *_ = env
    r = client.get("/api/v1/frame", headers=AUTH)
    assert r.status_code == 204
    assert r.headers["X-Inka-Sleep-Seconds"] == "230"
    assert r.headers["X-Inka-Sleep-Mode"] == "light"


def test_frame_200_then_304(env, make_image):
    client, photos, _, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    r = client.get("/api/v1/frame", headers=AUTH)
    assert r.status_code == 200
    assert len(r.content) == panel.FRAME_LEN
    assert r.headers["content-type"] == "application/octet-stream"
    etag = r.headers["ETag"]
    r2 = client.get("/api/v1/frame", headers={**AUTH, "If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.headers["ETag"] == etag
    assert r2.headers["X-Inka-Sleep-Seconds"] == "230"


def test_next_slot_shows_next_photo(env, make_image):
    client, photos, _, now = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    add_photo(make_image, photos, "b.png", DEFAULT_PALETTE["blue"])
    first = client.get("/api/v1/frame", headers=AUTH).headers["ETag"]
    now["t"] += 600
    assert client.get("/api/v1/frame", headers=AUTH).headers["ETag"] != first


def test_button_advances_rotation(env, make_image):
    client, photos, data, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    add_photo(make_image, photos, "b.png", DEFAULT_PALETTE["blue"])
    first = client.get("/api/v1/frame", headers=AUTH).headers["ETag"]
    second = client.get("/api/v1/frame?wake=button", headers=AUTH).headers["ETag"]
    assert second != first
    assert json.loads((data / "state.json").read_text())["offset"] == 1


def test_corrupt_photo_is_skipped(env, make_image):
    client, photos, data, _ = env
    # clock 1000, interval 600 → slot 1 → pořadí [a.png, b.jpg] vybere poškozenou b.jpg
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    (photos / "b.jpg").write_bytes(b"not an image")
    r = client.get("/api/v1/frame", headers=AUTH)
    assert r.status_code == 200
    assert json.loads((data / "state.json").read_text())["current_photo"] == "a.png"


def test_only_corrupt_photos_gives_204(env):
    client, photos, *_ = env
    (photos / "a.jpg").write_bytes(b"not an image")
    assert client.get("/api/v1/frame", headers=AUTH).status_code == 204


def test_device_report_is_stored(env, make_image):
    client, photos, data, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    client.get("/api/v1/frame?battery_mv=3790&fw=abc123&wake=timer", headers=AUTH)
    st = json.loads((data / "state.json").read_text())
    assert st["battery_mv"] == 3790
    assert st["fw"] == "abc123"
    assert st["wake"] == "timer"
    assert st["last_seen"].endswith("+00:00")


def test_bad_battery_value_is_ignored(env):
    client, _, data, _ = env
    client.get("/api/v1/frame?battery_mv=abc", headers=AUTH)
    assert json.loads((data / "state.json").read_text())["battery_mv"] is None


def test_interval_header_is_sent(env, make_image):
    client, photos, _, _ = env
    assert client.get("/api/v1/frame", headers=AUTH).headers["X-Inka-Interval-Seconds"] == "600"
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    r = client.get("/api/v1/frame", headers=AUTH)
    assert r.headers["X-Inka-Interval-Seconds"] == "600"
    r2 = client.get("/api/v1/frame", headers={**AUTH, "If-None-Match": r.headers["ETag"]})
    assert r2.headers["X-Inka-Interval-Seconds"] == "600"



def test_frame_is_not_cacheable(env, make_image):
    client, photos, _, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    assert client.get("/api/v1/frame", headers=AUTH).headers["Cache-Control"] == "no-store"
    assert client.get("/api/v1/frame", headers=AUTH).headers["Cache-Control"] == "no-store"


def test_hidden_photo_is_not_served(env, make_image):
    from inka_server.library import set_hidden

    client, photos, data, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    add_photo(make_image, photos, "b.png", DEFAULT_PALETTE["blue"])
    set_hidden(data, "b.png", True)
    for _ in range(3):
        client.get("/api/v1/frame?wake=button", headers=AUTH)
        assert json.loads((data / "state.json").read_text())["current_photo"] == "a.png"


def test_all_hidden_gives_204(env, make_image):
    from inka_server.library import set_hidden

    client, photos, data, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    set_hidden(data, "a.png", True)
    assert client.get("/api/v1/frame", headers=AUTH).status_code == 204


def test_view_header_describes_orientation(env, make_image):
    client, photos, data, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    assert client.get("/api/v1/frame", headers=AUTH).headers["X-Inka-View"] == "landscape;rot180"
    (data / "settings.json").write_text(json.dumps({"orientation": "portrait", "rotate_180": False}))
    assert client.get("/api/v1/frame", headers=AUTH).headers["X-Inka-View"] == "portrait;rot0"


def test_device_report_with_temperature_and_charging(env, make_image):
    client, photos, data, _ = env
    add_photo(make_image, photos, "a.png", DEFAULT_PALETTE["red"])
    client.get("/api/v1/frame?battery_mv=3790&battery_pct=54&charging=1&temp_c=22.5&wake=timer", headers=AUTH)
    st = json.loads((data / "state.json").read_text())
    assert st["battery_pct"] == 54 and st["charging"] is True and st["temp_c"] == 22.5


def test_bad_temperature_is_ignored(env):
    client, _, data, _ = env
    client.get("/api/v1/frame?temp_c=nan&battery_pct=abc&charging=x", headers=AUTH)
    st = json.loads((data / "state.json").read_text())
    assert st["temp_c"] is None and st["battery_pct"] is None and st["charging"] is None


def mode_and_sleep(client, query=""):
    r = client.get(f"/api/v1/frame{query}", headers=AUTH)
    return r.headers["X-Inka-Sleep-Mode"], r.headers["X-Inka-Sleep-Seconds"]


@pytest.fixture
def hourly(env):
    client, photos, data, now = env
    (data / "settings.json").write_text(json.dumps({"interval_s": 3600, "order": "name"}))
    return client, data


def test_auto_is_default_and_follows_usb(hourly):
    client, data = hourly
    assert mode_and_sleep(client, "?usb=1") == ("light", "300")
    assert mode_and_sleep(client, "?usb=0") == ("deep", "2630")
    assert json.loads((data / "state.json").read_text())["usb"] is False


def test_auto_without_usb_report_is_light(hourly):
    client, _ = hourly
    assert mode_and_sleep(client) == ("light", "300")  # starší firmware nehlásí usb → bezpečně lehký spánek


def test_manual_mode_overrides_usb(hourly):
    client, data = hourly
    (data / "settings.json").write_text(json.dumps({"interval_s": 3600, "order": "name", "sleep_mode": "deep"}))
    assert mode_and_sleep(client, "?usb=1") == ("deep", "2630")
    (data / "settings.json").write_text(json.dumps({"interval_s": 3600, "order": "name", "sleep_mode": "light"}))
    assert mode_and_sleep(client, "?usb=0") == ("light", "300")
