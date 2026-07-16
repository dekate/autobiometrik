"""Desktop automation for the BPJS FRISTA and fingerprint apps.

This drives two Windows desktop programs through AutoIt (PyAutoIt / AutoItX):

* **FRISTA** (face recognition) — launched, then the login window is filled with
  the operator's credentials from ``config.json`` and submitted.
* **Fingerprint** ("After.exe") — launched, logged in with its own credentials
  (``finger_username`` / ``finger_password`` — a separate account from FRISTA),
  then the patient's BPJS number is typed into the registration window.

The window titles and control ids below target the BPJS apps as shipped at the
time of writing (FRISTA 3.0.x). If BPJS updates those apps and the controls move,
adjust :data:`FRISTA_UI` / :data:`FINGER_UI` — that is the one place that needs
touching, no rebuild logic elsewhere depends on them.

AutoItX is Windows-only. On any other platform (or if the ``autoit`` package is
missing) the module still imports; the automation calls then raise
:class:`AutomationUnavailable` so the HTTP layer can return a clean error instead
of crashing.
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass

from .config import Config

log = logging.getLogger("dekate.autobiometrik")

# --- Optional AutoIt binding -------------------------------------------------
try:  # pragma: no cover - availability depends on the host OS
    import autoit  # type: ignore

    AUTOIT_AVAILABLE = True
except Exception as exc:  # noqa: BLE001 - any import failure means "unavailable"
    autoit = None  # type: ignore
    AUTOIT_AVAILABLE = False
    _IMPORT_ERROR = exc


class AutomationUnavailable(RuntimeError):
    """Raised when AutoItX is not usable on this machine."""


# --- UI targets (BPJS app specific) ------------------------------------------
@dataclass(frozen=True)
class FristaUi:
    login_title: str = "Login Frista (Face Recognition BPJS Kesehatan)"
    main_title: str = "Frista (Face Recognition BPJS Kesehatan) 3.0.2"
    username_ctrl: str = "TkChild3"
    password_ctrl: str = "TkChild4"
    login_button: str = "Button1"
    main_ctrl: str = "TkChild2"


@dataclass(frozen=True)
class FingerUi:
    # The login and registration screens share this window title; the login
    # form is what appears first after launch, with the username field focused.
    # The app is WPF (window class "HwndWrapper[After.exe;;<guid>]"), so its
    # fields are not Win32 controls — control_send/control_click can't target
    # them and everything must go through focus + keyboard sends. Match the
    # window by title only: the guid in the class changes between builds.
    title: str = "Aplikasi Registrasi Sidik Jari"
    # Seconds to let the app process the login before the registration form
    # is ready to receive the BPJS number.
    login_settle: float = 2.0


FRISTA_UI = FristaUi()
FINGER_UI = FingerUi()

# How long to wait for a window to appear before giving up (seconds).
WINDOW_TIMEOUT = 30
# How long to wait for an existing window to take focus (seconds). Shorter than
# WINDOW_TIMEOUT: the window is already up, only focus has to land.
ACTIVATE_TIMEOUT = 5


def _require_autoit() -> None:
    if not AUTOIT_AVAILABLE:
        raise AutomationUnavailable(
            "AutoItX is not available on this machine "
            f"({_IMPORT_ERROR!r}). Install on Windows with: pip install PyAutoIt"
        )


def _win_exists(selector: str) -> bool:
    """Whether a window matching ``selector`` is currently open.

    This is the login probe. Both BPJS apps show their login screen on every
    fresh launch, so a window that exists is one somebody already logged in.
    Asking the live desktop each time (rather than remembering what we
    launched) keeps us right when an operator opens or closes an app by hand.
    """
    return bool(autoit.win_exists(selector))


def _focus(selector: str) -> None:
    """Bring a window to the front and confirm it has focus.

    Keystrokes go wherever focus happens to be, so never send without this.
    """
    autoit.win_activate(selector)
    if not autoit.win_wait_active(selector, ACTIVATE_TIMEOUT):
        raise TimeoutError(f"window did not take focus: {selector!r}")


def _set_block_input(block: bool) -> None:
    """Freeze/unfreeze physical keyboard & mouse during automation (Windows).

    Prevents an operator's stray keypress from landing in the middle of the
    scripted login. Best effort — silently ignored off Windows.
    """
    try:  # pragma: no cover - Windows only
        import ctypes

        ctypes.windll.user32.BlockInput(bool(block))
    except Exception:  # noqa: BLE001
        pass


def launch_frista(no_peserta: str, cfg: Config) -> None:
    """Launch FRISTA and log in, then hand the app the BPJS number.

    Raises :class:`AutomationUnavailable` if AutoItX is missing, or
    :class:`TimeoutError` if a window never appears.
    """
    _require_autoit()
    ui = FRISTA_UI

    log.info("launching FRISTA for no_peserta=%s", no_peserta)
    autoit.run(cfg.frista_path)

    login = f"[TITLE:{ui.login_title}]"
    if not autoit.win_wait(login, WINDOW_TIMEOUT):
        raise TimeoutError(f"FRISTA login window did not appear: {ui.login_title!r}")

    autoit.win_activate(login)
    _set_block_input(True)
    try:
        if cfg.has_credentials:
            # FRISTA's login controls don't respond reliably to per-control
            # sends: a send aimed at the password control leaks back into the
            # username field, so both values end up concatenated in Username.
            # Drive it by keyboard instead — focus the username field, TAB to
            # the password field, then TAB to the Login button and press it
            # with SPACE. The form does not submit on ENTER, and the button is
            # a custom control that control_click can't hit, so keyboard
            # activation is the reliable path. Raw mode (1) keeps password
            # symbols from being read as AutoIt key macros.
            autoit.control_focus(login, ui.username_ctrl)
            autoit.send(cfg.frista_username, 1)
            autoit.send("{TAB}")
            autoit.send(cfg.frista_password, 1)
            autoit.send("{TAB}")
            autoit.send("{SPACE}")
        else:
            log.warning("no FRISTA credentials configured; leaving login blank")
    finally:
        _set_block_input(False)

    # Wait for the main window so the operator sees the app is ready.
    main = f"[TITLE:{ui.main_title}]"
    if not autoit.win_wait(main, WINDOW_TIMEOUT):
        log.warning("FRISTA main window not detected within timeout")

    log.info("FRISTA ready for no_peserta=%s", no_peserta)


def launch_finger(no_peserta: str, cfg: Config) -> None:
    """Send the BPJS number to the fingerprint app, launching it if needed.

    A fresh instance always opens at its login screen, so an existing window
    means the app is already logged in and only needs the number. Both apps
    allow multiple instances: relaunching blindly would spawn a duplicate and
    type the username into the registration field.
    """
    _require_autoit()
    ui = FINGER_UI
    window = f"[TITLE:{ui.title}]"

    fresh = not _win_exists(window)
    if fresh:
        log.info("fingerprint app not running; launching for no_peserta=%s", no_peserta)
        autoit.run(cfg.finger_path)
        if not autoit.win_wait(window, WINDOW_TIMEOUT):
            raise TimeoutError(f"Fingerprint window did not appear: {ui.title!r}")
    else:
        log.info(
            "fingerprint app already running; reusing window for no_peserta=%s",
            no_peserta,
        )

    _focus(window)
    autoit.win_set_on_top(window, "", 1)
    _set_block_input(True)
    try:
        if fresh:
            if not cfg.has_finger_credentials:
                log.warning(
                    "fingerprint app is at the login screen and no credentials "
                    "are configured; not sending the number (it would land in "
                    "the username field)"
                )
                return
            # Login form, username field focused. Raw mode (1) so symbols in
            # the password aren't interpreted as AutoIt key macros.
            autoit.send(cfg.finger_username, 1)
            autoit.send("{TAB}")
            autoit.send(cfg.finger_password, 1)
            autoit.send("{ENTER}")
            time.sleep(ui.login_settle)
        # The registration field clears itself after each entry, so the number
        # can go straight in. Then advance with TAB/SPACE as the app expects.
        autoit.send(str(no_peserta))
        time.sleep(0.2)
        autoit.send("{TAB}")
        autoit.send("{SPACE}")
    finally:
        _set_block_input(False)

    log.info("fingerprint number sent for no_peserta=%s", no_peserta)


def stop_process(exe_name: str) -> bool:
    """Terminate a running process by image name. Returns True if it was running.

    Uses ``taskkill`` on Windows and ``pkill`` elsewhere; never raises for a
    process that simply is not running.
    """
    import os

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/F", "/IM", exe_name],
                capture_output=True,
                text=True,
                check=False,
            )
            running = result.returncode == 0
        else:
            result = subprocess.run(
                ["pkill", "-f", exe_name],
                capture_output=True,
                text=True,
                check=False,
            )
            running = result.returncode == 0
    except OSError as exc:
        log.error("failed to stop %s: %s", exe_name, exc)
        return False

    if running:
        log.info("terminated process: %s", exe_name)
    else:
        log.info("process not running: %s", exe_name)
    return running
