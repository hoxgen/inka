import json

from inka_server.settings import (
    DEFAULT_PALETTE,
    Settings,
    load_settings,
    save_settings,
    settings_from_dict,
)
from inka_server.state import DeviceState, load_state, save_state


def test_defaults_when_missing(tmp_path):
    s = load_settings(tmp_path)
    assert s == Settings()
    assert s.rotate_180 is True
    assert set(s.palette) == {"black", "white", "yellow", "red", "blue", "green"}


def test_roundtrip(tmp_path):
    s = Settings(interval_s=600, order="name", contrast=1.2)
    save_settings(tmp_path, s)
    assert load_settings(tmp_path) == s


def test_invalid_values_fall_back():
    s = settings_from_dict(
        {
            "interval_s": 0,
            "order": "random",
            "orientation": "diagonal",
            "rotate_180": "yes",
            "contrast": 99,
            "brightness": "x",
            "sleep_mode": "hibernate",
            "palette": {"red": [300, 0, 0], "blue": [1, 2]},
            "unknown": 1,
        }
    )
    assert s.interval_s == 60
    assert s.order == "shuffle"
    assert s.orientation == "landscape"
    assert s.rotate_180 is True
    assert s.contrast == 3.0
    assert s.brightness == 1.0
    assert s.sleep_mode == "auto"
    assert s.palette["red"] == DEFAULT_PALETTE["red"]
    assert s.palette["blue"] == DEFAULT_PALETTE["blue"]


def test_corrupt_json_gives_defaults(tmp_path):
    (tmp_path / "settings.json").write_text("{not json")
    assert load_settings(tmp_path) == Settings()


def test_render_hash_ignores_schedule_fields():
    a = Settings(interval_s=60, order="name", sleep_mode="deep")
    b = Settings()
    assert a.render_hash() == b.render_hash()
    assert Settings(contrast=1.1).render_hash() != b.render_hash()


def test_settings_file_is_plain_json(tmp_path):
    save_settings(tmp_path, Settings(interval_s=900))
    data = json.loads((tmp_path / "settings.json").read_text())
    assert data["interval_s"] == 900
    assert data["palette"]["white"] == list(DEFAULT_PALETTE["white"])


def test_state_roundtrip(tmp_path):
    assert load_state(tmp_path) == DeviceState()
    st = DeviceState(offset=2, battery_mv=3800, fw="v1", wake="timer", current_photo="a.jpg")
    save_state(tmp_path, st)
    assert load_state(tmp_path) == st


def test_non_finite_numbers_fall_back():
    s = settings_from_dict({"interval_s": float("nan"), "brightness": float("inf"), "contrast": float("nan")})
    assert s.interval_s == 3600
    assert s.brightness == 1.0
    assert s.contrast == 1.0


def test_nan_in_settings_file_gives_defaults(tmp_path):
    (tmp_path / "settings.json").write_text('{"interval_s": NaN, "gamma": Infinity}')
    s = load_settings(tmp_path)
    assert s.interval_s == 3600
    assert s.gamma == 1.0


def test_state_with_non_utf8_file_name_is_saved(tmp_path):
    # Na Linuxu Python převede neplatné UTF-8 v názvu souboru na surrogate escape.
    name = b"foto-\xe8esk\xe9.png".decode("utf-8", "surrogateescape")
    save_state(tmp_path, DeviceState(current_photo=name))
    assert load_state(tmp_path).current_photo is not None


def test_dither_settings_validate():
    s = settings_from_dict({"dither": "magic", "dither_strength": 5, "grain": -1})
    assert s.dither == "fs" and s.dither_strength == 1.0 and s.grain == 0.0
    s = settings_from_dict({"dither": "blue-noise", "dither_strength": 0.6, "grain": 0.25})
    assert s.dither == "blue-noise" and s.dither_strength == 0.6 and s.grain == 0.25


def test_render_hash_includes_dither():
    assert Settings(dither="jjn").render_hash() != Settings().render_hash()
    assert Settings(grain=0.9).render_hash() != Settings().render_hash()


def test_warmth_validates_and_affects_render_hash():
    assert settings_from_dict({"warmth": 5}).warmth == 1.0
    assert settings_from_dict({"warmth": -5}).warmth == -1.0
    assert settings_from_dict({"warmth": "x"}).warmth == 0.0
    assert Settings(warmth=0.3).render_hash() != Settings().render_hash()
