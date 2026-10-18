# AUTO CLIP

Masukkan satu video panjang (YouTube atau file lokal), dapat beberapa **klip vertikal
9:16 (1080x1920) bersubtitle** — subtitle sudah tertanam di dalam videonya.

Semua gratis & open source, jalan di laptop tanpa GPU.

Cara kerjanya: unduh video → transkrip per kata (Whisper) → pilih momen terbaik
(OpenRouter, model gratis) → potong & ubah ke 9:16 (FFmpeg) → tulis subtitle.

---

## Cara Pakai (lokal)

### Langkah 1 — Pastikan FFmpeg ada

```bash
ffmpeg -version && ffprobe -version
```

Belum ada? `sudo apt install ffmpeg` (Linux) atau `brew install ffmpeg` (Mac).

### Langkah 2 — Install

```bash
cd /home/qwerty/clip
venv/bin/pip install -r requirements.txt
```

### Langkah 3 — Isi `.env`

```bash
cp .env.example .env
nano .env
```

Cukup isi dua baris ini:

```dotenv
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
OPENROUTER_MODEL=google/gemini-2.0-flash-exp:free
```

- API key gratis: <https://openrouter.ai/keys>
- Nama model **wajib berakhiran `:free`**: <https://openrouter.ai/models?max_price=0>

Kalau masih placeholder atau modelnya bukan `:free`, program berhenti dengan pesan error.
Itu disengaja supaya kuota berbayar tidak kepakai tanpa disadari.

Sisanya biarkan default dari `.env.example` (sudah cocok untuk kebanyakan kasus):

| Variabel | Default | Kapan diubah |
|---|---|---|
| `WHISPER_MODEL` | `small` | `tiny`/`base` lebih cepat, `medium` lebih akurat |
| `CLIP_MIN_SECONDS` / `CLIP_MAX_SECONDS` | `30` / `60` | mau klip lebih pendek atau lebih panjang |
| `MAX_CLIPS` | `5` | mau lebih banyak atau lebih sedikit klip per video |
| `LANGUAGE` | `id` | video berbahasa lain (`en`, atau `auto`) |
| `FACE_TRACKING` | `false` | `true` = crop ikut wajah, `false` = crop tengah |
| `MAX_SOURCE_HEIGHT` | `1080` | turunkan ke `720` supaya unduhan jauh lebih cepat |
| `DOWNLOAD_PROGRESS_SECONDS` | `15` | jarak antar baris progress unduhan; `0` = hanya tiap 10% |
| `YT_COOKIES_FILE` | (kosong) | isi `cookies.txt` hanya kalau YouTube meminta verifikasi bot |

### Langkah 4 — Jalankan

```bash
# dari YouTube / URL lain (pakai yt-dlp)
venv/bin/python main.py --input https://www.youtube.com/watch?v=VIDEO_ID

# dari file lokal (taruh dulu di folder input/, atau tulis path absolut)
venv/bin/python main.py --input input/vidio-saya.mp4
```

Tunggu prosesnya (transkripsi di CPU paling lama bagiannya), lalu buka folder
`output/`. Hasilnya:

```
output/
├── 01_judulvideo_klip1_hook-nya.mp4   <- klip 9:16 + subtitle terbakar
├── 01_judulvideo_klip1_hook-nya.srt   <- subtitle editable
└── 01_judulvideo_klip1_hook-nya.ass   <- subtitle yang dipakai untuk bake
```

---

## Opsi yang Sering Dipakai

| Opsi | Fungsi |
|---|---|
| `--input`, `-i` | URL atau path file (wajib) |
| `--max-clips N` | jumlah klip per video |
| `--min-seconds N` / `--max-seconds N` | durasi klip |
| `--language KODE` | `id`, `en`, atau `auto` |
| `--face-tracking` / `--no-face-tracking` | crop ikut wajah / crop tengah |
| `--reuse-transcript` | pakai `temp/transcript.json`, lewati transkripsi (hemat waktu) |
| `--progress-seconds N` | jarak antar baris progress unduhan (default 15 detik, `0` = hanya tiap 10%) |
| `--cookies PATH` | kirim `cookies.txt` ke yt-dlp (hanya perlu kalau YouTube minta verifikasi bot) |
| `--keep-temp` | jangan bersihkan `temp/` |
| `--verbose` | tampilkan konfigurasi (API key dimasker) |

Contoh: 3 klip, 30–45 detik, tanpa mengulang transkripsi yang sudah ada.

```bash
venv/bin/python main.py \
  --input https://www.youtube.com/watch?v=VIDEO_ID \
  --max-clips 3 \
  --min-seconds 30 \
  --max-seconds 45 \
  --reuse-transcript \
  --verbose
```

---

## Tips Biar Cepat

- **Pakai `--reuse-transcript`** kalau mau coba-coba hasil tanpa mengulang transkripsi
  (butuh `temp/transcript.json` dari percobaan sebelumnya, sebelumnya pakai `--keep-temp`).
- **Turunkan `MAX_SOURCE_HEIGHT=720`** kalau unduhannya terasa lama. Hasil akhir tetap
  1080x1920, cuma jauh lebih ringan.
- **Video pendek dulu** (1–3 menit) untuk mencoba; kalau cocok baru proses video panjang.
- Tanpa GPU, transkripsi ~4 menit untuk audio 1 menit. Video 1 jam bisa makan 50+ menit,
  jadi pakai Colab gratis (lihat bagian Colab) atau `--reuse-transcript`.

---

## Kalau Ada Masalah

