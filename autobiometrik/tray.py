"""System-tray icon and menu for the AutoBiometrik server.

pystray owns the main thread; menu actions receive ``(icon, item)`` from
pystray. Everything here is defensive: a failed icon load or a failed menu
click must never crash the tray, because the operator's only way to stop the
server is the Quit item.
"""

from __future__ import annotations

import logging
import os
import sys
import webbrowser

import pystray
from PIL import Image

from . import paths
from .config import Config

log = logging.getLogger("dekate.autobiometrik")

APP_NAME = "autobiometrik-bpjs"
APP_TITLE = "AutoBiometrik BPJS"


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


def open_health(cfg: Config) -> None:
    """Open the /health page in the default browser."""
    url = f"{cfg.scheme}://{cfg.host}:{cfg.port}/health"
    try:
        webbrowser.open(url)
    except Exception as exc:  # noqa: BLE001
        log.error("failed to open health page %s: %s", url, exc)


def open_logs(log_file) -> None:
    """Open the log file in the default editor (guarded)."""
    try:
        os.startfile(str(log_file))  # type: ignore[attr-defined]  # Windows only
    except AttributeError:
        # Non-Windows dev fallback.
        webbrowser.open(f"file://{log_file}")
    except Exception as exc:  # noqa: BLE001
        log.error("failed to open logs %s: %s", log_file, exc)


def build_menu(cfg: Config, version: str, log_file, on_quit) -> pystray.Menu:
    """Build the tray menu: disabled info lines + actions."""
    caps = (
        f"AutoItX: {_autoit_available()} | "
        f"frista: {cfg.has_credentials} | finger: {cfg.has_finger_credentials}"
    )
    noop = lambda icon, item: None  # noqa: E731 - disabled info lines need a callable
    return pystray.Menu(
        pystray.MenuItem(f"{APP_TITLE} v{version}", noop, enabled=False),
        pystray.MenuItem(f"{cfg.scheme}://{cfg.host}:{cfg.port}", noop, enabled=False),
        pystray.MenuItem(caps, noop, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open health page", lambda icon, item: open_health(cfg)),
        pystray.MenuItem("Open logs", lambda icon, item: open_logs(log_file)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )


def run(cfg: Config, version: str, log_file, on_quit) -> None:
    """Create the tray icon and run its loop (blocks until Quit)."""
    icon = pystray.Icon(
        APP_NAME,
        icon=load_icon_image(),
        title=f"{APP_TITLE} v{version}",
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
