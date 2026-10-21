# CARA PAKAI — AUTO CLIP (resep perintah siap pakai)

Semua perintah di bawah bisa langsung disalin. Ganti `VIDEO_ID` / `namafile.mp4`
sesuai kebutuhan.

---

## 0. Persiapan sekali saja (lokal)

```bash
cd /home/qwerty/clip
venv/bin/pip install -r requirements.txt        # dependency
cp .env.example .env                            # buat file konfigurasi
nano .env                                       # isi 2 baris ini:
#   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxx
#   OPENROUTER_MODEL=google/gemini-2.0-flash-exp:free
```

Cek dulu semuanya siap:

```bash
venv/bin/python main.py --verbose --input input/contoh.mp4 --max-clips 1
```

---

## 1. Cara paling sederhana

```bash
# dari YouTube
venv/bin/python main.py --input "https://www.youtube.com/watch?v=VIDEO_ID"

# dari file lokal
venv/bin/python main.py --input input/vidio-saya.mp4
```

Hasil ada di `output/`: `01_<judul>_klip1_....mp4` (9:16 + subtitle terbakar),
lalu `.srt` dan `.ass` (subtitle yang bisa diedit).

---

## 2. Cara baru: crop yang **mengikuti wajah**

```bash
venv/bin/python main.py --input input/vidio-saya.mp4 --face-tracking
```

Wajah dilacak sepanjang klip, jendela crop bergerak mengikuti wajah (orang
yang jalan/bergeser tetap di tengah frame). Wajah tidak terdeteksi? Program
otomatis fallback ke crop tengah — tidak pernah gagal.

### Mengatur kepekaan & keelusan

| Tujuan | Perintah | `.env` |
|---|---|---|
| Lebih akurat (deteksi lebih rapat) | `--face-sample-fps 20` | `FACE_TRACK_SAMPLE_FPS=20` |
| Lebih responsif (cepat mengikuti gerak) | `--face-smooth 3` | `FACE_TRACK_SMOOTH=3` |
| Wajah kecil lebih mudah kena | `--face-detect-width 1280` | `FACE_DETECT_WIDTH=1280` |
| Mematikan (crop tengah) | `--no-face-tracking` | `FACE_TRACKING=false` |

Contoh gabungan:

```bash
venv/bin/python main.py \
  --input input/vidio-saya.mp4 \
  --face-tracking --face-sample-fps 20 --face-smooth 3 \
  --max-clips 3 --min-seconds 30 --max-seconds 45
```

> Perintah di baris perintah **menimpa** nilai `.env` untuk satu kali jalan.
> Nilai `.env` dipakai kalau opsi tidak diberikan.

### Cara kerjanya (4 langkah)

1. **Deteksi** — YuNet (model DNN 227 KB di `assets/`) tiap
   `FACE_TRACK_SAMPLE_FPS` detik; Haar cascade sebagai cadangan.
2. **Pilih** — wajah terbesar yang masih dekat dengan posisi sebelumnya
   (tidak berganti orang).
3. **Haluskan** — celah diisi, deteksi liar dibuang (median), dirata-rata.
4. **Gerakkan crop** — lintasan jadi perintah `sendcmd` untuk filter `crop`
   FFmpeg, jadi crop benar-benar bergerak.

---

## 3. Cara baru: gabungkan semua klip jadi satu video

```bash
venv/bin/python main.py --input input/vidio-saya.mp4 --merge
```

Hasil: `output/00_<judulvideo>_gabungan.mp4` (semua klip berurutan, 1080x1920,
subtitle tetap tertanam). Kalau gagal, klip individual **tidak dihapus**.

---

## 4. Cara baru: subtitle rapi (otomatis)

Tidak perlu opsi apa pun — subtitle sudah:

- tidak pernah tumpang tindih antar cue,
- selalu muat di frame (lebar diukur dalam piksel, bukan jumlah karakter),
- maksimal 2 baris, di bagian tengah-bawah, di atas area UI platform.

