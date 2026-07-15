# Dekate AutoBiometrik

A tiny local HTTP bridge that lets a web-based hospital **queue/kiosk** system
drive the two BPJS Kesehatan biometric desktop apps — **FRISTA** (face
recognition) and the **fingerprint** app ("After.exe") — without an operator
having to open them and type anything by hand.

The kiosk sends a patient's BPJS number to this service; the service launches the
right desktop app, fills in the login/registration for you (via
[AutoIt](https://www.autoitscript.com/)), and gets out of the way.

> Made and open-sourced by **[Dekate](https://github.com/dekate)** so any hospital
> or vendor can use and adapt it. MIT licensed.

---

## Why this exists

The BPJS biometric programs are native Windows apps — a browser can't talk to
them directly. This service is the missing link: a small
[Flask](https://flask.palletsprojects.com/) server on the kiosk PC exposing a
handful of HTTP endpoints your kiosk web app can call.

```
┌─────────────┐   HTTP GET /run_exe?no_peserta=0001xxxx   ┌──────────────────────┐
│  Kiosk web  │ ───────────────────────────────────────► │  Dekate AutoBiometrik │
│  (browser)  │                                           │   (this service)      │
└─────────────┘                                           └──────────┬───────────┘
                                                                     │ launches + AutoIt
                                                                     ▼
                                                     FRISTA.exe / After.exe (BPJS apps)
```

## Endpoints

All are `GET` and return JSON. CORS is open so a kiosk page on any origin can
call them.

| Endpoint | Query | Action |
|---|---|---|
| `/run_exe` | `no_peserta` | Launch FRISTA (face) and log in with the configured credentials |
| `/run_finger_exec` | `no_peserta` | Launch the fingerprint app and type the BPJS number |
| `/stop_exec` | — | Terminate FRISTA |
| `/stop_finger_exec` | — | Terminate the fingerprint app |
| `/health` | — | Liveness + whether AutoItX and credentials are ready |

Automation runs on a background thread, so `/run_*` returns immediately with
`{"status": "running", ...}` while the desktop app comes up.

Example:

```bash
curl "http://127.0.0.1:5000/run_exe?no_peserta=0001234567890"
# {"status":"running","target":"frista","no_peserta":"0001234567890"}
```

## Configuration

Copy `config.example.json` to `config.json` (next to the program) and fill it in.
`config.json` holds credentials and is **git-ignored** — never commit it.

```json
{
  "frista_path": "C:\\frista\\frista.exe",
  "finger_path": "C:\\Program Files (x86)\\BPJS Kesehatan\\Aplikasi Sidik Jari BPJS Kesehatan\\After.exe",
  "username": "your-frista-user",
  "password": "your-frista-pass",
  "host": "127.0.0.1",
  "port": 5000
}
```

| Key | Meaning |
|---|---|
| `frista_path` | Path to the FRISTA executable |
| `finger_path` | Path to the fingerprint app (`After.exe`) |
| `username` / `password` | FRISTA login, typed into its login window |
| `host` / `port` | Where the HTTP server listens (default `127.0.0.1:5000`) |

A legacy `config.conf` (`[Config]` with `api` and `camera_id`) is also read if
present, for compatibility with older installs. The `path` / `pathfinger` keys
from older `config.json` files are accepted too.

## Run from source

```bash
pip install -r requirements.txt
python -m dekate_autobiometrik
```

On non-Windows machines the server still starts (handy for development); the
automation endpoints respond but skip the AutoIt steps — `/health` reports
`"autoit": false`.

## Build a standalone .exe

```bash
pip install pyinstaller PyAutoIt
pyinstaller dekate-autobiometrik.spec
```

The single-file `dist/dekate-autobiometrik.exe` needs no Python on the target
machine. Drop `config.json` next to it and run.

## Wiring it into a kiosk

From the kiosk front-end, call the endpoints when the patient chooses a
verification method:

```js
// Face recognition
await fetch(`http://127.0.0.1:5000/run_exe?no_peserta=${encodeURIComponent(noBpjs)}`)

// Fingerprint
await fetch(`http://127.0.0.1:5000/run_finger_exec?no_peserta=${encodeURIComponent(noBpjs)}`)
```

If your kiosk page is served over **HTTPS**, calling `http://127.0.0.1` is
mixed content and browsers may block it. Serve the kiosk over plain HTTP on the
device, or front this service with a locally-trusted certificate.

## Security notes

- Binds to `127.0.0.1` by default — reachable only from the same machine. Only
  change `host` if you understand the exposure.
- Credentials live in `config.json` on the kiosk and are never transmitted by
  this service; the kiosk only ever sends a BPJS number.
- Intended for use on trusted, hospital-controlled kiosk hardware.

## Compatibility

Window titles and control ids target FRISTA 3.0.x and the BPJS fingerprint app
as shipped at release time. If BPJS updates those apps, adjust `FRISTA_UI` /
`FINGER_UI` in [`dekate_autobiometrik/automation.py`](dekate_autobiometrik/automation.py).

## License

MIT © Dekate. See [LICENSE](LICENSE).

Not affiliated with or endorsed by BPJS Kesehatan. "FRISTA" and related app
names are the property of BPJS Kesehatan.
