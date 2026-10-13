import io
import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from inka_server.app import Config, create_app
from inka_server.settings import DEFAULT_PALETTE

TOKEN = "t0ken"


@pytest.fixture
def web(tmp_path):
    photos = tmp_path / "photos"
    data = tmp_path / "data"
    photos.mkdir()
    data.mkdir()
    (data / "settings.json").write_text(json.dumps({"interval_s": 600, "order": "name"}))
    now = {"t": 1000.0}
    app = create_app(Config(photos, data, TOKEN), clock=lambda: now["t"])
    return TestClient(app, follow_redirects=False), photos, data


def put(photos, name, color=(200, 0, 0), size=(800, 480)):
    Image.new("RGB", size, color).save(photos / name)


def frame_photo(client, data):
    client.get("/api/v1/frame", headers={"Authorization": f"Bearer {TOKEN}"})
    return json.loads((data / "state.json").read_text())["current_photo"]


def test_gallery_lists_photos(web):
    client, photos, _ = web
    put(photos, "a.png")
    put(photos, "b.png")
    r = client.get("/")
    assert r.status_code == 200
    assert "a.png" in r.text and "b.png" in r.text


def test_gallery_empty_state(web):
    client, *_ = web
    assert "Přetáhněte sem fotky" in client.get("/").text


def test_cloudflare_requests_are_denied(web):
    client, photos, _ = web
    put(photos, "a.png")
    cf = {"Cf-Connecting-Ip": "1.2.3.4"}
    assert client.get("/", headers=cf).status_code == 404
    assert client.get("/settings", headers=cf).status_code == 404
    assert client.post("/photo/a.png/hide", headers=cf).status_code == 404


def test_preview_and_original(web):
    client, photos, _ = web
    put(photos, "a.png")
    r = client.get("/photo/a.png/preview.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(r.content)).size == (800, 480)
    o = client.get("/photo/a.png/original.jpg")
    assert o.status_code == 200 and o.headers["content-type"] == "image/jpeg"


def test_preview_with_overrides_differs(web):
    client, photos, _ = web
    put(photos, "a.png", color=(120, 120, 120))
    base = client.get("/photo/a.png/preview.png").content
    bright = client.get("/photo/a.png/preview.png?brightness=2.0").content
    assert base != bright


def test_unknown_and_traversal_names_404(web):
    client, photos, data = web
    (data / "secret.png").write_bytes(b"x")
    assert client.get("/photo/nope.png/preview.png").status_code == 404
    assert client.get("/photo/..%2Fdata%2Fsecret.png/preview.png").status_code == 404


def test_photo_with_spaces_and_diacritics_roundtrip(web):
    client, photos, _ = web
    name = "Dovolená #1 léto.png"
    put(photos, name)
    page = client.get("/").text
    assert f"/photo/{quote(name)}/preview.png" in page
    assert client.get(f"/photo/{quote(name)}/preview.png").status_code == 200


def test_hide_and_show(web):
    client, photos, data = web
    put(photos, "a.png")
    put(photos, "b.png")
    assert client.post("/photo/b.png/hide").status_code == 303
    assert json.loads((data / "library.json").read_text())["hidden"] == ["b.png"]
    client.post("/photo/b.png/show")
    assert json.loads((data / "library.json").read_text())["hidden"] == []


def test_next_makes_photo_current(web):
    client, photos, data = web
    for n in ("a.png", "b.png", "c.png"):
        put(photos, n)
    assert client.post("/photo/a.png/next").status_code == 303
    assert frame_photo(client, data) == "a.png"
    client.post("/photo/c.png/next")
    assert frame_photo(client, data) == "c.png"


def test_upload_saves_files_and_reports_errors(web):
    client, photos, _ = web
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (0, 0, 200)).save(buf, format="JPEG")
    files = [
        ("files", ("Léto.JPG", buf.getvalue(), "image/jpeg")),
        ("files", ("bad.jpg", b"nope", "image/jpeg")),
    ]
    r = client.post("/upload", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] == ["Léto.jpg"]
    assert len(body["errors"]) == 1
    assert (photos / "Léto.jpg").is_file()


