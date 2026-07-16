# Tray-Icon Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `autobiometrik-bpjs` from a console (cmd-window) app into a Windows system-tray app whose Flask server runs quietly in the background.

**Architecture:** Flask runs on a background daemon thread via `werkzeug.serving.make_server` (whose `.shutdown()` enables a clean Quit); a `pystray` icon owns the main thread. A named-mutex single-instance guard blocks double-launches. Logging goes to a rotating file next to the exe (no console). On non-Windows or when a tray is unavailable, `main()` falls back to running the server in the foreground.

**Tech Stack:** Python 3.14, Flask, Werkzeug, pystray 0.19.5, Pillow, PyInstaller (onefile), ctypes (Win32 mutex).

## Global Constraints

- Existing HTTP endpoints and `create_app(config)` behavior must not change; `tests/test_app.py` and `tests/test_config.py` must keep passing.
- Windows is the target; non-Windows must still import, run the server in foreground, and pass the test suite (dev machines).
- No `print()` / stderr reliance in `main()` — a windowed PyInstaller exe may have `sys.stdout`/`sys.stderr` == `None`.
- Log file: `autobiometrik.log` in the same folder as `config.json` (the `base_dir()`), rotating ~1 MB × 3 backups.
- Build stays **onefile**; only `console` flips to `False`. Do not change UPX/onedir here.
- Package name for the mutex and tray: `autobiometrik-bpjs`. Version string comes from `autobiometrik.__version__`.
- Follow Conventional Commits for every commit.

---

### Task 1: `paths.py` — frozen-aware path helpers

**Files:**
- Create: `autobiometrik/paths.py`
- Modify: `autobiometrik/config.py` (replace body of `_base_dir` to delegate — DRY)
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces:
  - `base_dir() -> pathlib.Path` — folder of the exe when frozen (`sys.frozen`), else `Path.cwd()`.
  - `resource_path(name: str) -> pathlib.Path` — bundled data file; frozen → `Path(sys._MEIPASS)/"autobiometrik"/name`, else `Path(__file__).parent/name` (the package dir).
  - `log_path() -> pathlib.Path` — `base_dir()/"autobiometrik.log"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_paths.py`:

```python
from pathlib import Path

from autobiometrik import paths


def test_base_dir_is_cwd_when_not_frozen():
    assert paths.base_dir() == Path.cwd()


def test_resource_path_points_into_package_when_not_frozen():
    p = paths.resource_path("icon.png")
    assert p.name == "icon.png"
    assert p.parent.name == "autobiometrik"
    assert p.exists()  # icon.png already ships in the package


def test_log_path_is_autobiometrik_log_in_base_dir():
    assert paths.log_path() == paths.base_dir() / "autobiometrik.log"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autobiometrik.paths'`

- [ ] **Step 3: Write minimal implementation**

Create `autobiometrik/paths.py`:

```python
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
```

- [ ] **Step 4: Make `config.py` delegate to `paths` (DRY)**

In `autobiometrik/config.py`, replace the existing `_base_dir` function body (lines ~83-92) so it delegates:

```python
from . import paths as _paths


def _base_dir() -> Path:
    """Directory to look for config files in. Delegates to paths.base_dir()."""
    return _paths.base_dir()
```

Add the `from . import paths as _paths` import alongside the other imports at the top of `config.py`. Leave the rest of `config.py` unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_paths.py tests/test_config.py -v`
Expected: PASS (new path tests + unchanged config tests)

- [ ] **Step 6: Commit**

```bash
git add autobiometrik/paths.py autobiometrik/config.py tests/test_paths.py
git commit -m "feat: add frozen-aware path helpers and reuse in config"
```

---

### Task 2: `single_instance.py` — named-mutex guard

**Files:**
- Create: `autobiometrik/single_instance.py`
- Test: `tests/test_single_instance.py`

**Interfaces:**
- Produces: `acquire(name: str) -> bool` — returns `True` if this process now owns the lock, `False` if another process already holds it. Non-Windows always returns `True`. The underlying handle is kept alive for the process lifetime.

- [ ] **Step 1: Write the failing test**

Create `tests/test_single_instance.py`:

```python
import sys

import pytest

from autobiometrik import single_instance


def test_acquire_true_off_windows():
    if sys.platform == "win32":
        pytest.skip("covered by the Windows-specific test")
    assert single_instance.acquire("autobiometrik-test-nonwin") is True


def test_second_acquire_same_name_fails_on_windows():
    if sys.platform != "win32":
        pytest.skip("named mutex is Windows-only")
    name = "autobiometrik-bpjs-test-guard-A1"
    assert single_instance.acquire(name) is True
    assert single_instance.acquire(name) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_single_instance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autobiometrik.single_instance'`

- [ ] **Step 3: Write minimal implementation**

Create `autobiometrik/single_instance.py`:

