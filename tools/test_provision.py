import csv
import io

import pytest

import provision

VALUES = {
    "INKA_WIFI_SSID": "Domov, 2.4 GHz",
    "INKA_WIFI_PASS": 'he"slo,ěšč=1',
    "INKA_SERVER_URL": "http://192.168.1.159:8100",
    "INKA_DEVICE_TOKEN": "abc",
}


def test_parse_env_keeps_values_verbatim():
    text = "# komentář\n\nINKA_WIFI_PASS=a=b c\nINKA_WIFI_SSID= x \n"
    assert provision.parse_env(text) == {"INKA_WIFI_PASS": "a=b c", "INKA_WIFI_SSID": " x "}


def test_csv_roundtrip_special_chars():
    rows = list(csv.reader(io.StringIO(provision.build_csv(VALUES))))
    assert rows[0] == ["key", "type", "encoding", "value"]
    assert rows[1] == ["inka", "namespace", "", ""]
    data = {r[0]: r[3] for r in rows[2:]}
    assert data == {
        "wifi_ssid": VALUES["INKA_WIFI_SSID"],
        "wifi_pass": VALUES["INKA_WIFI_PASS"],
        "server_url": VALUES["INKA_SERVER_URL"],
        "device_token": VALUES["INKA_DEVICE_TOKEN"],
    }
    assert all(r[1:3] == ["data", "string"] for r in rows[2:])


def test_missing_value_is_error():
    values = dict(VALUES, INKA_WIFI_PASS="")
    with pytest.raises(ValueError, match="INKA_WIFI_PASS"):
        provision.build_csv(values)


def rows_of(values):
    return {r[0]: r[3] for r in list(csv.reader(io.StringIO(provision.build_csv(values))))[2:]}


def test_server_url_trailing_slash_and_space_are_removed():
    data = rows_of(dict(VALUES, INKA_SERVER_URL="https://inka.example.com/ ", INKA_DEVICE_TOKEN="abc \n"))
    assert data["server_url"] == "https://inka.example.com"
    assert data["device_token"] == "abc"


def test_wifi_password_whitespace_is_kept():
    assert rows_of(dict(VALUES, INKA_WIFI_PASS=" pass "))["wifi_pass"] == " pass "


@pytest.mark.parametrize(
    "key,value",
    [
        ("INKA_WIFI_SSID", "s" * 33),
        ("INKA_WIFI_PASS", "ě" * 33),  # 66 bajtů v UTF-8
        ("INKA_SERVER_URL", "http://" + "a" * 121),
        ("INKA_DEVICE_TOKEN", "t" * 65),
    ],
)
def test_too_long_values_are_rejected(key, value):
    with pytest.raises(ValueError, match=key):
        provision.build_csv(dict(VALUES, **{key: value}))


def test_server_url_must_be_http():
    with pytest.raises(ValueError, match="INKA_SERVER_URL"):
        provision.build_csv(dict(VALUES, INKA_SERVER_URL="192.168.1.159:8100"))
