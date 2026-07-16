"""Branch tests for the launchers: does it launch and log in, or reuse?

The real AutoItX is never called here — `autoit` is replaced with a mock that
records every call, so these run on any platform.
"""

import pytest
from unittest import mock

from autobiometrik import automation
from autobiometrik.config import Config


@pytest.fixture
def cfg():
    return Config(
        frista_username="u",
        frista_password="p",
        finger_username="fu",
        finger_password="fp",
    )


@pytest.fixture
def fake_autoit(monkeypatch):
    """Stand in for the AutoItX binding, recording calls in order."""
    fake = mock.MagicMock()
    fake.win_exists.return_value = 0      # nothing running by default
    fake.win_wait.return_value = 1        # windows appear promptly
    fake.win_wait_active.return_value = 1
    monkeypatch.setattr(automation, "autoit", fake)
    monkeypatch.setattr(automation, "AUTOIT_AVAILABLE", True)
    # Real sleeps would add ~2.2s per test for no benefit.
    monkeypatch.setattr(automation.time, "sleep", lambda _s: None)
    # BlockInput would freeze the developer's keyboard mid-test.
    monkeypatch.setattr(automation, "_set_block_input", lambda _b: None)
    return fake


def sent(fake):
    """The first positional arg of every autoit.send call, in order."""
    return [call.args[0] for call in fake.send.call_args_list]


def test_finger_reuses_running_window_without_retyping_credentials(fake_autoit, cfg):
    fake_autoit.win_exists.return_value = 1  # app already up == already logged in

    automation.launch_finger("0001234567890", cfg)

    fake_autoit.run.assert_not_called()
    keys = sent(fake_autoit)
    assert "fu" not in keys, "username must never be typed into a logged-in app"
    assert "fp" not in keys
    assert "0001234567890" in keys


def test_finger_launches_and_logs_in_when_not_running(fake_autoit, cfg):
    fake_autoit.win_exists.return_value = 0

    automation.launch_finger("0001234567890", cfg)

    fake_autoit.run.assert_called_once_with(cfg.finger_path)
    assert sent(fake_autoit) == [
        "fu", "{TAB}", "fp", "{ENTER}",
        "0001234567890", "{TAB}", "{SPACE}",
    ]


def test_finger_confirms_focus_before_sending_keys(fake_autoit, cfg):
    fake_autoit.win_exists.return_value = 1
    fake_autoit.win_wait_active.return_value = 0  # focus never lands

    with pytest.raises(TimeoutError):
        automation.launch_finger("0001234567890", cfg)

    fake_autoit.send.assert_not_called()


def test_finger_fresh_without_credentials_does_not_send_the_number(fake_autoit):
    fake_autoit.win_exists.return_value = 0

    automation.launch_finger("0001234567890", Config())

    # The app is sitting at its login screen; the number would land in the
    # username field.
    assert "0001234567890" not in sent(fake_autoit)


def test_finger_raises_when_window_never_appears(fake_autoit, cfg):
    fake_autoit.win_exists.return_value = 0
    fake_autoit.win_wait.return_value = 0

    with pytest.raises(TimeoutError):
        automation.launch_finger("0001234567890", cfg)


def only_main_open(fake):
    """FRISTA is logged in: the main window matches, the login window does not.

    The two selectors are unambiguous — only the main one is a REGEXPTITLE,
    and only the login one contains "Login Frista".
    """
    fake.win_exists.side_effect = lambda sel, *a: 1 if "REGEXPTITLE" in sel else 0


def only_login_open(fake):
    """FRISTA is running but still sitting at its login screen."""
    fake.win_exists.side_effect = lambda sel, *a: 1 if "Login Frista" in sel else 0


def test_frista_already_logged_in_skips_launch_and_login(fake_autoit, cfg):
    only_main_open(fake_autoit)

    automation.launch_frista("0001234567890", cfg)

    fake_autoit.run.assert_not_called()
    assert "u" not in sent(fake_autoit), "credentials must not be retyped"
    assert "p" not in sent(fake_autoit)


def test_frista_at_login_screen_logs_in_without_relaunching(fake_autoit, cfg):
    only_login_open(fake_autoit)

    automation.launch_frista("0001234567890", cfg)

    fake_autoit.run.assert_not_called()
    assert sent(fake_autoit) == [
        "u", "{TAB}", "p", "{TAB}", "{SPACE}",
        "{END}", "+{HOME}", "0001234567890",
    ]


def test_frista_launches_when_not_running(fake_autoit, cfg):
    fake_autoit.win_exists.return_value = 0

    automation.launch_frista("0001234567890", cfg)

    fake_autoit.run.assert_called_once_with(cfg.frista_path)


def test_frista_types_the_number_into_the_nik_field(fake_autoit, cfg):
    only_main_open(fake_autoit)

    automation.launch_frista("0001234567890", cfg)

    focused = fake_autoit.control_focus.call_args_list[-1]
    assert focused.args[1] == automation.FRISTA_UI.nik_ctrl
    assert sent(fake_autoit) == ["{END}", "+{HOME}", "0001234567890"]


def test_frista_never_presses_ambil_foto(fake_autoit, cfg):
    only_main_open(fake_autoit)

    automation.launch_frista("0001234567890", cfg)

    # The operator presses it once the face is framed; firing it here would
    # capture a bad frame.
    fake_autoit.control_click.assert_not_called()
    assert "{ENTER}" not in sent(fake_autoit)


def test_frista_without_credentials_does_not_send_the_number(fake_autoit):
    fake_autoit.win_exists.return_value = 0

    automation.launch_frista("0001234567890", Config())

    assert "0001234567890" not in sent(fake_autoit)


def test_frista_raises_when_login_window_never_appears(fake_autoit, cfg):
    fake_autoit.win_exists.return_value = 0
    fake_autoit.win_wait.return_value = 0

    with pytest.raises(TimeoutError):
        automation.launch_frista("0001234567890", cfg)


def test_frista_raises_when_main_window_never_appears(fake_autoit, cfg):
    fake_autoit.win_exists.return_value = 0
    # The login window shows up, but the main window never follows.
    fake_autoit.win_wait.side_effect = lambda sel, *a: 0 if "REGEXPTITLE" in sel else 1

    with pytest.raises(TimeoutError):
        automation.launch_frista("0001234567890", cfg)
