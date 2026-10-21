# AUTO CLIP

Masukkan satu video panjang (YouTube atau file lokal), dapat beberapa **klip vertikal
9:16 (1080x1920) bersubtitle** — subtitle sudah tertanam di dalam videonya.

Semua gratis & open source, jalan di laptop tanpa GPU.

Cara kerjanya: unduh video → transkrip per kata (Whisper) → pilih momen terbaik
(OpenRouter, model gratis) → potong & ubah ke 9:16 (FFmpeg) → tulis subtitle.

---

## Yang Bisa Dilakukan (fitur & cara pakainya)

| Fitur | Cara pakai | Catatan |
|---|---|---|
| **Crop ikut wajah (face tracking)** | `--face-tracking` atau `FACE_TRACKING=true` | Wajah dilacak sepanjang klip, jendela crop **bergerak** mengikuti wajah. Detail di [Crop yang Mengikuti Wajah](#crop-yang-mengikuti-wajah-face-tracking) |
| Atur face tracking per-cli | `--face-sample-fps 20 --face-smooth 3 --face-detect-width 1280` | Menimpa nilai `.env` untuk satu kali jalan |
| Subtitle terbakar, tidak keluar frame | otomatis | Lebar teks diukur dalam piksel, cue tidak pernah tumpang tindih |
| Subtitle juga dalam `.srt` | otomatis | File `.srt` + `.ass` tersimpan di `output/` |
| Gabungkan semua klip jadi 1 video | `--merge` atau `MERGE_CLIPS=true` | Hasil: `output/00_<judul>_gabungan.mp4` |
| Ambil video dari YouTube | `--input <URL>` | yt-dlp + progress + penanganan verifikasi bot |
| Pakai video lokal | `--input input/vidio.mp4` | Tidak perlu internet untuk pemrosesannya |
| Hemat waktu saat bereksperimen | `--reuse-transcript` | Memakai `temp/transcript.json` yang sudah ada |
| Batas resolusi unduhan | `MAX_SOURCE_HEIGHT=720` | Hasil akhir tetap 1080x1920, unduhan jauh lebih ringan |
| Kirim cookie YouTube | `--cookies cookies.txt` | Hanya kalau YouTube minta verifikasi bot |
| Jalan di Colab (GPU gratis) | `!python autoclip_colab.py ...` | Install, CUDA, `.env`, zip hasil, semua diurus |

> 📄 **[CARA_PAKAI.md](CARA_PAKAI.md)** = resep perintah siap pakai (lokal + Colab),
> termasuk cara mengatur face tracking dan semua opsinya.

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
  (router `openrouter/free` juga boleh — dia otomatis memilih model gratis)

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
| `FACE_TRACK_SAMPLE_FPS` | `10` | berapa kali deteksi wajah per detik (makin tinggi makin akurat & makin lambat) |
| `FACE_TRACK_SMOOTH` | `5` | jendela perataan lintasan wajah (`1` = mengikuti apa adanya, `9` = sangat halus) |
| `FACE_DETECT_WIDTH` | `640` | lebar frame untuk deteksi wajah (`640` = cepat, `1280` = lebih rinci) |
| `MAX_SOURCE_HEIGHT` | `1080` | turunkan ke `720` supaya unduhan jauh lebih cepat |
| `DOWNLOAD_PROGRESS_SECONDS` | `15` | jarak antar baris progress unduhan; `0` = hanya tiap 10% |
| `YT_COOKIES_FILE` | (kosong) | isi `cookies.txt` hanya kalau YouTube meminta verifikasi bot |
| `YT_PLAYER_CLIENTS` | `tv,tv_simply,ios,mweb` | player client yang dicoba saat verifikasi bot; tambah `android_vr`/`web_embedded` kalau masih ditolak |
| `YT_JS_RUNTIMES` | (auto) | runtime JS untuk yt-dlp (`node`/`deno`); kosong = pakai yang ada, `none` = matikan |
| `MERGE_CLIPS` | `false` | `true` = gabungkan semua klip jadi satu video (setara `--merge`) |

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
| `--merge` / `--no-merge` | gabungkan semua klip jadi satu video `00_<judul>_gabungan.mp4` (default dari `.env` `MERGE_CLIPS`) |
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

### Crop yang Mengikuti Wajah (face tracking)

```bash
venv/bin/python main.py --input input/vidio-saya.mp4 --face-tracking
```

Kalau `--face-tracking` aktif, program **melacak wajah sepanjang klip** dan
jendela crop 9:16 bergerak mengikuti wajah — orang yang jalan/bergeser tetap
wajahnya di tengah frame, bukan terkunci di satu posisi.

**Sebelum vs sesudah** (video uji: wajah bergerak dari kiri ke kanan):

| | Wajah di frame hasil | Posisi wajah di frame |
|---|---|---|
| Crop diam (cara lama) | hilang di **101 dari 200** frame | 0,23 – 0,74 (kadang sama sekali tidak ada) |
| Crop bergerak (sekarang) | ada di **200 dari 200** frame | 0,458 – 0,547 (tengah = 0,500) |

#### Cara kerjanya (4 langkah)

1. **Deteksi** — wajah dideteksi tiap `FACE_TRACK_SAMPLE_FPS` detik memakai
   **YuNet** (model DNN di `assets/face_detection_yunet_2023mar.onnx`, 227 KB,
   gratis & open source). Kalau modelnya tidak ada, program otomatis pakai
   Haar cascade `assets/haarcascade_frontalface_default.xml`.
2. **Pilih wajah** — yang dipilih adalah wajah **terbesar** yang masih **dekat**
   dengan posisi sebelumnya, jadi tidak berganti orang di tengah klip.
3. **Haluskan lintasan** — celah diisi (interpolasi), deteksi liar dibuang
   (filter median), lalu dirata-rata. Hasilnya mulus, tidak "goyang".
4. **Gerakkan crop** — lintasan diubah jadi perintah `sendcmd` untuk filter
   `crop` FFmpeg, sehingga jendela crop benar-benar bergerak mengikuti wajah.

Kalau wajah **tidak terdeteksi sama sekali** (atau modelnya hilang, atau
render gagal), program otomatis **fallback ke crop tengah** — klip tetap jadi,
tidak pernah gagal karena fitur ini.

#### Menyesuaikan hasil

| Yang diubah | Cara | Efek |
|---|---|---|
| Lebih akurat | `--face-sample-fps 20` atau `FACE_TRACK_SAMPLE_FPS=20` | deteksi lebih rapat, gerak lebih halus, ~2× lebih lambat |
| Lebih responsif | `--face-smooth 3` atau `FACE_TRACK_SMOOTH=3` | lebih cepat mengikuti gerakan, sedikit lebih "goyang" |
| Lebih rinci | `--face-detect-width 1280` atau `FACE_DETECT_WIDTH=1280` | wajah kecil lebih mudah terdeteksi |
| Mematikan | `--no-face-tracking` atau `FACE_TRACKING=false` | crop tengah, paling cepat |

Contoh gabungan:

```bash
venv/bin/python main.py \
  --input input/vidio-saya.mp4 \
  --face-tracking \
  --face-sample-fps 20 \
  --face-smooth 3 \
  --max-clips 3
```

> Catatan: `--face-sample-fps`, `--face-smooth`, `--face-detect-width` hanya
> berlaku kalau face tracking aktif. Nilai defaultnya diambil dari `.env`
> (`FACE_TRACK_SAMPLE_FPS`, `FACE_TRACK_SMOOTH`, `FACE_DETECT_WIDTH`), dan
> perintah di baris perintah **menimpa** nilai `.env` untuk satu kali jalan.

### Gabungkan Semua Klip Jadi Satu Video

```bash
venv/bin/python main.py --input input/vidio-saya.mp4 --merge
```

Hasilnya ada di `output/00_<judulvideo>_gabungan.mp4`: semua klip disusun berurutan,
di-encode ulang (H.264 + AAC, tetap 1080x1920, subtitle tetap tertanam), lalu
dicek dengan ffprobe (harus ada stream video **dan** audio). Kalau hanya ada satu
klip atau penggabungan gagal, program memberi pesan jelas dan **klip individual
tidak dihapus**. Di Colab, teruskan lewat `-- --merge`; file gabungan ikut masuk
ke zip hasil dan ke `--drive-dir`.

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
| `Sign in to confirm you're not a bot` | Reputasi IP sedang ditandai, bukan bug program. Program menyalakan runtime JS (node/deno) lalu mencoba beberapa player client satu per satu (`tv`, `tv_simply`, `ios`, `mweb`). Kalau tetap ditolak: pakai file lokal (`input/`), kirim cookie (`--cookies cookies.txt`), atau tambah client lain lewat `YT_PLAYER_CLIENTS=tv,ios,tv_simply,mweb,android_vr` di `.env`. **Jangan** tambahkan `player_skip=webpage` — itu justru memicu verifikasi bot. Lihat [P-016](problem.md) dan [P-025](problem.md) |
| `HTTP 429` dari OpenRouter | Kuota model gratis habis; tunggu, ganti model `:free`, atau pakai akun yang pernah beli kredit |
| `libcublas.so.12 is not found` | GPU tidak bisa dipakai. Otomatis turun ke CPU; kalau `WHISPER_DEVICE=cuda` dipaksa, ubah ke `cpu` + `int8`, atau jalankan lewat `autoclip_colab.py` |
| `[colab] GPU ada tapi ctranslate2 tidak bisa memakainya -> fallback ke CPU` | Angka `[transcribe] device=cpu` muncul, padahal Colab punya GPU. Cek penyebabnya dengan `!python autoclip_colab.py --check-env` (baris `CUDA :` + daftar pustaka). Kalau muncul "TIDAK ADA di folder mana pun", program sudah mencoba `pip install --force-reinstall --no-deps nvidia-cublas-cu12 nvidia-cuda-runtime-cu12`; kalau masih gagal, **Restart runtime** lalu ulangi. Lihat [P-019](problem.md) dan [P-021](problem.md) |
| `Transkripsi kosong` | Coba `--language auto` |
| Wajah tidak terdeteksi | Otomatis fallback ke crop tengah, jadi aman. Kalau wajah **terdeteksi tapi gerakannya kaku**, naikkan `FACE_TRACK_SAMPLE_FPS=20` dan turunkan `FACE_TRACK_SMOOTH=3` |
| `[clipper] tidak ada model deteksi wajah` | Berkas `assets/face_detection_yunet_2023mar.onnx` hilang (mis. repo di-clone tanpa `assets/`). Taruh file itu kembali ke `assets/`, atau andalkan Haar cascade `assets/haarcascade_frontalface_default.xml` |

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
| `--skip-install` | lewati install (percobaan kedua dst.). GPU tetap diperiksa, jadi kalau pustaka CUDA sudah terpasang, mode tetap GPU |
| `--no-download` | jangan zip/unduh hasil |
| `--face-tracking` / `--no-face-tracking` | crop ikut wajah / crop tengah (ditulis ke `.env` di Colab) |
| `-- <args>` | teruskan argumen ke `main.py`, mis. `-- --max-clips 3 --keep-temp` |

### Face tracking di Colab

Sama persis dengan di laptop — yang berbeda cuma letaknya. Yang perlu dijaga:
**folder `assets/` harus ikut ter-clone**, karena model deteksi wajah
(`face_detection_yunet_2023mar.onnx`) ada di sana. Kalau `assets/` tidak ikut,
program otomatis fallback ke crop tengah (tidak error, tapi wajah tidak
diikuti).

```python
# 1) clone repo (pastikan folder assets/ ikut ter-clone)
!git clone https://github.com/USER/autoclip.git /content/autoclip

# 2) cek dulu: model wajah & GPU sudah siap?
!python /content/autoclip/autoclip_colab.py --check-env
```

Baris `Wajah : model=...` dioutput `--check-env` menunjukkan model apa yang
dipakai (`yunet` = akurat, `haar` = cadangan, `tidak ada` = face tracking
tidak bisa jalan, crop tengah saja).

```python
# 3) jalankan dengan crop ikut wajah
!python /content/autoclip/autoclip_colab.py \
    --input "https://www.youtube.com/watch?v=VIDEO_ID" \
    --model google/gemini-2.0-flash-exp:free \
    --face-tracking \
    -- --face-sample-fps 20 --face-smooth 3 --max-clips 3
```

- `--face-tracking` (milik `autoclip_colab.py`) menulis `FACE_TRACKING=true`
  ke `.env` di Colab, jadi berlaku untuk semua percobaan berikutnya di runtime
  yang sama.
- Argumen setelah `--` diteruskan ke `main.py`, jadi
  `-- --face-sample-fps 20` berlaku khusus untuk percobaan ini saja.
- Face tracking menambah waktu sekitar **10–20 detik per klip** (deteksi wajah
  berjalan di CPU). Kalau video sudah banyak, turunkan
  `--face-sample-fps` ke `5`.
- Hasil tetap sama: zip berisi semua klip + file `.srt`/`.ass`, dan file
  gabungan kalau `-- --merge` dipakai.

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

Lihat juga `CARA_PAKAI.md` (resep perintah siap pakai, lokal + Colab),
`AGENTS.md` (aturan kerja proyek), `problem.md`, dan `fix.md` kalau
ingin tahu riwayat masalah yang pernah ditangani.