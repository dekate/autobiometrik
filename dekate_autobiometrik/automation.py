"""Desktop automation for the BPJS FRISTA and fingerprint apps.

This drives two Windows desktop programs through AutoIt (PyAutoIt / AutoItX):

* **FRISTA** (face recognition) — launched, then the login window is filled with
  the operator's credentials from ``config.json`` and submitted.
* **Fingerprint** ("After.exe") — launched, then the patient's BPJS number is
  typed into the registration window.

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
    title: str = "Aplikasi Registrasi Sidik Jari"


FRISTA_UI = FristaUi()
FINGER_UI = FingerUi()

# How long to wait for a window to appear before giving up (seconds).
WINDOW_TIMEOUT = 30


def _require_autoit() -> None:
    if not AUTOIT_AVAILABLE:
        raise AutomationUnavailable(
            "AutoItX is not available on this machine "
            f"({_IMPORT_ERROR!r}). Install on Windows with: pip install PyAutoIt"
        )


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
            autoit.control_focus(login, ui.username_ctrl)
            autoit.control_send(login, ui.username_ctrl, cfg.username)
            autoit.control_focus(login, ui.password_ctrl)
            autoit.control_send(login, ui.password_ctrl, cfg.password)
        else:
            log.warning("no FRISTA credentials configured; leaving login blank")
        autoit.control_click(login, ui.login_button)
    finally:
        _set_block_input(False)

    # Wait for the main window so the operator sees the app is ready.
    main = f"[TITLE:{ui.main_title}]"
    if not autoit.win_wait(main, WINDOW_TIMEOUT):
        log.warning("FRISTA main window not detected within timeout")

    log.info("FRISTA ready for no_peserta=%s", no_peserta)


def launch_finger(no_peserta: str, cfg: Config) -> None:
    """Launch the fingerprint app and type the BPJS number into it."""
    _require_autoit()
    ui = FINGER_UI

    log.info("launching fingerprint app for no_peserta=%s", no_peserta)
    autoit.run(cfg.finger_path)

    window = f"[TITLE:{ui.title}]"
    if not autoit.win_wait_active(window, WINDOW_TIMEOUT):
        raise TimeoutError(f"Fingerprint window did not appear: {ui.title!r}")

    autoit.win_activate(window)
    autoit.win_set_on_top(window, "", 1)
    _set_block_input(True)
    try:
        # The registration field is focused on launch; send the number, then
        # advance with TAB/SPACE as the app expects.
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
