# AUTO CLIP

Ubah video panjang (YouTube / file lokal) menjadi **klip pendek vertikal 9:16 (1080x1920)**
dengan subtitle Bahasa Indonesia yang sudah **terbakar** ke dalam video.

Alurnya: unduh video → transkripsi per kata (faster-whisper) → pilih segmen terbaik
(OpenRouter model gratis) → potong + crop 9:16 (FFmpeg) → subtitle `.ass`/`.srt`.

Semua tool **gratis & open source**. Tidak ada API berbayar, tidak butuh GPU.

---

## 1. Yang Dibutuhkan

| Kebutuhan | Keterangan |
|---|---|
| Python 3.10+ | Telah diuji di 3.12 |
| FFmpeg + FFprobe | Wajib. `sudo apt install ffmpeg` (Linux) / `brew install ffmpeg` (Mac) |
| Koneksi internet | Untuk mengunduh model Whisper saat pertama jalan dan memanggil OpenRouter |
| RAM | ±2 GB cukup untuk model `small`. GPU opsional (otomatis dipakai bila ada) |

Cek FFmpeg lebih dulu:

```bash
ffmpeg -version && ffprobe -version
```

---

## 2. Install

```bash
cd /home/qwerty/clip

# buat virtual environment (sudah ada lewat venv/ di repo ini)
python3 -m venv venv

# install dependency (~2 menit, mengunduh model Whisper saat pertama jalan)
venv/bin/pip install -r requirements.txt
```

---

## 3. Isi `.env` (WAJIB)

```bash
cp .env.example .env
nano .env
```

Isi **dua baris** ini:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
OPENROUTER_MODEL=google/gemini-2.0-flash-exp:free
```

| Variabel | Isi |
|---|---|
| `OPENROUTER_API_KEY` | Ambil di <https://openrouter.ai/keys> (gratis, cukup daftar) |
| `OPENROUTER_MODEL` | **Harus berakhiran `:free`.** Daftar model gratis: <https://openrouter.ai/models?max_price=0> |

Sisanya boleh dibiarkan sesuai `.env.example`:

| Variabel | Default | Arti |
|---|---|---|
| `WHISPER_MODEL` | `small` | `tiny`/`base` lebih cepat, `medium` lebih akurat (lebih berat) |
| `WHISPER_DEVICE` | `auto` | `auto`/`cuda`/`cpu` |
| `WHISPER_COMPUTE_TYPE` | `auto` | otomatis `int8` (CPU) atau `float16` (GPU) |
| `CLIP_MIN_SECONDS` | `30` | durasi minimum klip |
| `CLIP_MAX_SECONDS` | `60` | durasi maksimum klip |
| `MAX_CLIPS` | `5` | jumlah klip maksimal per video |
| `LANGUAGE` | `id` | kode bahasa, atau `auto` |
| `FACE_TRACKING` | `false` | `true` = crop mengikuti wajah, `false` = crop tengah |

> ⚠️ **Program menolak jalan** kalau `OPENROUTER_API_KEY`/`OPENROUTER_MODEL` masih
> placeholder, atau kalau `OPENROUTER_MODEL` tidak berakhiran `:free`. Ini disengaja agar
> kuota berbayar tidak terpakai tanpa disadari.

---

## 4. Jalankan

```bash
# dari URL (YouTube, Vimeo, Twitter/X, dll — pakai yt-dlp)
venv/bin/python main.py --input https://www.youtube.com/watch?v=VIDEO_ID

# dari file lokal (taruh di folder input/ atau path absolut)
venv/bin/python main.py --input input/vidio-saya.mp4
```

Contoh lengkap:

```bash
venv/bin/python main.py \
  --input https://www.youtube.com/watch?v=VIDEO_ID \
  --max-clips 3 \
  --min-seconds 30 \
  --max-seconds 60 \
  --language id \
  --face-tracking \
  --keep-temp \
  --verbose
