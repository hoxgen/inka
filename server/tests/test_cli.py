import pytest

from inka_server.cli import config_from_env


def test_config_from_env(tmp_path):
    cfg = config_from_env(
        {"PHOTOS_DIR": str(tmp_path / "p"), "DATA_DIR": str(tmp_path / "d"), "INKA_DEVICE_TOKEN": "x"}
    )
    assert cfg.photos_dir == tmp_path / "p"
    assert cfg.device_token == "x"


def test_missing_token_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        config_from_env({"PHOTOS_DIR": "a", "DATA_DIR": "b"})
    assert "INKA_DEVICE_TOKEN" in str(exc.value)