def test_settings_form_saves(web):
    client, _, data = web
    form = {
        "interval_s": "3600", "order": "shuffle", "orientation": "portrait", "rotate_180": "on",
        "brightness": "1.1", "contrast": "1.2", "saturation": "0.9", "gamma": "1.0", "sleep_mode": "light",
    }
    r = client.post("/settings", data=form)
    assert r.status_code == 303 and r.headers["location"] == "/settings?saved=1"
    s = json.loads((data / "settings.json").read_text())
    assert s["orientation"] == "portrait" and s["rotate_180"] is True and s["contrast"] == 1.2


def test_settings_form_clamps_bad_input(web):
    client, _, data = web
    client.post("/settings", data={"interval_s": "", "brightness": "abc", "order": "x"})
    s = json.loads((data / "settings.json").read_text())
    assert s["interval_s"] == 3600
    assert s["brightness"] == 1.0
    assert s["rotate_180"] is False  # nezaškrtnutý checkbox
    assert s["palette"]["red"] == list(DEFAULT_PALETTE["red"])  # paleta se formulářem nemění


def test_settings_page_renders(web):
    client, *_ = web
    r = client.get("/settings?saved=1")
    assert r.status_code == 200 and "Uloženo" in r.text


def test_next_survives_slot_change(tmp_path):
    photos = tmp_path / "photos"
    data = tmp_path / "data"
    photos.mkdir()
    data.mkdir()
    (data / "settings.json").write_text(json.dumps({"interval_s": 600, "order": "name"}))
    now = {"t": 1000.0}
    client = TestClient(create_app(Config(photos, data, TOKEN), clock=lambda: now["t"]), follow_redirects=False)
    for n in ("a.png", "b.png", "c.png"):
        put(photos, n)
    client.post("/photo/a.png/next")
    now["t"] = 1700.0  # rámeček se probudí až v dalším slotu
    assert frame_photo(client, data) == "a.png"
    now["t"] = 1750.0  # ve stejném slotu zůstává
    assert frame_photo(client, data) == "a.png"


def test_gallery_all_hidden_explains(web):
    client, photos, data = web
    put(photos, "a.png")
    client.post("/photo/a.png/hide")
    page = client.get("/").text
    assert "Všechny fotky jsou vyřazené" in page
    assert "Rámeček zatím nic nezobrazil" not in page


def test_gallery_keeps_hidden_current_on_wall(web):
    client, photos, data = web
    put(photos, "a.png")
    put(photos, "b.png")
    frame_photo(client, data)
    current = json.loads((data / "state.json").read_text())["current_photo"]
    client.post(f"/photo/{current}/hide")
    page = client.get("/").text
    assert "Rámeček zatím nic nezobrazil" not in page
    assert "při příští změně zmizí" in page


def test_pinned_photo_is_marked(web):
    client, photos, _ = web
    put(photos, "a.png")
    put(photos, "b.png")
    r = client.post("/photo/b.png/next")
    assert r.headers["location"] == "/#p-b.png"
    page = client.get("/").text
    assert page.count("stamp--next") == 1


def test_settings_form_rejects_non_finite(web):
    client, _, data = web
    r = client.post("/settings", data={"interval_s": "inf", "brightness": "nan", "contrast": "-inf"})
    assert r.status_code == 303
    s = json.loads((data / "settings.json").read_text())
    assert s["interval_s"] == 3600 and s["brightness"] == 1.0 and s["contrast"] == 1.0