```

### Opsi CLI

| Opsi | Fungsi |
|---|---|
| `--input`, `-i` | URL atau path file (wajib) |
| `--max-clips N` | override `MAX_CLIPS` |
| `--min-seconds N` / `--max-seconds N` | override durasi klip |
| `--language KODE` | override `LANGUAGE`, mis. `id`, `en`, `auto` |
| `--face-tracking` | paksa crop mengikuti wajah |
| `--no-face-tracking` | paksa crop tengah |
| `--reuse-transcript` | pakai `temp/transcript.json`, **lewati transkripsi** (hemat waktu) |
| `--keep-temp` | jangan bersihkan `temp/` setelah selesai |
| `--env PATH` | pakai file `.env` lain (dipakai pengujian) |
| `--verbose`, `-v` | tampilkan konfigurasi (API key dimasker) |

---

## 5. Hasil di `output/`

Setiap klip menghasilkan tiga file:

```
output/
├── 01_judulvideo_klip1_hook-nya.mp4      <- klip 9:16 + subtitle terbakar
├── 01_judulvideo_klip1_hook-nya.srt      <- subtitle editable (SRT)
└── 01_judulvideo_klip1_hook-nya.ass      <- subtitle yang dipakai untuk bake
```

Nama file memuat nomor urut, judul video, dan judul klip. Gaya subtitle: **maksimal 2 baris,
tebal, putih, di bagian tengah-bawah**.

---

## 6. Kalau ada masalah

Program berhenti dengan kode berikut:

| Kode | Arti | Yang harus dilakukan |
|---|---|---|
| `0` | Sukses | — |
| `2` | `.env` belum lengkap / model bukan `:free` | Perbaiki `.env` sesuai pesan error |
| `3` | FFmpeg tidak ditemukan | Pasang FFmpeg, pastikan ada di PATH |
| `4` | Gagal unduh video atau transkripsi | Cek koneksi; coba file lokal |
| `5` | Gagal pilih segmen dari OpenRouter | usually rate limit → tunggu, atau ganti model `:free`. Masalahnya **dicatat otomatis di `problem.md`** |
| `6` | Gagal memotong klip / membuat subtitle | Cek pesan error |

Pesan yang sering muncul:

- **HTTP 429 dari OpenRouter** → kuota model gratis habis (lihat bagian 7). Program sudah
  mencoba retry otomatis dengan jedaincreasing.
- **`Transkripsi kosong`** → audio sunyi, format rusak, atau `LANGUAGE` salah. Coba `--language auto`.
- **Wajah tidak terdeteksi** → otomatis fallback ke crop tengah. Haar cascade hanya
  detección wajah depan; untuk video multi-wajah perlu detector lain.

> Kalau keluar kode `5`, program menuliskan detail masalahnya ke `problem.md` secara
> otomatis. Buka file itu untuk melihat penyebabnya.

---

## 7. Soal biaya (bukan 100% tanpa batas)

Semua tool gratis, tapi **kuota model gratis OpenRouter terbatas**:

| Syarat | Batas request `:free` |
|---|---|
| Belum pernah membeli kredit di OpenRouter | 20/menit · **50/hari** |
| Pernah membeli kredit ≥ $10 (sekali, seumur akun) | 20/menit · 1000/hari |

Karena AUTO CLIP hanya memakai **1 request per video** (maksimal 3 bila retry), kuota 50/hari
cukup untuk ±50 video per hari. Reset pukul 00:00 UTC (07:00 WIB).

Hal lain yang perlu diketahui:

- Daftar model `:free` **berubah-ubah**; kalau modelmu hilang, ganti satu baris di `.env`.
- Kalau saldo akunmu negatif, model gratis pun ditolak (HTTP 402).
- Tanpa GPU, transkripsi cukup lambat: ±72 detik audio ≈ 4 menit di CPU 8-core.
  Video 1 jam bisa makan 50+ menit. Pakai `--reuse-transcript` untuk_iterasi cepat.

---

## 8. Pengujian

```bash
# uji modul highlight vs mock OpenRouter lokal (7 skenario, tanpa API key)
venv/bin/python tests/test_highlight.py

# buat video uji 1-3 menit dengan suara Indonesia (butuh edge-tts)
venv/bin/pip install edge-tts
venv/bin/python make_test_video.py

# alur penuh tanpa API key sungguhan (mock)
venv/bin/python tests/mock_openrouter.py --port 8792 --scenario good &
venv/bin/python main.py --input input/testvideo_id.mp4 --env tests/.env.test
```

Skenario mock yang tersedia: `good`, `fenced`, `trailing`, `truncated`, `dictwrap`,
`garbage`, `ratelimit`.

---

## 9. Struktur proyek

```
autoclip/
├── main.py                 entry point CLI
├── autoclip_colab.py       pembungkus sekali jalan untuk Google Colab
├── src/
│   ├── config.py           baca .env + validasi (blokir model non-:free)
│   ├── downloader.py       yt-dlp / file lokal + ekstrak audio
│   ├── transcriber.py      faster-whisper, timestamp per kata
│   ├── highlight.py        pilih segmen via OpenRouter (retry + bersihkan JSON)
│   ├── clipper.py          FFmpeg potong + crop 9:16 (+ face tracking)
│   └── subtitles.py        buat .ass/.srt lalu bake ke video
├── assets/                 Haar cascade untuk face tracking
├── tests/                  mock OpenRouter + uji modul
├── input/                  taruh video sumber di sini
├── temp/                   file sementara (transkrip, audio)
└── output/                 HASIL AKHIR
```

Jurnal pengembangan: `AGENTS.md` (aturan kerja), `problem.md` (12 masalah + status),
`fix.md` (12 perbaikan + hasil uji).

---

## 10. Di Google Colab

Gunakan `autoclip_colab.py`: satu file yang mengurus install FFmpeg + dependency,
membaca API key dari **Colab Secrets**, menyiapkan GPU, menjalankan pipeline, lalu
menyalin hasil ke Drive dan mengunduhnya sebagai zip.

### 10.0 Upload ke GitHub lalu dipanggil dari Colab

`.gitignore` sudah mengecualikan `.env`, `venv/`, `output/`, `temp/`, dan media di
`input/`, jadi aman untuk di-push (repo hanya ±1,1 MB, hampir semuanya Haar cascade):

```bash
cd /home/qwerty/clip
git init -b main
git add -A
git commit -m "AUTO CLIP"
git remote add origin https://github.com/USER/autoclip.git
git push -u origin main
```

Lalu di Colab ada **dua cara**, pilih salah satu:

```python
# CARA 1 (paling ringkas): skrip meng-clone sendiri ke /content/autoclip
!python autoclip_colab.py --repo https://github.com/USER/autoclip.git \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free
```

```python
# CARA 2: clone manual dulu, lalu jalankan skrip dari dalam repo
!git clone https://github.com/USER/autoclip.git
!python autoclip/autoclip_colab.py \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free
```

Yang perlu disiapkan sekali di Colab: aktifkan **Runtime → Change runtime type → GPU**,
dan simpan API key sebagai **Colab Secret** bernama `OPENROUTER_API_KEY`
(**Runtime → Manage secrets**). Kalau repo sudah ada (mis. run kedua), `--repo` dipakai
ulang tanpa clone lagi.

### 10.1 Persiapan sekali jalan

Di Colab, aktifkan **Runtime → Change runtime type → GPU** (T4 gratis sudah cukup).

Cell pertama — clone repo lalu simpan API key sebagai Colab Secret
(**Runtime → Manage secrets → New secret**, nama: `OPENROUTER_API_KEY`):

```python
!git clone https://github.com/USER/autoclip.git /content/autoclip
```

### 10.2 Jalankan

```python
# dari URL YouTube
!python /content/autoclip/autoclip_colab.py \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free
```

```python
# dari file di Google Drive + hasil disimpan ke Drive
from google.colab import drive
drive.mount('/content/drive')