| Gejala | Yang harus dilakukan |
|---|---|
| Unduhan lama "macet" | Bukan macet — cek file `.part` di `temp/`, unduhan sedang jalan |
| Progress unduhan terlalu jarang/terlalu sering | atur `DOWNLOAD_PROGRESS_SECONDS` di `.env` atau pakai `--progress-seconds N` |
| `HTTP 403` dari YouTube | IP diblokir; pakai file lokal, atau `venv/bin/pip install -U yt-dlp`, atau coba lagi nanti |
| `Sign in to confirm you're not a bot` | Reputasi IP sedang ditandai, bukan bug program. Program sudah mencoba ulang dengan player client tanpa login. Kalau tetap ditolak: pakai file lokal (`input/`), kirim cookie (`--cookies cookies.txt`), tunggu beberapa jam, atau ganti jaringan. Lihat [P-016](problem.md) |
| `HTTP 429` dari OpenRouter | Kuota model gratis habis; tunggu, ganti model `:free`, atau pakai akun yang pernah beli kredit |
| `libcublas.so.12 is not found` | GPU tidak bisa dipakai. Otomatis turun ke CPU; kalau `WHISPER_DEVICE=cuda` dipaksa, ubah ke `cpu` + `int8`, atau jalankan lewat `autoclip_colab.py` |
| `[colab] GPU ada tapi ctranslate2 tidak bisa memakainya -> fallback ke CPU` | Angka `[transcribe] device=cpu` muncul, padahal Colab punya GPU. Cek penyebabnya dengan `!python autoclip_colab.py --check-env` (baris `CUDA :` + daftar pustaka) — biasanya perlu `pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"` lalu restart runtime. Lihat [P-019](problem.md) |
| `Transkripsi kosong` | Coba `--language auto` |
| Wajah tidak terdeteksi | Otomatis fallback ke crop tengah, jadi aman |

Kalau program berhenti dengan pesan error, detail masalahnya otomatis ditulis ke
`problem.md` — buka file itu untuk tahu penyebabnya. Kode keluarannya: `0` sukses,
`2` `.env` belum benar, `3` FFmpeg tidak ada, `4` gagal unduh/transkripsi,
`5` gagal pilih segmen, `6` gagal potong/subtitle.

---

## Cara Pakai di Google Colab (GPU gratis)

Kalau laptopnya berat, jalankan di Colab: runtime GPU T4 gratis jauh lebih cepat
untuk transkripsi. Repo ini harus sudah ada di GitHub (`.env`, `venv/`, `output/`
sudah masuk `.gitignore`, jadi aman untuk di-push).

Sekali saja di Colab:

1. **Runtime → Change runtime type → GPU**.
2. **Runtime → Manage secrets → New secret**, nama `OPENROUTER_API_KEY`, isi API key.
3. Clone repo lalu jalankan:

```python
!git clone https://github.com/USER/autoclip.git /content/autoclip

!python /content/autoclip/autoclip_colab.py \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free
```

`autoclip_colab.py` mengurus semuanya: install FFmpeg + dependency, siapkan CUDA,
baca API key dari Secrets, pilih segmen, lalu meng-*zip* hasil untuk diunduh.

Hasil dari file di Google Drive:

```python
from google.colab import drive
drive.mount('/content/drive')

!python /content/autoclip/autoclip_colab.py \
    --input "/content/drive/MyDrive/videos/videosaya.mp4" \
    --model google/gemini-2.0-flash-exp:free \
    --drive-dir "/content/drive/MyDrive/autoclip"
```

Opsi Colab yang berguna:

| Opsi | Fungsi |
|---|---|
| `--repo URL` | clone repo kalau belum ada (path lokal juga boleh) |
| `--model NAMA` | model OpenRouter gratis, **wajib berakhiran `:free`** |
| `--drive-dir PATH` | simpan hasil ke Google Drive |
| `--skip-install` | lewati install (percobaan kedua dst.) |
| `--no-download` | jangan zip/unduh hasil |
| `-- <args>` | teruskan argumen ke `main.py`, mis. `-- --max-clips 3 --keep-temp` |

### Kalau YouTube minta verifikasi bot di Colab

Pesan `Sign in to confirm you're not a bot` artinya IP Colab sedang ditandai, bukan
program yang rusak. Program sudah mencoba ulang dengan player client tanpa login.
Kalau tetap ditolak, urutannya:

1. Pakai file lokal: unduh videonya di browser, unggah ke `/content/drive`, lalu
   `--input /content/drive/MyDrive/videos/nama.mp4`.
2. Kirim cookie (opsional, perlu akun YouTube): export `cookies.txt` di laptop
   (extension browser "Get cookies.txt LOCALLY"), unggah ke `/content/cookies.txt`,
   lalu teruskan lewat `-- --cookies /content/cookies.txt`.
3. Restart runtime (dapat IP baru) atau tunggu beberapa jam. Mengulang video yang
   sama hanya memperburuk reputasi IP.

Lihat [P-016](problem.md).

Contoh paling ringkas (repo di-clone sendiri oleh skrip, ini cara pertama
dipakai di Colab):

```python
!python autoclip_colab.py --repo https://github.com/USER/autoclip.git \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free
```

> ⚠️ File `/content` di Colab hilang saat runtime berhenti. Unduh zip hasilnya
> (atau pakai `--drive-dir`) sebelum menutup tab.

---

## Kalau Ingin Coba Tanpa Video Sendiri

```bash
# buat video uji 1-3 menit dengan suara Indonesia
venv/bin/pip install edge-tts
venv/bin/python make_test_video.py
```

Lihat juga `AGENTS.md` (aturan kerja proyek), `problem.md`, dan `fix.md` kalau
ingin tahu riwayat masalah yang pernah ditangani.