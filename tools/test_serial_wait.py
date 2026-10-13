import io
from types import SimpleNamespace

import serial_wait


def port(device, vid):
    return SimpleNamespace(device=device, vid=vid)


def test_find_port_picks_espressif_vid():
    ports = [port("/dev/cu.Bluetooth", None), port("/dev/cu.usbmodem2101", 0x303A)]
    assert serial_wait.find_port(ports) == "/dev/cu.usbmodem2101"


def test_find_port_none_when_missing():
    assert serial_wait.find_port([port("/dev/cu.debug-console", None)]) is None


def test_wait_for_finds_pattern_and_echoes():
    lines = [b"I (10) inka: boot\r\n", b"I (25000) inka: refresh done in 24871 ms\r\n"]
    out = io.StringIO()
    assert serial_wait.wait_for(iter(lines), "inka: refresh done", out) is True
    assert "boot" in out.getvalue()


def test_wait_for_returns_false_when_stream_ends():
    out = io.StringIO()
    assert not serial_wait.wait_for(iter([b"I (10) inka: boot\r\n"]), "refresh done", out)


def test_wait_for_survives_invalid_utf8():
    out = io.StringIO()
    lines = [b"\xff\xfe garbage\r\n", b"inka: refresh done\r\n"]
    assert serial_wait.wait_for(iter(lines), "refresh done", out) is True


def test_wait_for_stops_on_fail_pattern():
    out = io.StringIO()
    lines = [b"inka: display failed: ESP_ERR_TIMEOUT\r\n", b"inka: refresh done\r\n"]
    assert serial_wait.wait_for(iter(lines), "refresh done", out, fail_patterns=["display failed"]) is False


def test_wait_for_none_when_stream_ends():
    out = io.StringIO()
    assert serial_wait.wait_for(iter([b"boot\r\n"]), "refresh done", out, fail_patterns=["x"]) is None
