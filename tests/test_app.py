from unittest import mock

import pytest

from autobiometrik import automation
from autobiometrik.app import create_app
from autobiometrik.config import Config


@pytest.fixture
def client():
    app = create_app(
        Config(username="u", password="p", finger_username="fu", finger_password="fp")
    )
    app.config.update(TESTING=True)
    return app.test_client()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["service"] == "autobiometrik-bpjs"
    assert body["has_credentials"] is True
    assert body["has_finger_credentials"] is True
    assert "autoit" in body


def test_run_exe_requires_no_peserta(client):
    resp = client.get("/run_exe")
    assert resp.status_code == 400
    assert resp.get_json()["status"] == "error"


def test_run_finger_requires_no_peserta(client):
    resp = client.get("/run_finger_exec")
    assert resp.status_code == 400


def test_run_exe_dispatches_launch_frista():
    with mock.patch.object(automation, "launch_frista") as m:
        # patch the reference imported into app as well
        import autobiometrik.app as appmod

        with mock.patch.object(appmod, "launch_frista", m):
            app = create_app(Config())
            client = app.test_client()
            resp = client.get("/run_exe?no_peserta=0001234567890")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["status"] == "running"
            assert body["no_peserta"] == "0001234567890"
    # background thread should have invoked the launcher
    m.assert_called()


def test_stop_endpoints(client):
    with mock.patch("autobiometrik.app.stop_process", return_value=True) as m:
        resp = client.get("/stop_exec")
        assert resp.status_code == 200
        assert resp.get_json()["was_running"] is True
        resp = client.get("/stop_finger_exec")
        assert resp.status_code == 200
    assert m.call_count == 2


def test_setup_logging_writes_to_file(tmp_path):
    import logging

    from autobiometrik.app import _setup_logging

    log_file = tmp_path / "autobiometrik.log"
    _setup_logging(log_file)
    logging.getLogger("dekate.autobiometrik").info("hello-tray-test")

    for h in logging.getLogger("dekate.autobiometrik").handlers:
        h.flush()
    assert log_file.exists()
    assert "hello-tray-test" in log_file.read_text(encoding="utf-8")


def test_automation_unavailable_off_windows():
    # When AutoItX is missing, the guard must raise a clean error, not crash.
    if automation.AUTOIT_AVAILABLE:
        pytest.skip("AutoItX is available on this machine")
    with pytest.raises(automation.AutomationUnavailable):
        automation.launch_frista("123", Config())
