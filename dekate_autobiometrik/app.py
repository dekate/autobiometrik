"""Dekate AutoBiometrik — local HTTP bridge for BPJS biometric apps.

Runs a small Flask server on the kiosk machine. The queue/kiosk web app calls
these endpoints with a patient's BPJS number; this service launches the matching
BPJS desktop app (FRISTA face recognition or the fingerprint app) and drives its
login/registration via AutoIt.

Endpoints (GET, kept compatible with earlier kiosk integrations):

    /run_exe?no_peserta=<bpjs>          launch + log in to FRISTA (face)
    /run_finger_exec?no_peserta=<bpjs>  launch + send number to fingerprint app
    /stop_exec                          terminate FRISTA
    /stop_finger_exec                   terminate the fingerprint app
    /health                             liveness + capability probe

Long-running desktop automation is dispatched on a background thread so the HTTP
call returns immediately (the app appears on screen; the kiosk UI moves on).
"""

from __future__ import annotations

import logging
import threading

from flask import Flask, jsonify, request
from flask_cors import CORS

from . import __version__
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
                "service": "dekate-autobiometrik",
                "version": __version__,
                "autoit": AUTOIT_AVAILABLE,
                "has_credentials": cfg.has_credentials,
            }
        )

    @app.get("/run_exe")
    def run_exe():
        """Launch FRISTA (face recognition) and log in — non-blocking."""
        no_peserta = request.args.get("no_peserta")
        if not no_peserta:
            return jsonify({"status": "error", "message": "Parameter no_peserta is required"}), 400

        _run_in_background(_safe, launch_frista, no_peserta, cfg)
        return jsonify(
            {"status": "running", "target": "frista", "no_peserta": no_peserta}
        )

    @app.get("/run_finger_exec")
    def run_finger_exec():
        """Launch the fingerprint app and send the BPJS number — non-blocking."""
        no_peserta = request.args.get("no_peserta")
        if not no_peserta:
            return jsonify({"status": "error", "message": "Parameter no_peserta is required"}), 400

        _run_in_background(_safe, launch_finger, no_peserta, cfg)
        return jsonify(
            {"status": "running", "target": "finger", "no_peserta": no_peserta}
        )

    @app.get("/stop_exec")
    def stop_exec():
        running = stop_process(FRISTA_IMAGE)
        return jsonify({"status": "ok", "target": "frista", "was_running": running})

    @app.get("/stop_finger_exec")
    def stop_finger_exec():
        running = stop_process(FINGER_IMAGE)
        return jsonify({"status": "ok", "target": "finger", "was_running": running})

    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = load_config()
    app = create_app(cfg)

    banner = (
        "\n"
        "  Dekate AutoBiometrik\n"
        "  BPJS biometric bridge (FRISTA / fingerprint)\n"
        f"  by Dekate — https://github.com/dekate/autobiometrik\n"
        f"  listening on http://{cfg.host}:{cfg.port}\n"
        f"  AutoItX available: {AUTOIT_AVAILABLE} | credentials set: {cfg.has_credentials}\n"
    )
    print(banner)
    if not AUTOIT_AVAILABLE:
        log.warning(
            "AutoItX not available — endpoints will respond but no desktop "
            "automation will run. Install on Windows: pip install PyAutoIt"
        )

    # threaded=True so a slow /run_* dispatch never blocks /stop_*.
    app.run(host=cfg.host, port=cfg.port, threaded=True)


if __name__ == "__main__":
    main()
