"""System-tray icon and menu for the AutoBiometrik server.

pystray owns the main thread; menu actions receive ``(icon, item)`` from
pystray. Everything here is defensive: a failed icon load or a failed menu
click must never crash the tray, because the operator's only way to stop the
server is the Quit item.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import webbrowser

import pystray
from PIL import Image

from . import paths
from .config import Config, reload_config

log = logging.getLogger("dekate.autobiometrik")

APP_NAME = "autobiometrik-bpjs"
APP_TITLE = "AutoBiometrik BPJS"
VENDOR = "Dekate"
VENDOR_URL = "https://dekate.id"


def available() -> bool:
    """True when a system tray is supported (Windows)."""
    return sys.platform == "win32"


def load_icon_image() -> Image.Image:
    """Load the bundled tray icon, or a solid fallback if it can't be read."""
    try:
        return Image.open(paths.resource_path("icon.png"))
    except Exception as exc:  # noqa: BLE001 - never let the tray fail to appear
        log.warning("tray icon image unavailable (%s) — using fallback", exc)
        return Image.new("RGB", (64, 64), (13, 71, 161))


def probe_health(cfg: Config, timeout: float = 1.0) -> bool:
    """Return True if the local server is listening on its port.

    A TCP connect is enough: the tray runs in the same process as the server,
    so if the port accepts a connection the werkzeug thread is alive and
    serving. A refused connection (instant) means it is down. No TLS handshake
    is performed, so this works the same for HTTP and HTTPS.
    """
    host = "127.0.0.1" if cfg.host in ("0.0.0.0", "") else cfg.host
    try:
        with socket.create_connection((host, cfg.port), timeout=timeout):
            return True
    except OSError:
        return False


def status_text(cfg: Config) -> str:
    """Live status line for the tray menu, re-evaluated each time it opens."""
    return "● Running" if probe_health(cfg) else "○ Not responding"


def _open_url(url: str) -> None:
    """Open a URL in the default browser (guarded; never raises)."""
    try:
        webbrowser.open(url)
    except Exception as exc:  # noqa: BLE001 - a menu click must not kill the tray
        log.error("failed to open %s: %s", url, exc)


def open_health(cfg: Config) -> None:
    """Open the /health page in the default browser."""
    _open_url(f"{cfg.scheme}://{cfg.host}:{cfg.port}/health")


def open_vendor_site() -> None:
    """Open the Dekate site — the title line doubles as the vendor link."""
    _open_url(VENDOR_URL)


def _edit_text_file(path) -> None:
    """Open a text file in an editor (guarded; never raises).

    On Windows we launch Notepad explicitly rather than os.startfile: types
    like .json/.log often have no file association, and os.startfile then
    returns success without opening anything (silent no-op). Notepad always
    exists and handles both. Other platforms use the default handler.
    """
    path = str(path)
    if sys.platform == "win32":
        try:
            subprocess.Popen(["notepad.exe", path])
        except Exception as exc:  # noqa: BLE001
            log.error("failed to open %s in notepad: %s", path, exc)
        return
    try:
        webbrowser.open(f"file://{path}")
    except Exception as exc:  # noqa: BLE001
        log.error("failed to open %s: %s", path, exc)


def open_logs(log_file) -> None:
    """Open the log file in an editor."""
    _edit_text_file(log_file)


def open_config(cfg: Config) -> None:
    """Open the active config.json in an editor."""
    if not cfg.source_path:
        log.error("no config file path known — cannot open config")
        return
    _edit_text_file(cfg.source_path)


def do_reload(cfg: Config, icon=None) -> None:
    """Reload config from disk and (if given) notify via the tray icon."""
    reload_config(cfg)
    if icon is not None:
        try:
            icon.notify("Configuration reloaded", APP_TITLE)
        except Exception as exc:  # noqa: BLE001 - notify is best-effort
            log.debug("tray notify failed: %s", exc)


def build_menu(cfg: Config, version: str, log_file, on_quit) -> pystray.Menu:
    """Build the tray menu: disabled info lines + actions."""
    caps = (
        f"AutoItX: {_autoit_available()} | "
        f"frista: {cfg.has_credentials} | finger: {cfg.has_finger_credentials}"
    )
    noop = lambda icon, item: None  # noqa: E731 - disabled info lines need a callable
    return pystray.Menu(
        # The only enabled info line: it opens the Dekate site. The lines below
        # it stay disabled so they read as status, not as things to click.
        pystray.MenuItem(
            f"{APP_TITLE} v{version} by {VENDOR}",
            lambda icon, item: open_vendor_site(),
        ),
        # Live status — the callable is re-evaluated each time the menu opens.
        pystray.MenuItem(lambda item: status_text(cfg), noop, enabled=False),
        pystray.MenuItem(f"{cfg.scheme}://{cfg.host}:{cfg.port}", noop, enabled=False),
        pystray.MenuItem(caps, noop, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open health page", lambda icon, item: open_health(cfg)),
        pystray.MenuItem("Open config", lambda icon, item: open_config(cfg)),
        pystray.MenuItem("Open logs", lambda icon, item: open_logs(log_file)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Reload config", lambda icon, item: do_reload(cfg, icon)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )


def run(cfg: Config, version: str, log_file, on_quit) -> None:
    """Create the tray icon and run its loop (blocks until Quit)."""
    icon = pystray.Icon(
        APP_NAME,
        icon=load_icon_image(),
        title=f"{APP_TITLE} v{version} by {VENDOR}",
        menu=build_menu(cfg, version, log_file, on_quit),
    )
    icon.run()


def _autoit_available() -> bool:
    """Late import so this module stays importable off-Windows."""
    try:
        from .automation import AUTOIT_AVAILABLE

        return AUTOIT_AVAILABLE
    except Exception:  # noqa: BLE001
        return False