def test_cross_site_post_is_rejected(web):
    client, photos, data = web
    put(photos, "a.png")
    r = client.post("/photo/a.png/hide", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert not (data / "library.json").exists()
    assert client.post("/photo/a.png/hide", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 303


def test_source_png_and_tone_override(web):
    client, photos, _ = web
    put(photos, "a.png", color=(120, 120, 120))
    plain = client.get("/photo/a.png/source.png")
    assert plain.status_code == 200 and plain.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(plain.content)).size == (800, 480)
    toned = client.get("/photo/a.png/source.png?tone=1&brightness=2.0").content
    assert toned != plain.content


def test_stats_json(web):
    client, photos, _ = web
    put(photos, "a.png", color=DEFAULT_PALETTE["red"])
    stats = client.get("/photo/a.png/stats.json").json()
    assert abs(sum(stats.values()) - 100.0) < 0.01
    assert stats["red"] > 99


def test_save_tone_keeps_other_settings(web):
    client, _, data = web
    r = client.post("/settings/tone", json={"brightness": 1.3, "contrast": 1.1, "saturation": 0.9, "gamma": 1.0})
    assert r.status_code == 200 and r.json() == {"saved": True}
    s = json.loads((data / "settings.json").read_text())
    assert s["brightness"] == 1.3 and s["contrast"] == 1.1 and s["saturation"] == 0.9
    assert s["interval_s"] == 600 and s["order"] == "name"


def test_save_tone_rejects_bad_values(web):
    client, _, data = web
    client.post("/settings/tone", json={"brightness": "abc", "contrast": 99})
    s = json.loads((data / "settings.json").read_text())
    assert s["brightness"] == 1.0 and s["contrast"] == 3.0


def test_compare_page_with_neighbours(web):
    client, photos, _ = web
    for n in ("a.png", "b.png", "c.png"):
        put(photos, n)
    page = client.get("/photo/b.png/compare").text
    assert "/photo/b.png/source.png" in page and "/photo/b.png/preview.png" in page
    assert 'data-prev="/photo/a.png/compare"' in page
    assert 'data-next="/photo/c.png/compare"' in page
    first = client.get("/photo/a.png/compare").text
    assert 'data-prev="/photo/c.png/compare"' in first  # dokola


def test_gallery_links_to_compare(web):
    client, photos, _ = web
    put(photos, "a.png")
    assert "/photo/a.png/compare" in client.get("/").text


def test_guide_page(web):
    client, *_ = web
    page = client.get("/navod").text
    assert "KEY" in page and "BOOT" in page and "PWR" in page


def test_new_pages_denied_via_cloudflare(web):
    client, photos, _ = web
    put(photos, "a.png")
    cf = {"Cf-Connecting-Ip": "1.2.3.4"}
    for url in ("/navod", "/photo/a.png/compare", "/photo/a.png/source.png", "/photo/a.png/stats.json"):
        assert client.get(url, headers=cf).status_code == 404


def debug_env(tmp_path):
    photos = tmp_path / "photos"
    data = tmp_path / "data"
    photos.mkdir()
    data.mkdir()
    (data / "settings.json").write_text(json.dumps({"interval_s": 3600, "order": "name"}))
    now = {"t": 1000.0}
    client = TestClient(create_app(Config(photos, data, TOKEN), clock=lambda: now["t"]), follow_redirects=False)
    return client, photos, data, now


def sleep_header(client):
    return client.get("/api/v1/frame", headers={"Authorization": f"Bearer {TOKEN}"}).headers["X-Inka-Sleep-Seconds"]


def test_debug_mode_shortens_sleep_and_expires(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    put(photos, "a.png")
    assert sleep_header(client) == "300"  # ze sítě: nejvýš 5 min
    assert client.post("/debug", data={"on": "1", "next": "/"}).status_code == 303
    assert sleep_header(client) == "30"
    now["t"] += 3601  # po hodině se sám vypne
    assert sleep_header(client) != "30"


def test_debug_mode_off(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    put(photos, "a.png")
    client.post("/debug", data={"on": "1"})
    client.post("/debug", data={"on": "0"})
    assert sleep_header(client) != "30"


def test_show_now_pins_and_enables_debug(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    for n in ("a.png", "b.png", "c.png"):
        put(photos, n)
    r = client.post("/photo/c.png/show-now", data={"next": "/photo/c.png/compare"})
    assert r.status_code == 303 and r.headers["location"] == "/photo/c.png/compare"
    assert sleep_header(client) == "30"
    assert json.loads((data / "state.json").read_text())["current_photo"] == "c.png"


def test_debug_redirect_only_local(tmp_path):
    client, *_ = debug_env(tmp_path)
    assert client.post("/debug", data={"on": "1", "next": "https://evil.example/"}).headers["location"] == "/"
    assert client.post("/debug", data={"on": "1", "next": "//evil.example/"}).headers["location"] == "/"


def test_gallery_shows_debug_state(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    put(photos, "a.png")
    assert "Zapnout ladicí režim" in client.get("/").text
    client.post("/debug", data={"on": "1"})
    page = client.get("/").text
    assert "Ladicí režim do" in page and "Zobrazit hned" in page


def test_light_mode_caps_sleep_at_5_min(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    put(photos, "a.png")
    assert sleep_header(client) == "300"  # interval 1 h, režim ze sítě


def test_deep_mode_is_not_capped(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    (data / "settings.json").write_text(json.dumps({"interval_s": 3600, "order": "name", "sleep_mode": "deep"}))
    put(photos, "a.png")
    assert sleep_header(client) == "2630"


def test_gallery_shows_temperature_and_charging(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    put(photos, "a.png")
    client.get("/api/v1/frame?battery_pct=54&charging=1&temp_c=22.5", headers={"Authorization": f"Bearer {TOKEN}"})
    page = client.get("/").text
    assert "54&nbsp;%" in page and "nabíjí se" in page and "22,5&nbsp;°C" in page


def test_gallery_shows_power_source(tmp_path):
    client, photos, data, now = debug_env(tmp_path)
    put(photos, "a.png")
    client.get("/api/v1/frame?usb=1", headers={"Authorization": f"Bearer {TOKEN}"})
    assert "napájení z USB" in client.get("/").text
    client.get("/api/v1/frame?usb=0", headers={"Authorization": f"Bearer {TOKEN}"})
    assert "z baterie" in client.get("/").text


def test_settings_has_auto_power_option(web):
    client, *_ = web
    assert 'value="auto"' in client.get("/settings").text


def test_preview_dither_override_differs(web):
    client, photos, _ = web
    rng = __import__("numpy").random.default_rng(2)
    Image.fromarray(rng.integers(0, 256, (480, 800, 3), dtype="uint8")).save(photos / "n.png")
    fs = client.get("/photo/n.png/preview.png").content
    blue = client.get("/photo/n.png/preview.png?dither=blue-noise&grain=0.5").content
    assert fs != blue


def test_save_tone_saves_dither(web):
    client, _, data = web
    client.post("/settings/tone", json={"dither": "fs-grain", "dither_strength": 0.8, "grain": 0.3})
    s = json.loads((data / "settings.json").read_text())
    assert s["dither"] == "fs-grain" and s["dither_strength"] == 0.8 and s["grain"] == 0.3
    client.post("/settings/tone", json={"dither": "bogus"})
    assert json.loads((data / "settings.json").read_text())["dither"] == "fs"


def test_settings_form_keeps_and_sets_dither(web):
    client, _, data = web
    client.post("/settings/tone", json={"dither": "jjn", "grain": 0.2})
    client.post("/settings", data={"interval_s": "600", "order": "name"})  # starý formulář bez polí ditheringu
    s = json.loads((data / "settings.json").read_text())
    assert s["dither"] == "jjn" and s["grain"] == 0.2
    client.post("/settings", data={"interval_s": "600", "dither": "atkinson", "dither_strength": "0.7", "grain": "0.1"})
    s = json.loads((data / "settings.json").read_text())
    assert s["dither"] == "atkinson" and s["dither_strength"] == 0.7


def test_variants_page(web):
    from inka_server.dither import LABELS, METHODS

    client, photos, _ = web
    put(photos, "a.png")
    page = client.get("/photo/a.png/variants").text
    for m in METHODS:
        assert f"/photo/a.png/preview.png?dither={m}" in page
        assert LABELS[m] in page
    assert "/photo/a.png/source.png" in page
    assert client.get("/photo/a.png/compare").text.count('name="dither"') >= 1


def test_warmth_override_and_save(web):
    client, photos, data = web
    put(photos, "a.png", color=(128, 128, 128))
    assert client.get("/photo/a.png/source.png?tone=1&warmth=1").content != client.get("/photo/a.png/source.png?tone=1").content
    client.post("/settings/tone", json={"warmth": 0.4})
    assert json.loads((data / "settings.json").read_text())["warmth"] == 0.4
