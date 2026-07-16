"""Configuration loading for Dekate AutoBiometrik.

Credentials and executable paths are read from ``config.json`` sitting next to
the running program (or from a path given via ``--config`` / ``DEKATE_CONFIG``).
An optional legacy ``config.conf`` (INI) supplies the FRISTA API URL and camera
id, matching the original file layout so existing kiosk installs keep working.

Nothing here ever leaves the machine: the HTTP server only receives a BPJS
number from the kiosk and reads these local files to know how to log in.
"""

from __future__ import annotations

import configparser
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import paths as _paths

log = logging.getLogger("dekate.autobiometrik")

# Sensible Windows defaults for a stock BPJS workstation. Override in config.json.
DEFAULT_FRISTA_PATH = r"C:\frista\frista.exe"
DEFAULT_FINGER_PATH = (
    r"C:\Program Files (x86)\BPJS Kesehatan"
    r"\Aplikasi Sidik Jari BPJS Kesehatan\After.exe"
)
DEFAULT_FRISTA_API = "https://frista.bpjs-kesehatan.go.id/frista-api"


@dataclass
class Config:
    """Resolved runtime configuration."""

    # Face recognition (FRISTA) desktop app
    frista_path: str = DEFAULT_FRISTA_PATH
    # Fingerprint desktop app (BPJS "After.exe")
    finger_path: str = DEFAULT_FINGER_PATH
    # FRISTA login credentials (typed into the app's login window)
    username: str = ""
    password: str = ""
    # Fingerprint app login credentials — a separate account from FRISTA.
    # When set, the fingerprint launch logs in first before sending the
    # BPJS number; when empty, the login step is skipped (app assumed to be
    # already logged in).
    finger_username: str = ""
    finger_password: str = ""
    # Server bind
    host: str = "127.0.0.1"
    port: int = 5000
    # TLS — when both are set, the server runs over HTTPS. Needed when the
    # kiosk page is served over HTTPS (a secure page cannot reliably reach an
    # http:// helper). See the "Running behind an HTTPS kiosk" section of the
    # README for how to obtain a trusted certificate.
    tls_cert: str = ""
    tls_key: str = ""
    # Extras (kept for parity with the legacy config.conf)
    frista_api: str = DEFAULT_FRISTA_API
    camera_id: int = 0

    # Bookkeeping
    source_path: str | None = field(default=None)

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)

    @property
    def has_finger_credentials(self) -> bool:
        return bool(self.finger_username and self.finger_password)

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_cert and self.tls_key)

    @property
    def scheme(self) -> str:
        return "https" if self.tls_enabled else "http"


def _base_dir() -> Path:
    """Directory to look for config files in. Delegates to paths.base_dir()."""
    return _paths.base_dir()


def _load_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh) or {}
    except FileNotFoundError:
        log.warning("config.json not found at %s — using defaults", path)
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        log.error("failed to read %s: %s — using defaults", path, exc)
        return {}


def _load_conf(path: Path) -> dict:
    """Read the legacy ``[Config]`` INI (api, camera_id). Best effort."""
    if not path.exists():
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError) as exc:
        log.warning("failed to read %s: %s", path, exc)
        return {}
    if not parser.has_section("Config"):
        return {}
    section = parser["Config"]
    conf: dict = {}
    if "api" in section:
        conf["frista_api"] = section["api"].strip()
    if "camera_id" in section:
        try:
            conf["camera_id"] = int(section["camera_id"])
        except ValueError:
            pass
    return conf


def load_config(config_path: str | os.PathLike | None = None) -> Config:
    """Build a :class:`Config` from config.json (+ optional config.conf).

    Resolution order for the config file:
    1. explicit ``config_path`` argument
    2. ``DEKATE_CONFIG`` environment variable
    3. ``config.json`` next to the program / in the working directory
    """
    base = _base_dir()

    if config_path is None:
        config_path = os.environ.get("DEKATE_CONFIG")

    json_path = Path(config_path) if config_path else base / "config.json"
    conf_path = base / "config.conf"

    data = _load_json(json_path)
    legacy = _load_conf(conf_path)

    cfg = Config()

    # Executable paths: accept both the modern keys and the legacy
    # "path" / "pathfinger" keys from the original config.json.
    cfg.frista_path = data.get("frista_path") or data.get("path") or cfg.frista_path
    cfg.finger_path = data.get("finger_path") or data.get("pathfinger") or cfg.finger_path
    cfg.username = data.get("username", cfg.username)
    cfg.password = data.get("password", cfg.password)
    cfg.finger_username = data.get("finger_username", cfg.finger_username)
    cfg.finger_password = data.get("finger_password", cfg.finger_password)
    cfg.host = data.get("host", cfg.host)
    try:
        cfg.port = int(data.get("port", cfg.port))
    except (TypeError, ValueError):
        pass
    cfg.tls_cert = data.get("tls_cert", cfg.tls_cert)
    cfg.tls_key = data.get("tls_key", cfg.tls_key)

    cfg.frista_api = data.get("frista_api") or legacy.get("frista_api", cfg.frista_api)
    cfg.camera_id = data.get("camera_id", legacy.get("camera_id", cfg.camera_id))

    cfg.source_path = str(json_path)
    return cfg


# Fields safe to refresh while the server is running. Bind-time settings
# (host, port, tls_cert, tls_key) are deliberately excluded: the server is
# already listening, so changing them needs a full restart, and overwriting
# them at runtime would desync the live status probe.
_RELOADABLE_FIELDS = (
    "frista_path",
    "finger_path",
    "username",
    "password",
    "finger_username",
    "finger_password",
    "frista_api",
    "camera_id",
)


def reload_config(cfg: Config) -> Config:
    """Re-read the config file and update ``cfg`` in place.

    Only runtime-mutable fields (credentials, executable paths, extras) are
    refreshed; bind-time fields (host/port/TLS) are left as-is because the
    running server cannot rebind without a restart. Mutating in place means
    endpoints and the tray that already hold this ``cfg`` see the new values.
    """
    fresh = load_config(cfg.source_path)
    for name in _RELOADABLE_FIELDS:
        setattr(cfg, name, getattr(fresh, name))
    log.info("config reloaded from %s", cfg.source_path)
    return cfg
