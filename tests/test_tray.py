from unittest import mock

import pytest

from autobiometrik import tray
from autobiometrik.config import Config


def test_load_icon_image_returns_pil_image():
    img = tray.load_icon_image()
    assert img.size[0] > 0 and img.size[1] > 0


def test_open_health_opens_scheme_host_port():
    cfg = Config(host="127.0.0.1", port=5000)
    with mock.patch("autobiometrik.tray.webbrowser.open") as m:
        tray.open_health(cfg)
    m.assert_called_once_with("http://127.0.0.1:5000/health")


def test_open_health_uses_https_when_tls():
    cfg = Config(host="0.0.0.0", port=8443, tls_cert="c.pem", tls_key="k.pem")
    with mock.patch("autobiometrik.tray.webbrowser.open") as m:
        tray.open_health(cfg)
    m.assert_called_once_with("https://0.0.0.0:8443/health")


def test_probe_health_true_when_port_accepts():
    cfg = Config(host="127.0.0.1", port=5000)
    with mock.patch("autobiometrik.tray.socket.create_connection", return_value=mock.MagicMock()):
        assert tray.probe_health(cfg) is True


def test_probe_health_false_on_refused():
    cfg = Config()
    with mock.patch(
        "autobiometrik.tray.socket.create_connection", side_effect=OSError("refused")
    ):
        assert tray.probe_health(cfg) is False


def test_status_text_running():
    cfg = Config()
    with mock.patch("autobiometrik.tray.probe_health", return_value=True):
        assert "Running" in tray.status_text(cfg)


def test_status_text_not_running():
    cfg = Config()
    with mock.patch("autobiometrik.tray.probe_health", return_value=False):
        assert "Not responding" in tray.status_text(cfg)


def test_open_config_opens_source_path_in_editor():
    cfg = Config(source_path="C:/x/config.json")
    with mock.patch("autobiometrik.tray.sys.platform", "win32"), mock.patch(
        "autobiometrik.tray.subprocess.Popen"
    ) as m:
        tray.open_config(cfg)
    m.assert_called_once_with(["notepad.exe", "C:/x/config.json"])


def test_open_config_noop_without_source_path():
    cfg = Config(source_path=None)
    with mock.patch("autobiometrik.tray.subprocess.Popen") as m:
        tray.open_config(cfg)
    m.assert_not_called()


def test_open_logs_opens_in_editor():
    with mock.patch("autobiometrik.tray.sys.platform", "win32"), mock.patch(
        "autobiometrik.tray.subprocess.Popen"
    ) as m:
        tray.open_logs("C:/x/autobiometrik.log")
    m.assert_called_once_with(["notepad.exe", "C:/x/autobiometrik.log"])


def test_do_reload_calls_reload_config():
    cfg = Config()
    with mock.patch("autobiometrik.tray.reload_config") as m:
        tray.do_reload(cfg)
    m.assert_called_once_with(cfg)


def test_do_reload_notifies_icon_when_given():
    cfg = Config()
    icon = mock.MagicMock()
    with mock.patch("autobiometrik.tray.reload_config"):
        tray.do_reload(cfg, icon)
    icon.notify.assert_called_once()


def test_build_menu_has_config_actions():
    cfg = Config(source_path="c.json")
    with mock.patch("autobiometrik.tray.probe_health", return_value=True):
        menu = tray.build_menu(cfg, "1.0.0", "log.txt", lambda icon, item: None)
        texts = [item.text for item in menu.items]
    assert "Open config" in texts
    assert "Reload config" in texts


def test_build_menu_has_expected_items():
    cfg = Config(username="u", password="p")
    quit_called = []
    with mock.patch("autobiometrik.tray.probe_health", return_value=True):
        menu = tray.build_menu(
            cfg, "1.0.0", "C:/x/autobiometrik.log", lambda icon, item: quit_called.append(True)
        )
        texts = [item.text for item in menu.items]
    # info line with version, live status line, URL line, capability line, actions
    assert any("1.0.0" in t for t in texts)
    assert any("Running" in t for t in texts)
    assert any("127.0.0.1:5000" in t for t in texts)
    assert "Open health page" in texts
    assert "Open logs" in texts
    assert "Quit" in texts


def test_build_menu_info_lines_are_disabled():
    cfg = Config()
    with mock.patch("autobiometrik.tray.probe_health", return_value=True):
        menu = tray.build_menu(cfg, "1.0.0", "log.txt", lambda icon, item: None)
        by_text = {item.text: item for item in menu.items}
        version_line = next(item for item in menu.items if "1.0.0" in item.text)
        status_line = next(item for item in menu.items if "Running" in item.text)
    assert version_line.enabled is False
    assert status_line.enabled is False
    assert by_text["Quit"].enabled is True