Kalau ingin mengedit, buka file `.srt` di `output/` (subtitle ada juga sebagai
`.ass`).

---

## 5. Hemat waktu saat bereksperimen

```bash
# 1) jalankan sekali dengan --keep-temp supaya transkripnya tersimpan
venv/bin/python main.py --input input/vidio-saya.mp4 --keep-temp

# 2) coba-coba potongan/face tracking tanpa transkripsi ulang
venv/bin/python main.py --input input/vidio-saya.mp4 --reuse-transcript --face-tracking
```

---

## 6. Video dari YouTube yang kena verifikasi bot

```bash
# a) pakai cookie (butuh akun YouTube)
venv/bin/python main.py --input "https://..." --cookies cookies.txt

# b) atau pakai file lokal: unduh manual di browser, taruh di input/
venv/bin/python main.py --input input/vidio-saya.mp4
```

---

## 7. Di Google Colab (GPU gratis)

### 7.1 Sekali saja di Colab

1. **Runtime → Change runtime type → GPU**.
2. **Runtime → Manage secrets → New secret** → nama `OPENROUTER_API_KEY`,
   isi API key OpenRouter gratis.
3. Pastikan repo di GitHub **lengkap dengan folder `assets/`** (di situ model
   deteksi wajah berada).

### 7.2 Clone + cek lingkungan

```python
!git clone https://github.com/USER/autoclip.git /content/autoclip
!python /content/autoclip/autoclip_colab.py --check-env
```

Yang perlu dibaca di output:

```
[colab] FFmpeg  : True | FFprobe: True
[colab] GPU     : Tesla T4, 15360 MiB
[colab] CUDA    : siap=True device_count=1
[colab] Wajah   : yunet (227 KB) - akurat      <- face tracking siap
```

Kalau baris `Wajah` berbunyi `tidak ada`, folder `assets/` tidak ikut
ter-clone → face tracking tidak bisa jalan (crop tengah saja). Clone ulang
tanpa `--depth 1` yang membuang file besar, atau salin manual folder `assets/`.

Kalau `CUDA : siap=False`, jalankan sekali **tanpa** `--skip-install`
(sekali saja) supaya pustaka CUDA dipasang, atau `Execution → Restart runtime`.

### 7.3 Jalankan

```python
# paling ringkas (skrip clone repo sendiri)
!python /content/autoclip/autoclip_colab.py \
    --repo https://github.com/USER/autoclip.git \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free
```

```python
# dengan crop ikut wajah + pengaturan face tracking
!python /content/autoclip/autoclip_colab.py \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free \
    --face-tracking \
    -- --face-sample-fps 20 --face-smooth 3 --max-clips 3
```

```python
# simpan hasil ke Google Drive
from google.colab import drive
drive.mount('/content/drive')

!python /content/autoclip/autoclip_colab.py \
    --input "/content/drive/MyDrive/videos/videosaya.mp4" \
    --model google/gemini-2.0-flash-exp:free \
    --face-tracking --merge \
    --drive-dir "/content/drive/MyDrive/autoclip"
```

### 7.4 Aturan Colab yang perlu diingat

| Hal | Keterangan |
|---|---|
| Argumen untuk `main.py` | ditulis **setelah** `--` (mis. `-- --max-clips 3 --keep-temp`) |
| `--face-tracking` | milik `autoclip_colab.py`: menulis `FACE_TRACKING=true` ke `.env`, berlaku untuk percobaan berikutnya |
| `-- --face-sample-fps 20` | milik `main.py`: berlaku khusus percobaan itu saja |
| Model OpenRouter | **wajib** berakhiran `:free` (atau router `openrouter/free`) |
| API key | dibaca dari Colab Secrets, tidak pernah muncul di log |
| File di `/content` | **hilang** saat runtime ditutup → unduh zip hasil / pakai `--drive-dir` dulu |
| Face tracking | menambah ~10–20 detik per klip (deteksi wajah jalan di CPU) |
| Verifikasi bot YouTube | bukan bug program: pakai file lokal atau kirim cookie (`-- --cookies cookies.txt`) |