```python
"""Single-instance guard.

On Windows a named kernel mutex is the simplest cross-process lock: the first
process creates it; any later process that creates the same name gets
ERROR_ALREADY_EXISTS. Non-Windows platforms (dev machines) are not guarded.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("dekate.autobiometrik")

# Keep created handles referenced for the process lifetime so the OS holds the
# mutex until exit.
_handles: list[int] = []

_ERROR_ALREADY_EXISTS = 183


def acquire(name: str) -> bool:
    """True if this process now owns the lock; False if already held elsewhere."""
    if sys.platform != "win32":
        return True

    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, False, name)
    last_error = kernel32.GetLastError()

    if not handle:
        # Could not create the mutex at all — don't block startup over it.
        log.warning("single-instance mutex could not be created (err=%s)", last_error)
        return True

    if last_error == _ERROR_ALREADY_EXISTS:
        return False

    _handles.append(handle)
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_single_instance.py -v`
Expected: PASS (Windows: both asserts; non-Windows: first test passes, second skips)

- [ ] **Step 5: Commit**

```bash
git add autobiometrik/single_instance.py tests/test_single_instance.py
git commit -m "feat: add single-instance guard via named mutex"
```

---

### Task 3: `tray.py` — icon image, menu actions, menu builder

**Files:**
- Create: `autobiometrik/tray.py`
- Test: `tests/test_tray.py`

**Interfaces:**
- Consumes: `autobiometrik.config.Config`; `autobiometrik.paths.resource_path`.
- Produces:
  - `available() -> bool` — `True` on Windows (tray supported), else `False`.
  - `load_icon_image() -> PIL.Image.Image` — loads `icon.png`, or a solid fallback image if unreadable.
  - `open_health(cfg: Config) -> None` — opens `<scheme>://<host>:<port>/health` in the browser.
  - `open_logs(log_file) -> None` — opens the log file in the default editor (`os.startfile`), guarded.
  - `build_menu(cfg: Config, version: str, log_file, on_quit) -> pystray.Menu` — status/URL info lines (disabled), Open health page, Open logs, Quit. `on_quit` is a `(icon, item)` callable.
  - `run(cfg: Config, version: str, log_file, on_quit) -> None` — creates the `pystray.Icon` and runs its loop (blocks; not unit-tested).

- [ ] **Step 1: Write the failing test**

Create `tests/test_tray.py`:

```python
from unittest import mock

import pytest

from autobiometrik import tray
from autobiometrik.config import Config


def test_load_icon_image_returns_pil_image():
    img = tray.load_icon_image()
    assert img.size[0] > 0 and img.size[1] > 0


def test_open_health_opens_scheme_host_port():
    cfg = Config(host="127.0.0.1", port=5000)
    with mock.patch("autobiometrik.tray.webbrowser.open") as m:
        tray.open_health(cfg)
    m.assert_called_once_with("http://127.0.0.1:5000/health")


def test_open_health_uses_https_when_tls():
    cfg = Config(host="0.0.0.0", port=8443, tls_cert="c.pem", tls_key="k.pem")
    with mock.patch("autobiometrik.tray.webbrowser.open") as m:
        tray.open_health(cfg)
    m.assert_called_once_with("https://0.0.0.0:8443/health")


def test_build_menu_has_expected_items():
    cfg = Config(username="u", password="p")
    quit_called = []
    menu = tray.build_menu(
        cfg, "1.0.0", "C:/x/autobiometrik.log", lambda icon, item: quit_called.append(True)
    )
    texts = [item.text for item in menu.items]
    # info line with version, URL line, capability line, then actions
    assert any("1.0.0" in t for t in texts)
    assert any("127.0.0.1:5000" in t for t in texts)
    assert "Open health page" in texts
    assert "Open logs" in texts
    assert "Quit" in texts


def test_build_menu_info_lines_are_disabled():
    cfg = Config()
    menu = tray.build_menu(cfg, "1.0.0", "log.txt", lambda icon, item: None)
    by_text = {item.text: item for item in menu.items}
    version_line = next(item for item in menu.items if "1.0.0" in item.text)
    assert version_line.enabled is False
    assert by_text["Quit"].enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tray.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'autobiometrik.tray'`

- [ ] **Step 3: Write minimal implementation**

