# Design: Tray-icon mode for autobiometrik-bpjs

**Date:** 2026-07-16
**Status:** Approved

## Problem

Today `autobiometrik-bpjs.exe` is a PyInstaller **onefile console** app. Launching
it opens a `cmd` window that stays on screen for the life of the Flask server. On a
BPJS kiosk this is visually intrusive and easy to close by accident (which kills the
biometric bridge). We want it to run quietly as a **Windows system tray icon**
instead, with no console window.

## Goals

- No console/`cmd` window when the exe is launched.
- A system tray icon (reusing the existing `autobiometrik/icon.png`) that keeps the
  Flask server running in the background.
- A right-click tray menu to see status, open the health page, open logs, and quit.
- Logs still captured to a file (no console to read), viewable on demand.
- A single-instance guard so a double-launch can't spawn a second copy that fails to
  bind the port or leaves an orphaned tray icon.

## Non-goals

- The VirusTotal / UPX / onefile-vs-onedir packaging changes discussed separately.
  This design leaves the build as **onefile** and only flips console mode. Combining
  the two is a later decision.
- Migrating away from AutoIt.
- Auto-start on Windows boot.

## Architecture

### Threading model

pystray's icon event loop must own the **main thread** on Windows, and Flask's
server call blocks, so the two swap roles relative to today:

- **Flask server** runs on a **background daemon thread**, created with
  `werkzeug.serving.make_server(host, port, app, ssl_context=...)` instead of
  `app.run(...)`. `make_server` returns a server object exposing `serve_forever()`
  and `shutdown()`. `shutdown()` is callable from another thread, which is what makes
  **Quit** clean — today's `app.run()` has no graceful cross-thread stop.
- **pystray icon** runs on the **main thread** via `icon.run()` and stays alive until
  Quit is selected.

### Modules

Keep units small and independently testable:

- **`autobiometrik/tray.py`** — builds the tray `Icon` (loads `icon.png` via PIL),
  assembles the menu, and holds the server reference so menu actions can shut it down.
  Exposes a function to build the menu from a `Config` + runtime facts (pure enough to
  unit-test) and a function to run the icon loop.
- **`autobiometrik/single_instance.py`** — `acquire(name) -> bool`. On Windows uses a
  **named mutex** (`CreateMutexW` via `ctypes`, checking `GetLastError() ==
  ERROR_ALREADY_EXISTS`). On non-Windows it is a no-op returning `True` (dev machines).
  The mutex handle is held for process lifetime.
- **`autobiometrik/paths.py`** (small helper) — `base_dir()` (folder of the exe when
  frozen, else the project/cwd) and `resource_path(rel)` (resolves bundled data via
  `sys._MEIPASS` when frozen). Used for the log-file location and the tray icon image.
- **`autobiometrik/app.py`** `main()` becomes the orchestrator:
  1. `acquire()` the single-instance lock; if it fails, exit immediately.
  2. Set up file logging (rotating handler).
  3. Build the Flask app (`create_app`).
  4. Build the TLS context if configured (unchanged logic, moved as needed).
  5. `make_server(...)`, start `serve_forever()` on a daemon thread.
  6. Run the tray on the main thread (or foreground fallback — see below).

`create_app()` and all HTTP endpoints are unchanged.

### Tray menu

- `AutoBiometrik BPJS v<version>` — **disabled** info line.
- `<scheme>://<host>:<port>` — **disabled** info line (listening URL).
- `AutoItX: <bool> | frista: <bool> | finger: <bool>` — **disabled** info line.
- separator
- **Open health page** → `webbrowser.open("<scheme>://<host>:<port>/health")`.
- **Open logs** → `os.startfile(log_path)` (opens in the default text editor).
- separator
- **Quit** → `server.shutdown()` then `icon.stop()`.

### Logging

A windowed PyInstaller exe can have `sys.stdout`/`sys.stderr` as `None`, so `print`
and stderr logging are unsafe. Replace the current `print(banner)` +
`logging.basicConfig(stderr)` with:

- A **`RotatingFileHandler`** writing `autobiometrik.log` in `base_dir()` (the same
  folder as `config.json`), capped at ~1 MB with 3 backups.
- The existing startup banner (MOTD box + version/status lines) is written to the log
  as the first entries instead of printed.
- Logging setup guards against `sys.stdout is None` so nothing raises under windowed
  mode.

### Build changes

- `autobiometrik-bpjs.spec`: `console=True` → `console=False`. Icon stays embedded.
- Bundle the tray image: add `autobiometrik/icon.png` to `Analysis(datas=...)` so
  `resource_path("icon.png")` resolves when frozen.
- Add `pystray` to `requirements.txt` (and `hiddenimports` if PyInstaller misses it).
  `pystray` pulls in a Windows backend; verify it's collected in the frozen build.

### Dev-machine fallback

On non-Windows, or when pystray / a display is unavailable, `main()` logs a notice and
runs the server in the **foreground** (today's blocking behavior) with no tray. This
keeps development on other OSes and the automated test suite working.

## Error handling

- **Second instance:** `acquire()` returns `False` → log "already running" and exit 0
  (no error dialog, no port bind attempt).
- **Icon image missing/unreadable:** fall back to a generated 1-color PIL image so the
  tray still appears rather than crashing.
- **Server thread crash:** logged via the existing `_safe`-style guards; the tray keeps
  running so the operator can still Quit.
- **`os.startfile` / `webbrowser` failure:** wrapped so a menu click never crashes the
  tray; the exception is logged.

## Testing

Existing endpoint/config tests (`tests/test_app.py`, `tests/test_config.py`) stay
untouched and must keep passing.

New unit tests cover the pure logic (not the GUI loop):

- **Menu construction:** given a `Config`, the builder yields the expected item labels
  and enabled/disabled states; the health-page and logs actions target the right
  URL/path.
- **Path resolution:** `base_dir()` / `resource_path()` behave correctly for the
  non-frozen (source) case; frozen case documented/mocked via `sys.frozen`/`_MEIPASS`.
- **Single-instance guard:** the non-Windows path returns `True`; the Windows path is
  covered where the platform allows (mocked `ctypes` or skipped off-Windows).

The pystray event loop itself is not unit-tested (standard for tray apps).

## Dependencies

- New runtime dependency: `pystray` (Windows tray). Pillow is already present.
- No changes to Flask / flask-cors / PyAutoIt.
