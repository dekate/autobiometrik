from unittest import mock

import pytest

from dekate_autobiometrik import automation
from dekate_autobiometrik.app import create_app
from dekate_autobiometrik.config import Config


@pytest.fixture
def client():
    app = create_app(Config(username="u", password="p"))
    app.config.update(TESTING=True)
    return app.test_client()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["service"] == "dekate-autobiometrik"
    assert body["has_credentials"] is True
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
        import dekate_autobiometrik.app as appmod

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
    with mock.patch("dekate_autobiometrik.app.stop_process", return_value=True) as m:
        resp = client.get("/stop_exec")
        assert resp.status_code == 200
        assert resp.get_json()["was_running"] is True
        resp = client.get("/stop_finger_exec")
        assert resp.status_code == 200
    assert m.call_count == 2


def test_automation_unavailable_off_windows():
    # When AutoItX is missing, the guard must raise a clean error, not crash.
    if automation.AUTOIT_AVAILABLE:
        pytest.skip("AutoItX is available on this machine")
    with pytest.raises(automation.AutomationUnavailable):
        automation.launch_frista("123", Config())