### 7.5 Kalau model gratis kena rate limit

```python
# 1) tunggu beberapa menit, lalu ulangi tanpa transkripsi ulang
!python /content/autoclip/autoclip_colab.py ... -- --reuse-transcript

# 2) ganti model gratis lain di .env (semua berakhiran :free)
# 3) perkecil durasi klip
!python /content/autoclip/autoclip_colab.py ... -- --max-seconds 40
```

---

## 8. Daftar lengkap opsi

### `main.py`

| Opsi | Fungsi |
|---|---|
| `--input`, `-i` | URL atau path file (wajib) |
| `--max-clips N` | jumlah klip per video |
| `--min-seconds N` / `--max-seconds N` | durasi klip |
| `--language KODE` | `id`, `en`, atau `auto` |
| `--face-tracking` / `--no-face-tracking` | crop ikut wajah / crop tengah |
| `--face-sample-fps N` | deteksi wajah per detik (default 10) |
| `--face-smooth N` | jendela perataan lintasan (default 5) |
| `--face-detect-width N` | lebar frame deteksi (default 640) |
| `--merge` / `--no-merge` | gabungkan semua klip jadi satu video |
| `--reuse-transcript` | pakai `temp/transcript.json`, lewati transkripsi |
| `--progress-seconds N` | jarak antar baris progress unduhan (default 15) |
| `--cookies PATH` | kirim `cookies.txt` ke yt-dlp |
| `--env PATH` | pakai file `.env` lain |
| `--keep-temp` | jangan bersihkan `temp/` |
| `--verbose` | tampilkan konfigurasi (API key dimasker) |

### `autoclip_colab.py`

| Opsi | Fungsi |
|---|---|
| `--input`, `-i` | URL atau path file di Colab |
| `--repo URL` | clone repo kalau belum ada |
| `--model NAMA` | model OpenRouter gratis (wajib `:free`) |
| `--api-key KEY` | API key (alternatif dari Colab Secrets) |
| `--env-file PATH` | pakai file `.env` tertentu |
| `--whisper-model NAMA` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `--cpu` | paksa CPU walau GPU ada |
| `--face-tracking` / `--no-face-tracking` | crop ikut wajah / crop tengah |
| `--drive-dir PATH` | salin hasil ke Google Drive |
| `--skip-install` | lewati apt + pip (GPU tetap dicek) |
| `--no-download` | jangan zip/unduh hasil |
| `--no-prompt` | tanpa interaksi terminal |
| `--check-env` | periksa lingkungan lalu keluar |
| `-- <args>` | teruskan ke `main.py` |

---

## 9. Kalau ada masalah

| Gejala | Yang harus dilakukan |
|---|---|
| Wajah tidak terdeteksi | Otomatis fallback crop tengah. Kalau wajah terdeteksi tapi gerakannya kaku: `--face-sample-fps 20 --face-smooth 3` |
| `[clipper] tidak ada model deteksi wajah` | `assets/face_detection_yunet_2023mar.onnx` hilang → clone repo lengkap dengan `assets/` |
| `Sign in to confirm you're not a bot` | IP diblokir → pakai file lokal atau `--cookies cookies.txt` |
| `HTTP 429` dari OpenRouter | Kuota model gratis habis → tunggu / ganti model `:free` / `-- --reuse-transcript` |
| `libcublas.so.12 is not found` | GPU tidak bisa dipakai → otomatis turun ke CPU, atau restart runtime Colab |
| Unduhan lama "macet" | Bukan macet → cek file `.part` di `temp/` |

Kode keluar: `0` sukses, `2` konfigurasi belum benar, `3` FFmpeg tidak ada,
`4` gagal unduh/transkripsi, `5` gagal pilih highlight, `6` gagal potong/subtitle.
