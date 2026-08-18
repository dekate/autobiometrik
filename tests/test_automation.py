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
    """Stand in for the AutoItX binding, recording calls in order.

    Specced against the real module wherever it is installed, so a call with
    the wrong arity fails here rather than at the kiosk. A bare MagicMock
    swallows any signature, which is how ``win_set_on_top(title, "", 1)`` — an
    argument list PyAutoIt has not accepted for years — reached production
    green. Off Windows the module is missing and the spec is skipped; the
    signature check then happens on the developer machine that has AutoItX.
    """
    try:
        import autoit as real_autoit

        fake = mock.create_autospec(real_autoit)
    except Exception:  # noqa: BLE001 - not on Windows / AutoItX not installed
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


# The title bar text of a running BPJS fingerprint app (After.exe), read off
# the real thing. Both its login screen and its registration screen carry it.
# Pinned here because every other test stubs win_exists with a constant, which
# would happily pass with a selector that matches no real window at all.
REAL_FINGER_TITLE = "Aplikasi Verifikasi dan Registrasi Sidik Jari"


def desktop(fake, *titles):
    """Answer win_exists/win_wait against a desktop of real window titles.

    AutoIt's default WinTitleMatchMode is "start with", so a ``[TITLE:x]``
    selector matches any window whose title begins with ``x``.
    """

    def matches(selector, *_a):
        prefix = selector[len("[TITLE:"):-1] if selector.startswith("[TITLE:") else selector
        return int(any(title.startswith(prefix) for title in titles))

    fake.win_exists.side_effect = matches
    fake.win_wait.side_effect = matches


def test_finger_selector_matches_the_real_window_title(fake_autoit, cfg):
    """A running app must be recognised, or every request opens another copy."""
    desktop(fake_autoit, REAL_FINGER_TITLE)

    automation.launch_finger("0001234567890", cfg)

    fake_autoit.run.assert_not_called()
    assert "0001234567890" in sent(fake_autoit)


def test_finger_waits_for_the_real_window_title_after_launching(fake_autoit, cfg):
    """Nothing is running; the launched app must satisfy the wait, not time out."""
    desktop(fake_autoit)  # empty desktop
    fake_autoit.run.side_effect = lambda *_a: desktop(fake_autoit, REAL_FINGER_TITLE)

    automation.launch_finger("0001234567890", cfg)

    fake_autoit.run.assert_called_once_with(cfg.finger_path)
    assert "0001234567890" in sent(fake_autoit)


def test_finger_never_pins_the_window_on_top(fake_autoit, cfg):
    """WS_EX_TOPMOST is a permanent style, not a one-shot raise.

    Setting it left the app floating over the browser until it was restarted;
    activating the window is enough for the keystrokes to land.
    """
    desktop(fake_autoit, REAL_FINGER_TITLE)

    automation.launch_finger("0001234567890", cfg)

    fake_autoit.win_set_on_top.assert_not_called()
    fake_autoit.win_activate.assert_called()


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
