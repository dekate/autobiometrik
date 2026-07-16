<div align="center">

# AutoBiometrik BPJS by Dekate

[![Latest release](https://img.shields.io/github/v/release/dekate/autobiometrik?label=latest&color=4c1)](https://github.com/dekate/autobiometrik/releases/latest)
[![Installs](https://img.shields.io/github/downloads/dekate/autobiometrik/total?label=installs&color=4c1)](https://github.com/dekate/autobiometrik/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2B-0078d4)](https://github.com/dekate/autobiometrik/releases/latest)
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G4I123ATGC) 
[![Trakteer](https://img.shields.io/badge/Trakteer-Dukung%20Saya-be1e2d?style=for-the-badge)](https://trakteer.id/dekate)

</div>

Service HTTP lokal kecil yang jadi jembatan antara sistem **antrean/kiosk**
rumah sakit (berbasis web) dengan dua aplikasi desktop biometrik BPJS
Kesehatan — **FRISTA** (verifikasi wajah) dan aplikasi **sidik jari**
("After.exe"). Jadi operator tidak perlu lagi buka aplikasinya dan mengetik
manual.

Cara kerjanya: kiosk kirim nomor BPJS pasien ke service ini, lalu service
membuka aplikasi desktop yang sesuai dan mengisi login/registrasinya secara
otomatis. Selesai.

> Dibuat dan di-open-source-kan oleh **[Dekate](https://github.com/dekate)**
> supaya rumah sakit atau vendor mana pun bisa pakai dan modifikasi sesuai
> kebutuhan. Lisensi MIT.

---

## Kenapa perlu service ini?

Aplikasi biometrik BPJS itu aplikasi Windows biasa — browser tidak bisa
mengaksesnya langsung. Service ini yang jadi perantaranya: server
[Flask](https://flask.palletsprojects.com/) kecil yang jalan di PC kiosk dan
menyediakan beberapa endpoint HTTP yang bisa dipanggil dari web kiosk.

```
┌─────────────┐  HTTP GET /start_frista?no_peserta=0001xxxx ┌──────────────────────┐
│  Web kiosk  │ ─────────────────────────────────────────► │  AutoBiometrik BPJS  │
│  (browser)  │                                            │    (service ini)     │
└─────────────┘                                            └──────────┬───────────┘
                                                                      │ buka aplikasi
                                                                      ▼
                                                   FRISTA.exe / After.exe (Finger BPJS)
```

## Endpoint

Semua endpoint pakai method `GET` dan balikannya JSON. CORS-nya terbuka, jadi
halaman kiosk dari origin mana pun bisa memanggilnya.

| Endpoint | Query | Fungsi |
|---|---|---|
| `/start_frista` | `no_peserta` | Buka FRISTA (wajah) dan login pakai kredensial dari config |
| `/start_finger` | `no_peserta` | Buka aplikasi sidik jari, login (kalau kredensialnya diisi), lalu ketikkan nomor BPJS |
| `/stop_frista` | — | Tutup FRISTA |
| `/stop_finger` | — | Tutup aplikasi sidik jari |
| `/health` | — | Cek service hidup + status AutoItX dan kredensial |

Otomasinya jalan di background thread, jadi `/start_*` langsung membalas
`{"status": "running", ...}` tanpa menunggu aplikasinya selesai terbuka.
Kalau parameter `no_peserta` tidak dikirim, endpoint `/start_*` membalas
HTTP 400 dengan `{"status": "error", ...}`.

Contoh:

```bash
curl "http://127.0.0.1:5000/start_frista?no_peserta=0001234567890"
# {"status":"running","target":"frista","no_peserta":"0001234567890"}

curl "http://127.0.0.1:5000/health"
# {"status":"ok","service":"autobiometrik-bpjs","version":"1.0.0",
#  "autoit":true,"has_credentials":true,"has_finger_credentials":true,
#  "scheme":"http"}
```

## Konfigurasi

Copy `config.example.json` jadi `config.json` (taruh di folder yang sama
dengan programnya), lalu isi. `config.json` berisi kredensial dan sudah
masuk **.gitignore** — jangan pernah di-commit.

```json
{
  "frista_path": "C:\\frista\\frista.exe",
  "finger_path": "C:\\Program Files (x86)\\BPJS Kesehatan\\Aplikasi Sidik Jari BPJS Kesehatan\\After.exe",
  "frista_username": "user-frista-anda",
  "frista_password": "password-frista-anda",
  "finger_username": "user-aplikasi-sidik-jari",
  "finger_password": "password-aplikasi-sidik-jari",
  "host": "127.0.0.1",
  "port": 5000,
  "tls_cert": "",
  "tls_key": ""
}
```

| Key | Keterangan |
|---|---|
| `frista_path` | Lokasi file FRISTA (.exe) |
| `finger_path` | Lokasi aplikasi sidik jari (`After.exe`) |
| `frista_username` / `frista_password` | Akun login **FRISTA**, akan diketikkan otomatis ke jendela login-nya |
| `finger_username` / `finger_password` | Akun login **aplikasi sidik jari** (akunnya beda dengan FRISTA). Kalau dikosongkan, langkah login di-skip — aplikasinya dianggap sudah login |
| `host` / `port` | Alamat tempat server HTTP listen (default `127.0.0.1:5000`) |
| `tls_cert` / `tls_key` | Lokasi file sertifikat + private key; kalau dua-duanya diisi, server otomatis jalan pakai HTTPS (lihat bagian HTTPS di bawah) |
| `frista_api` | URL API FRISTA (opsional, default-nya URL resmi BPJS) |
| `camera_id` | ID kamera untuk FRISTA (opsional, default `0`) |

Lokasi file config bisa diganti lewat environment variable `DEKATE_CONFIG`
(isi dengan path lengkap ke file JSON-nya).

File `config.conf` versi lama (section `[Config]` berisi `api` dan
`camera_id`) juga tetap dibaca kalau ada, biar instalasi lama tetap jalan.
Key `path` / `pathfinger` dari `config.json` versi lama juga masih diterima.

## Menjalankan dari source

```bash
pip install -r requirements.txt
python -m autobiometrik
```

Di mesin selain Windows, server tetap bisa jalan (enak buat development);
endpoint otomasinya tetap membalas tapi langkah AutoIt-nya di-skip —
`/health` akan menampilkan `"autoit": false`.

## Build jadi .exe

```bash
pip install pyinstaller PyAutoIt
pyinstaller autobiometrik-bpjs.spec
```

Hasilnya satu file `dist/autobiometrik-bpjs.exe` yang tidak butuh Python di
mesin tujuan. Tinggal taruh `config.json` di sebelahnya, lalu jalankan.

## Menyambungkan ke kiosk

Dari front-end kiosk, panggil endpoint-nya saat pasien memilih metode
verifikasi:

```js
const BRIDGE = 'http://127.0.0.1:5000' // atau URL HTTPS kamu — lihat di bawah

// Verifikasi wajah
await fetch(`${BRIDGE}/start_frista?no_peserta=${encodeURIComponent(noBpjs)}`)

// Sidik jari
await fetch(`${BRIDGE}/start_finger?no_peserta=${encodeURIComponent(noBpjs)}`)
```

## Kalau web kiosk-nya pakai HTTPS

Kalau web kiosk kamu diakses lewat **HTTPS** (kebanyakan begitu), memanggil
`http://127.0.0.1` biasa bisa bermasalah:

- Secara *teknis* panggilan ke loopback memang bebas dari blokir
  mixed-content (loopback dianggap origin yang "potentially trustworthy"),
  **tapi**
- Chrome 142 ke atas memunculkan popup izin **Local Network Access** saat
  halaman HTTPS publik pertama kali mengakses loopback, dan perilakunya
  beda-beda tiap browser/versi.

Solusi yang paling aman: jalankan **service ini pakai HTTPS juga**, jadi
komunikasinya secure→secure. Cukup isi `tls_cert` dan `tls_key` di
`config.json`, server langsung jalan pakai HTTPS. Tinggal satu masalah:
bagaimana dapat sertifikat yang *dipercaya* browser — pilih salah satu:

### Opsi A — Sertifikat publik di domain loopback (tanpa setting per kiosk)

Ini cara yang dipakai aplikasi desktop seperti Plex dan Discord. Setting
sekali saja, tidak ada yang perlu diinstal di tiap kiosk.

1. Siapkan sebuah domain, misalnya `dekate.id`. Arahkan satu subdomain ke
   loopback: `local.dekate.id  A  127.0.0.1`
2. Buat sertifikat asli untuk domain itu lewat Let's Encrypt pakai challenge
   **DNS-01** (host-nya tidak bisa diakses dari internet, jadi HTTP-01 tidak
   akan bisa):
   ```bash
   certbot certonly --manual --preferred-challenges dns -d local.dekate.id
   ```
3. Sertakan `fullchain.pem` / `privkey.pem` bersama service ini, lalu
   arahkan `tls_cert` / `tls_key` ke file tersebut.
4. Kiosk memanggil `https://local.dekate.id:5000/...`.

Semua browser percaya sertifikatnya (dari CA publik), dan trafiknya tidak
pernah keluar dari mesin (DNS-nya mengarah ke 127.0.0.1). Perlu diperpanjang
tiap ~90 hari. Catatan: private key-nya ikut terbagikan bersama aplikasi;
karena domainnya cuma mengarah ke loopback, risikonya kecil, tapi tetap
anggap saja key itu bukan rahasia.

### Opsi B — CA lokal per kiosk pakai mkcert (full offline)

Tanpa domain, tanpa internet. Cukup satu perintah per kiosk waktu instalasi.

```bash
# di tiap kiosk, sekali saja:
mkcert -install                       # pasang CA lokal di OS/browser
mkcert 127.0.0.1 localhost            # bikin sertifikat + key untuk loopback
```

Arahkan `tls_cert` / `tls_key` ke file yang dihasilkan. Kiosk memanggil
`https://127.0.0.1:5000/...`. Tidak ada data yang keluar dari mesin, dan
tidak ada private key yang perlu dibagikan ke mana-mana.

> Apa pun pilihannya, kiosk tetap cuma mengirim nomor BPJS; kredensial tidak
> pernah lewat jaringan.

## Catatan keamanan

- Default-nya cuma listen di `127.0.0.1` — hanya bisa diakses dari mesin itu
  sendiri. Jangan ganti `host` kecuali kamu paham risikonya.
- Kredensial tersimpan di `config.json` di kiosk dan tidak pernah dikirim
  ke mana pun oleh service ini; kiosk cuma mengirim nomor BPJS.
- Dirancang untuk dipakai di perangkat kiosk yang dikelola rumah sakit.

Nemu celah keamanan? Jangan buka issue publik — laporkan lewat tab **Security**
repo ini. Detailnya ada di [SECURITY.md](.github/SECURITY.md).

## Testing

```bash
pip install pytest
pytest
```

Test-nya tidak butuh Windows ataupun aplikasi BPJS — bagian AutoIt-nya
di-mock, jadi bisa dijalankan di mesin development mana saja.

## Kompatibilitas

Judul window dan control id-nya menyesuaikan FRISTA 3.0.x dan aplikasi sidik
jari BPJS versi saat rilis. Kalau BPJS meng-update aplikasinya, sesuaikan
`FRISTA_UI` / `FINGER_UI` di
[`autobiometrik/automation.py`](autobiometrik/automation.py).

## Lisensi

MIT © Dekate. Lihat [LICENSE](LICENSE).

Tidak berafiliasi dengan dan tidak didukung oleh BPJS Kesehatan. "FRISTA"
dan nama-nama aplikasi terkait adalah milik BPJS Kesehatan.
