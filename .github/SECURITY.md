# Kebijakan Keamanan

## Melaporkan kerentanan

**Tolong jangan buka issue publik untuk masalah keamanan.**

Laporkan secara privat lewat [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
milik GitHub: buka tab **Security** di repo ini, lalu klik **Report a
vulnerability**. Laporannya jadi advisory privat yang cuma bisa dilihat
maintainer.

Sertakan:

- Masalahnya apa dan dampak yang kamu perkirakan.
- Langkah reproduksinya (proof of concept sangat membantu).
- Komponen yang kena: server HTTP (`autobiometrik/app.py`), lapisan otomasi
  AutoIt (`autobiometrik/automation.py`), pembacaan konfigurasi
  (`autobiometrik/config.py`), atau pipeline rilis
  (`.github/workflows/release.yml`).

Kami usahakan membalas dalam beberapa hari dan mengabari perkembangannya selama
perbaikan dikerjakan. Tolong beri waktu yang wajar untuk merilis perbaikan
sebelum masalahnya dipublikasikan.

## Cakupan

Masuk cakupan:

- Server HTTP Flask (`autobiometrik/`) — endpoint, penanganan parameter, CORS,
  dan TLS.
- Lapisan otomasi AutoIt (`autobiometrik/automation.py`) — cara kredensial dan
  nomor BPJS diketikkan ke jendela aplikasi desktop.
- Pembacaan dan penyimpanan konfigurasi (`autobiometrik/config.py`), termasuk
  kalau ada kredensial yang bocor ke log atau ke response HTTP.
- Build PyInstaller (`autobiometrik-bpjs.spec`) dan `.exe` yang dihasilkannya.
- Pipeline rilis (`.github/workflows/release.yml`) — apa pun yang bisa membuat
  build merilis kode yang tidak ada di commit yang di-tag, atau membocorkan
  isi secret.

Di luar cakupan:

- **FRISTA dan aplikasi sidik jari BPJS itu sendiri.** Proyek ini tidak
  berafiliasi dengan BPJS Kesehatan — kami cuma mengotomasi jendelanya dari
  luar. Masalah di aplikasinya laporkan ke BPJS Kesehatan.
- **API BPJS.** Service ini tidak memanggilnya; `frista_api` cuma diteruskan ke
  FRISTA sebagai konfigurasi.
- Server yang sengaja di-bind ke host non-loopback. Default-nya `127.0.0.1`;
  mengganti `host` supaya bisa diakses dari jaringan berarti kamu memaparkan
  endpoint tanpa autentikasi ke jaringan — itu keputusan operator, bukan bug
  (lihat bagian di bawah).
- Advisory dependency tanpa bukti eksploitasi nyata di proyek ini.
- Temuan yang butuh mesin yang sudah dikuasai penyerang atau akses fisik ke
  kiosk.

## Apa yang service ini lakukan (biar kamu bisa menilai risikonya)

Service ini menjalankan server Flask kecil di mesin kiosk, lalu menyetir
aplikasi desktop BPJS dari luar lewat AutoItX: fokus ke jendelanya, ketik
kredensial dan nomor BPJS, tekan tombol. Aplikasi BPJS diperlakukan sebagai
kotak hitam — service ini **tidak** membaca/menulis memori prosesnya, tidak
memodifikasi file aplikasinya, dan tidak menyuntikkan kode. Yang dilakukan cuma
menjalankan aplikasinya, mengirim keystroke, dan mematikan prosesnya
(berdasarkan nama image `frista.exe` / `After.exe`) lewat endpoint `/stop_*`.

Dua properti desain yang perlu kamu tahu — dua-duanya disengaja, bukan bug:

- **Endpoint-nya tidak pakai autentikasi.** Apa pun yang bisa menjangkau
  port-nya bisa membuka, me-login-kan, atau menutup aplikasi BPJS. Pengamannya
  ada di binding default `127.0.0.1`: hanya bisa diakses dari mesin kiosk itu
  sendiri.
- **CORS-nya terbuka penuh.** Halaman kiosk dari origin mana pun bisa
  memanggilnya — memang itu tujuannya, karena web kiosk-nya beda origin. Efek
  sampingnya: halaman web lain yang kebetulan dibuka di browser mesin yang sama
  juga bisa memanggil endpoint-nya. Service ini dirancang untuk kiosk yang
  dikelola rumah sakit dan browser-nya terkunci.

`.exe` rilisnya **tidak ditandatangani** (`codesign_identity=None` di spec-nya),
jadi Windows SmartScreen kemungkinan memunculkan peringatan waktu pertama kali
dijalankan. Itu hal yang diharapkan, bukan kerentanan.

## Dari mana `.exe` rilisnya datang

Satu-satunya kanal distribusi resmi adalah [halaman
Releases](https://github.com/dekate/autobiometrik/releases) repo ini. Binary-nya
di-build oleh GitHub Actions (`.github/workflows/release.yml`) di runner
`windows-latest`, dipicu oleh tag `v*`, langsung dari commit yang di-tag —
tidak pernah di-upload manual dari mesin siapa pun. Sebelum build jalan,
pipeline-nya memastikan tag-nya cocok dengan `__version__` dan seluruh test
harus lulus.

Karena binary-nya tidak ditandatangani, tidak ada cara kriptografis untuk
memverifikasi asalnya. Ambil `.exe`-nya dari halaman Releases itu saja — jangan
dari mirror atau kiriman pihak ketiga.

## Penanganan kredensial

Tidak ada kredensial yang di-commit ke repo ini. `config.json` dan `config.conf`
masuk **.gitignore**; yang ada di repo cuma `config.example.json` berisi
placeholder — dan itu juga yang ikut dirilis, jadi rilisnya tidak pernah membawa
kredensial siapa pun.

Pipeline rilisnya tidak butuh secret khusus: dia cuma pakai `GITHUB_TOKEN`
bawaan GitHub Actions, dibatasi ke `contents: write` supaya bisa membuat
Release — tidak ada token pihak ketiga, tidak ada sertifikat signing.

Kredensial FRISTA dan aplikasi sidik jari tersimpan di `config.json` di mesin
kiosk dan tidak pernah dikirim ke mana pun lewat jaringan oleh service ini —
kredensial itu hanya diketikkan ke jendela login aplikasi desktop di mesin yang
sama. Kiosk cuma mengirim nomor BPJS.

Yang perlu diperhatikan operator:

- `config.json` disimpan sebagai **plaintext**. Amankan lewat permission file
  dan akses mesin kiosknya.
- `/health` membocorkan *apakah* kredensial sudah diisi (`has_credentials`,
  `has_finger_credentials`) — tapi tidak pernah nilainya.
- Log rotasi (`autobiometrik/paths.py`) mencatat nomor BPJS pasien yang
  diproses, tapi tidak pernah mencatat username maupun password. Perlakukan file
  log itu sebagai data pasien.