!python /content/autoclip/autoclip_colab.py \
    --input "/content/drive/MyDrive/videos/videosaya.mp4" \
    --model google/gemini-2.0-flash-exp:free \
    --drive-dir "/content/drive/MyDrive/autoclip"
```

Kalau repo belum ada di Colab, beri `--repo https://github.com/USER/autoclip.git`
agar file ini sekaligus meng-clone-nya.

### 10.3 Opsi `autoclip_colab.py`

| Opsi | Fungsi |
|---|---|
| `--input`, `-i` | URL video atau path file (wajib untuk menjalankan pipeline) |
| `--repo URL` | clone repo AUTO CLIP kalau belum ada di disk (path lokal juga boleh) |
| `--model NAMA` | model OpenRouter gratis, **wajib berakhiran `:free`** |
| `--api-key KEY` | API key langsung (lebih aman pakai Colab Secrets) |
| `--env-file PATH` | pakai file `.env` tertentu |
| `--whisper-model` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `--cpu` / `--face-tracking` / `--no-face-tracking` | paksa CPU / crop ikut wajah / crop tengah |
| `--drive-dir PATH` | salin hasil ke folder Google Drive, mis. `/content/drive/MyDrive/autoclip` |
| `--skip-install` | lewati `apt-get` + `pip install` (iterasi cepat) |
| `--no-download` | jangan zip/unduh hasil |
| `--check-env` | periksa lingkungan lalu keluar (tanpa memanggil LLM) |
| `--no-prompt` | tanpa interaksi: hanya Colab Secrets / environment / argumen |
| `-- <args>` | argumen tambahan untuk `main.py`, mis. `-- --max-clips 3 --keep-temp` |

Contoh performant (percobaan kedua, hemat waktu & kuota LLM):

```python
!python /content/autoclip/autoclip_colab.py \
    -i "https://www.youtube.com/watch?v=VIDEO_ID" \
    --no-download -- --reuse-transcript --max-clips 3
```

### 10.4 Yang otomatis ditangani

- `apt-get install ffmpeg fonts-dejavu-core` (FFmpeg + font untuk subtitle, tanpa `sudo`).
- `pip install -r requirements.txt` memakai python runtime Colab (bukan `venv/`).
- Pustaka CUDA 12 (`cuBLAS`/`cuDNN 9`) + `LD_LIBRARY_PATH` supaya faster-whisper
  jalan di GPU; kalau GPU tidak bisa dipakai, otomatis turun ke CPU (`int8`).
- `.env` dibuat otomatis dari Colab Secrets; model tanpa `:free` **ditolak keras**.
- If transkripsi di GPU gagal, pipeline diulang sekali di CPU, lalu `.env` dikembalikan.
- `--repo`: `git clone --depth 1` dari URL GitHub (`https://…`, `git@…`, `ssh://…`) ke
  `/content/autoclip`; URL ber-`.git` tidak diubah lagi, dan repo yang sudah ada tidak
  di-clone ulang.
- Hasil: ringkasan + zip `autoclip_output_<timestamp>.zip` yang diunduh ke browser.

> ⚠️ Runtime Colab bersifat sementara: file `/content` hilang saat runtime berhenti.
> Unduh zip hasil (atau pakai `--drive-dir`) **sebelum** menutup tab.