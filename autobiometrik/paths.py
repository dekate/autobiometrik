"""Filesystem path helpers that work both from source and when frozen by
PyInstaller.

- ``base_dir()``  — where operator-facing files (config.json, the log file)
  live: next to the .exe when frozen, else the working directory.
- ``resource_path()`` — where read-only bundled assets (the tray icon) live:
  the PyInstaller temp-extract dir when frozen, else the package folder.
"""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    """Folder for operator-editable files (config.json, autobiometrik.log)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def resource_path(name: str) -> Path:
    """Absolute path to a bundled asset shipped inside the package/exe."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "autobiometrik" / name  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / name


def log_path() -> Path:
    """Location of the rotating log file, next to config.json."""
    return base_dir() / "autobiometrik.log"
