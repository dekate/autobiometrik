"""Dekate AutoBiometrik — local HTTP bridge for BPJS biometric apps.

Runs a small Flask server on the kiosk machine. The queue/kiosk web app calls
these endpoints with a patient's BPJS number; this service launches the matching
BPJS desktop app (FRISTA face recognition or the fingerprint app) and drives its
login/registration via AutoIt.

Endpoints (GET):

    /start_frista?no_peserta=<bpjs>  launch + log in to FRISTA (face)
    /start_finger?no_peserta=<bpjs>  launch + send number to fingerprint app
    /stop_frista                     terminate FRISTA
    /stop_finger                     terminate the fingerprint app
    /health                          liveness + capability probe

Long-running desktop automation is dispatched on a background thread so the HTTP
call returns immediately (the app appears on screen; the kiosk UI moves on).
"""

from __future__ import annotations

import logging
import threading
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.serving import make_server

from . import __version__, paths, single_instance, tray
from .automation import (
    AUTOIT_AVAILABLE,
    stop_process,
    launch_finger,
    launch_frista,
)
from .config import Config, load_config

log = logging.getLogger("dekate.autobiometrik")

# Image names used to stop the desktop apps.
FRISTA_IMAGE = "frista.exe"
FINGER_IMAGE = "After.exe"

_MOTD_ART = (
    " ______   _______  ___   _  _______  _______  _______ ",
    "|      | |       ||   | | ||   _   ||       ||       |",
    "|  _    ||    ___||   |_| ||  |_|  ||_     _||    ___|",
    "| | |   ||   |___ |      _||       |  |   |  |   |___ ",
    "| |_|   ||    ___||     |_ |       |  |   |  |    ___|",
    "|       ||   |___ |    _  ||   _   |  |   |  |   |___ ",
    "|______| |_______||___| |_||__| |__|  |___|  |_______|",
)

_MOTD_DESCRIPTION = (
    "AutoBiometrik BPJS is a local HTTP bridge for BPJS biometric",
    "verification on kiosk machines. It receives a patient's BPJS",
    "number from the queue/kiosk web app, then launches and drives",
    "the matching BPJS desktop app (FRISTA face recognition or the",
    "fingerprint app) automatically via AutoIt.",
)


def motd() -> str:
    """Boxed startup banner: DEKATE ASCII art + a short app description."""
    width = 65

    def center(text: str = "") -> str:
        return f"*{text.center(width)}*"

    def left(text: str = "") -> str:
        return f"*{(' ' + text).ljust(width)}*"

    lines = ["*" * (width + 2)]
    lines.append(center("AutoBiometrik BPJS managed by"))
    lines.extend(center(row) for row in _MOTD_ART)
    lines.append(center("=" * (width - 2)))
    lines.append(left())
    lines.extend(left(row) for row in _MOTD_DESCRIPTION)
    lines.append(left())
    lines.append("*" * (width + 2))
    return "\n".join(lines)


def _run_in_background(target, *args) -> None:
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()


def _safe(target, *args) -> None:
    """Run an automation call, logging any failure instead of dying silently."""
    try:
        target(*args)
    except Exception as exc:  # noqa: BLE001 - background worker must not crash
        log.error("%s failed: %s", getattr(target, "__name__", target), exc)


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()

    app = Flask(__name__)
    CORS(app)  # kiosk SPA is served from a different origin
    app.config["DEKATE_CFG"] = cfg

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "service": "autobiometrik-bpjs",
                "version": __version__,
                "autoit": AUTOIT_AVAILABLE,
                "has_credentials": cfg.has_credentials,
                "has_finger_credentials": cfg.has_finger_credentials,
                "scheme": cfg.scheme,
            }
        )

    @app.get("/start_frista")
    def start_frista():
        """Launch FRISTA (face recognition) and log in — non-blocking."""
        no_peserta = request.args.get("no_peserta")
        if not no_peserta:
            return jsonify({"status": "error", "message": "Parameter no_peserta is required"}), 400

        _run_in_background(_safe, launch_frista, no_peserta, cfg)
        return jsonify(
            {"status": "running", "target": "frista", "no_peserta": no_peserta}
        )

    @app.get("/start_finger")
    def start_finger():
        """Launch the fingerprint app and send the BPJS number — non-blocking."""
        no_peserta = request.args.get("no_peserta")
        if not no_peserta:
            return jsonify({"status": "error", "message": "Parameter no_peserta is required"}), 400

        _run_in_background(_safe, launch_finger, no_peserta, cfg)
        return jsonify(
            {"status": "running", "target": "finger", "no_peserta": no_peserta}
        )

    @app.get("/stop_frista")
    def stop_frista():
        running = stop_process(FRISTA_IMAGE)
        return jsonify({"status": "ok", "target": "frista", "was_running": running})

    @app.get("/stop_finger")
    def stop_finger():
        running = stop_process(FINGER_IMAGE)
        return jsonify({"status": "ok", "target": "finger", "was_running": running})

    return app


def _setup_logging(log_file) -> None:
    """Send logs to a rotating file (no console under windowed mode)."""
    handler = RotatingFileHandler(
        str(log_file), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger("dekate.autobiometrik")
    root.setLevel(logging.INFO)
    # Avoid stacking duplicate handlers if called twice.
    root.handlers = [
        h for h in root.handlers if not isinstance(h, RotatingFileHandler)
    ]
    root.addHandler(handler)


def _build_ssl_context(cfg):
    """Build a TLS context when a cert+key are configured, else None."""
    if not cfg.tls_enabled:
        return None
    import os
    import ssl

    if not os.path.exists(cfg.tls_cert) or not os.path.exists(cfg.tls_key):
        log.error(
            "tls_cert / tls_key configured but not found (%s, %s) — "
            "falling back to HTTP",
            cfg.tls_cert,
            cfg.tls_key,
        )
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cfg.tls_cert, cfg.tls_key)
    return ctx


def main() -> None:
    log_file = paths.log_path()
    _setup_logging(log_file)

    if not single_instance.acquire("autobiometrik-bpjs"):
        log.warning("another AutoBiometrik instance is already running — exiting")
        return

    cfg = load_config()
    app = create_app(cfg)
    ssl_context = _build_ssl_context(cfg)
    scheme = "https" if ssl_context else "http"

    # Banner goes to the log file (there is no console under windowed mode).
    log.info("%s", motd())
    log.info(
        "v%s - listening on %s://%s:%s | AutoItX: %s | frista creds: %s | finger creds: %s",
        __version__,
        scheme,
        cfg.host,
        cfg.port,
        AUTOIT_AVAILABLE,
        cfg.has_credentials,
        cfg.has_finger_credentials,
    )
    if not AUTOIT_AVAILABLE:
        log.warning(
            "AutoItX not available — endpoints respond but no desktop automation "
            "will run. Install on Windows: pip install PyAutoIt"
        )

    server = make_server(
        cfg.host, cfg.port, app, threaded=True, ssl_context=ssl_context
    )

    if not tray.available():
        # Dev / non-Windows: run in the foreground like before.
        log.info("tray unavailable — running server in foreground")
        server.serve_forever()
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def on_quit(icon, item):
        log.info("quit requested from tray")
        server.shutdown()
        icon.stop()

    tray.run(cfg, __version__, log_file, on_quit)


if __name__ == "__main__":
    main()
