import json

from dekate_autobiometrik.config import (
    DEFAULT_FINGER_PATH,
    DEFAULT_FRISTA_PATH,
    load_config,
)


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.frista_path == DEFAULT_FRISTA_PATH
    assert cfg.finger_path == DEFAULT_FINGER_PATH
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 5000
    assert cfg.has_credentials is False


def test_modern_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "frista_path": "C:/x/frista.exe",
                "finger_path": "C:/y/After.exe",
                "username": "u",
                "password": "p",
                "port": 6001,
            }
        )
    )
    cfg = load_config(path)
    assert cfg.frista_path == "C:/x/frista.exe"
    assert cfg.finger_path == "C:/y/After.exe"
    assert cfg.username == "u"
    assert cfg.password == "p"
    assert cfg.port == 6001
    assert cfg.has_credentials is True


def test_legacy_path_keys_are_accepted(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"path": "C:/legacy/frista.exe", "pathfinger": "C:/legacy/After.exe"})
    )
    cfg = load_config(path)
    assert cfg.frista_path == "C:/legacy/frista.exe"
    assert cfg.finger_path == "C:/legacy/After.exe"


def test_malformed_json_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ not valid json ")
    cfg = load_config(path)
    assert cfg.frista_path == DEFAULT_FRISTA_PATH


def test_invalid_port_is_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"port": "not-a-number"}))
    cfg = load_config(path)
    assert cfg.port == 5000