Create `autobiometrik/tray.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tray.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 5: Commit**

```bash
git add autobiometrik/tray.py tests/test_tray.py
git commit -m "feat: add tray icon, menu, and menu actions"
```

---

### Task 4: Rework `app.main()` — file logging, background server, tray/foreground

**Files:**
- Modify: `autobiometrik/app.py` (imports; replace `main()`; add `_setup_logging`, `_build_ssl_context`)
- Test: `tests/test_app.py` (add logging-setup test; existing tests unchanged)

**Interfaces:**
- Consumes: `paths.log_path`, `single_instance.acquire`, `tray.available`, `tray.run`, `werkzeug.serving.make_server`.
- Produces:
  - `_setup_logging(log_file) -> None` — installs a `RotatingFileHandler` (1 MB × 3) on the `dekate.autobiometrik` logger; safe when `sys.stdout is None`.
  - `_build_ssl_context(cfg) -> ssl.SSLContext | None` — the TLS logic currently inline in `main()`.
  - `main() -> None` — orchestrator (see Step 3).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_setup_logging_writes_to_file(tmp_path):
    import logging

    from autobiometrik.app import _setup_logging

    log_file = tmp_path / "autobiometrik.log"
    _setup_logging(log_file)
    logging.getLogger("dekate.autobiometrik").info("hello-tray-test")

    for h in logging.getLogger("dekate.autobiometrik").handlers:
        h.flush()
    assert log_file.exists()
    assert "hello-tray-test" in log_file.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py::test_setup_logging_writes_to_file -v`
Expected: FAIL with `ImportError: cannot import name '_setup_logging'`

- [ ] **Step 3: Write the implementation**

In `autobiometrik/app.py`, update the imports near the top (add to the existing import block):

```python
import logging
import threading
from logging.handlers import RotatingFileHandler

from werkzeug.serving import make_server

from . import paths, single_instance, tray
```

(Keep the existing `from . import __version__`, automation imports, and config imports.)

Replace the entire `main()` function (currently the block that does `basicConfig`, builds `ssl_context` inline, prints the banner, and calls `app.run`) with the following three definitions:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS (all existing tests + the new logging test)

- [ ] **Step 5: Commit**

```bash
git add autobiometrik/app.py tests/test_app.py
git commit -m "feat: run server on background thread with tray and file logging"
```

---

### Task 5: Build config — `console=False`, bundle icon, add pystray

**Files:**
- Modify: `autobiometrik-bpjs.spec`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: everything above.
- Produces: a windowed onefile exe with the tray icon image bundled.

- [ ] **Step 1: Add pystray to requirements**

Append to `requirements.txt`:

```
pystray>=0.19; sys_platform == "win32"
```

- [ ] **Step 2: Bundle icon.png and add pystray hidden import**

In `autobiometrik-bpjs.spec`, change the `Analysis(...)` call: set `datas` and extend `hiddenimports`:

```python
    datas=[("autobiometrik/icon.png", "autobiometrik")],
    hiddenimports=["autoit", "pystray._win32"],
```

- [ ] **Step 3: Switch to windowed mode**

In `autobiometrik-bpjs.spec`, in the `EXE(...)` call, change:

```python
    console=False,
```

(Leave `icon="autobiometrik/icon.ico"` and everything else as-is.)

- [ ] **Step 4: Rebuild**

First ensure no old instance holds the exe open:

Run: `powershell -Command "Get-Process -Name 'autobiometrik-bpjs' -ErrorAction SilentlyContinue | Stop-Process -Force"`

Then build:

Run: `pyinstaller autobiometrik-bpjs.spec --noconfirm`
Expected: `Build complete!` and `dist/autobiometrik-bpjs.exe` present.

- [ ] **Step 5: Manual smoke test (documented — human/agent verifies)**

1. Double-click `dist/autobiometrik-bpjs.exe`. Expected: **no cmd window**; a tray icon appears (the dashed-circle logo).
2. `curl http://127.0.0.1:5000/health` → JSON with `"status":"ok"`.
3. Right-click the tray icon: see the version line, `http://127.0.0.1:5000`, the capability line, **Open health page**, **Open logs**, **Quit**.
4. Click **Open logs** → `autobiometrik.log` opens and contains the banner.
5. Launch the exe a second time → no second icon, no crash (single-instance guard); the log notes "already running".
6. Click **Quit** → tray icon disappears and the process exits (`Get-Process autobiometrik-bpjs` returns nothing).

- [ ] **Step 6: Commit**

```bash
git add autobiometrik-bpjs.spec requirements.txt
git commit -m "build: run as windowed tray app and bundle tray icon"
```

---

## Notes for the implementer

- The `dekate.autobiometrik` logger is used everywhere (`log = logging.getLogger("dekate.autobiometrik")`). `_setup_logging` configures that logger, not the root logger, so keep the name exact.
- `pystray.Menu.items` is iterable and each `MenuItem` exposes `.text` and `.enabled` — that's what the Task 3 tests assert against.
- pystray menu action callables always receive `(icon, item)`; that's why info-line actions are `lambda icon, item: None` and `on_quit(icon, item)` takes both.
- `make_server(..., threaded=True)` returns a server whose `.shutdown()` is safe to call from the tray thread — this is what makes Quit clean.
- Do not reintroduce `print()` in `main()`; the windowed exe may have no stdout.
