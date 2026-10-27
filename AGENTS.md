# AGENTS.md — AUTO CLIP

Proyek: mengubah video panjang menjadi klip pendek vertikal (9:16) lengkap dengan subtitle.
Semua tools wajib GRATIS dan open source.

---

## LINGKUNGAN

- **Lokasi proyek:** `/home/qwerty/clip` (lokal, bukan Colab).
- **Python:** `venv/bin/python` (Python 3.12). Install dependency dengan `venv/bin/pip install -r requirements.txt`.
- **GPU:** tidak ada (`nvidia-smi` tidak ditemukan). Semua operasi berjalan di CPU,
  jadi `WHISPER_COMPUTE_TYPE` efektif `int8`.
- **FFmpeg:** 6.1.1, sudah terpasang di sistem.
- File di mesin ini BUKAN file di komputer lokal user dan sebaliknya.
- **Rahasia hanya dari `.env`.** DILARANG menulis API key langsung di kode, di prompt,
  atau di output/log. Kalau perlu menampilkan key, tampilkan masker (`sk-...abcd`).

---

## ATURAN PROBLEM & FIX

Aturan ini WAJIB dipatuhi dan dibaca ulang setiap sesi.

1. **SEBELUM** memulai pekerjaan apa pun dan **SEBELUM** memperbaiki error apa pun,
   baca `problem.md` dan `fix.md` sampai habis.
2. Setiap kali menemui masalah (error, output salah, library tidak cocok, API gagal),
   langkah pertama adalah **MENULIS masalah itu di `problem.md`**, BARU setelah itu
   memperbaiki kode. **Dilarang memperbaiki sebelum mencatat.**
   Format entri `problem.md`:

   ```
   ## P-001 | judul singkat
   - Waktu:
   - File/langkah terkait:
   - Pesan error / gejala (salin apa adanya, tanpa API key):
   - Dugaan penyebab:
   - Status: OPEN
   ```

3. Setelah memperbaiki dan menguji ulang, tulis perubahannya di `fix.md`, lalu ubah
   status di `problem.md` menjadi `FIXED` (atau `FAILED` jika belum berhasil).
   Format entri `fix.md`:

   ```
   ## F-001 | memperbaiki P-001
   - Perubahan (file dan apa yang diubah):
   - Alasan:
   - Hasil pengujian ulang:
   ```

4. **Cegah kesalahan berulang:** sebelum mencoba perbaikan, cek apakah masalah serupa
   sudah pernah ada di `problem.md`/`fix.md`. Jika ya, **jangan ulangi pendekatan yang
   sama**. Pakai pendekatan berbeda dan catat bahwa ini percobaan ke-N.
5. Jika satu masalah gagal diperbaiki **3 kali**, **berhenti**, rangkum apa yang sudah
   dicoba, dan tanyakan arahan kepada pengguna.
6. Saat membuat kode baru, terapkan pelajaran dari `fix.md` supaya masalah lama
   tidak muncul lagi.

---

## STRUKTUR PROYEK

```
autoclip/
├── AGENTS.md
├── CARA_PAKAI.md       # resep perintah siap pakai (lokal + Colab) untuk user
├── problem.md          # jurnal masalah (tulis DULU sebelum fix)
├── fix.md              # jurnal perbaikan (tulis SETELAH berhasil)
├── .env                # diisi pengguna, JANGAN dicommit
├── .env.example
├── .gitignore
├── requirements.txt
├── main.py             # entry point CLI: python main.py --input URL_atau_file
├── autoclip_colab.py   # pembungkus Colab: install, .env dari Secrets, GPU, zip hasil
├── src/
│   ├── config.py       # baca .env dengan python-dotenv, validasi variabel wajib
│   ├── downloader.py   # yt-dlp untuk URL, atau pakai file lokal
│   ├── transcriber.py  # faster-whisper, timestamp per kata, simpan JSON
│   ├── highlight.py    # panggil OpenRouter untuk memilih segmen terbaik
│   ├── clipper.py      # FFmpeg: potong, crop 9:16 (statis atau ikut wajah)
│   ├── face_track.py   # deteksi wajah (YuNet/Haar) + lintasan -> perintah sendcmd
│   ├── merger.py       # FFmpeg concat: gabungkan semua klip jadi satu video
│   └── subtitles.py    # buat .ass/.srt dari timestamp kata, bakar ke video
├── assets/            # model deteksi wajah (YuNet ONNX + Haar cascade) + fixture uji
├── tests/             # mock OpenRouter + uji modul
├── input/
├── temp/
└── output/
```

---

## ATURAN KODE

- **Jangan hardcode nama model.** Semua nilai konfigurasi dibaca dari `.env`.
- Jika `OPENROUTER_API_KEY` atau `OPENROUTER_MODEL` masih berisi placeholder,
  hentikan program dengan **pesan error yang jelas** (jangan diam-diam jalan).
- **Blokir keras model berbayar HANYA di OpenRouter resmi:** jika
  `OPENROUTER_BASE_URL` menunjuk `openrouter.ai` dan `OPENROUTER_MODEL` tidak berakhiran
  `:free`, program **WAJIB** berhenti dengan pesan error — bukan hanya memberi peringatan.
  Proyek ini hanya mengizinkan model gratis di OpenRouter (lihat `problem.md` P-010 /
  `fix.md` F-010). Endpoint OpenAI-compatible milik pengguna (mis. 9router di
  `http://localhost:20128/v1` atau lewat ngrok) memakai model **apa adanya**: jangan
  pilih model otomatis dan jangan tambahkan `:free` (lihat P-030 / F-030).
  Pengecekan dilakukan lewat `src/config.py::model_is_free(model, base_url)` (helper yang
  juga menerima router gratis `openrouter/free`, lihat P-022) — jangan lagi mengecek
  sufiks `:free` secara terpisah di tempat lain, karena aturannya bisa berbeda.
  Daftar model gratis OpenRouter: `https://openrouter.ai/models?max_price=0`
- Model gratis OpenRouter sering rate limit dan kadang mengembalikan JSON berantakan:
  wajib retry dengan backoff, hapus pembungkus ```json sebelum parsing, dan validasi
  hasil (start < end, durasi sesuai batas, tidak melebihi durasi video).
- Jika model gagal berulang kali → tulis ke `problem.md`, jangan diam-diam ganti model.
- Face tracking hanya jalan jika `FACE_TRACKING=true`, dan **harus fallback ke crop
  tengah** jika gagal.
- Face tracking **harus bergerak**, bukan satu posisi diam: wajah di-lacak per sampel
  waktu, lintasan diperrata, lalu jendela crop digerakkan lewat `sendcmd` + filter
  `crop` FFmpeg (lihat `src/face_track.py` dan `problem.md` P-028).
- Semua stderr/stdout log tidak boleh membocorkan API key.

---

## ALUR PROGRAM

1. Ambil video (yt-dlp atau file lokal), ekstrak audio dengan FFmpeg.
2. Transkripsi dengan faster-whisper, simpan transkrip + timestamp per kata ke `temp/`.
3. Kirim transkrip ke OpenRouter (chat completions, API kompatibel OpenAI).
   Minta LLM memilih sampai `MAX_CLIPS` segmen dengan hook kuat, topik utuh,
   durasi sesuai `CLIP_MIN_SECONDS`/`CLIP_MAX_SECONDS`.
   Output WAJIB JSON: `[{"start": detik, "end": detik, "title": "...", "reason": "..."}]`
4. Potong tiap segmen dengan FFmpeg, ubah ke 9:16 (1080x1920). Default crop tengah.
5. Buat subtitle dari timestamp kata (maks 2 baris, teks besar di tengah-bawah),
   bakar ke video, simpan ke `output/` dengan nama rapi.

---

## CARA PAKAI

```bash
# 1) install dependency (sekali saja)
venv/bin/pip install -r requirements.txt

# 2) isi .env
cp .env.example .env
nano .env          # isi OPENROUTER_API_KEY + OPENROUTER_MODEL (model :free)

# 3) jalankan
venv/bin/python main.py --input https://www.youtube.com/watch?v=xxxx
venv/bin/python main.py --input input/vidio-saya.mp4
```

Opsi berguna:

| Opsi | Fungsi |
|---|---|
| `--max-clips N` | override `MAX_CLIPS` |
| `--min-seconds N` / `--max-seconds N` | override durasi klip |
| `--face-tracking` / `--no-face-tracking` | paksa ikut wajah / crop tengah |
| `--face-sample-fps N` | override `FACE_TRACK_SAMPLE_FPS` (deteksi wajah per detik) |
| `--face-smooth N` | override `FACE_TRACK_SMOOTH` (jendela perataan lintasan) |
| `--face-detect-width N` | override `FACE_DETECT_WIDTH` (lebar frame deteksi) |
| `--reuse-transcript` | pakai `temp/transcript.json`, lewati transkripsi (hemat waktu) |
| `--merge` / `--no-merge` | gabungkan semua klip jadi satu video (default dari `.env` `MERGE_CLIPS`) |
| `--keep-temp` | jangan bersihkan `temp/` |
| `--cookies PATH` | kirim `cookies.txt` ke yt-dlp (hanya kalau YouTube minta verifikasi bot, P-016) |
| `--env PATH` | pakai file .env lain (dipakai pengujian) |
| `--verbose` | tampilkan konfigurasi (API key dimasker) |

Kode keluar: `0` sukses, `2` konfigurasi `.env` belum lengkap **atau model bukan `:free`**,
`3` ffmpeg tidak ada, `4` gagal unduh/transkripsi, `5` gagal pilih highlight (LLM),
`6` gagal clip/subtitle.

### Pengujian

```bash
# uji modul highlight vs mock OpenRouter lokal (7 skenario)
venv/bin/python tests/test_highlight.py

# uji verifikasi bot YouTube + cookies (yt-dlp dipalsukan, tanpa internet)
venv/bin/python tests/test_bot_check.py

# uji diagnostik CUDA Colab runner (tanpa GPU, probe disimulasikan)
venv/bin/python tests/test_cuda_diagnostics.py

# uji aturan model gratis (suffix :free + router openrouter/free + gateway sendiri)
venv/bin/python tests/test_model_gratis.py

# uji provider OpenAI-compatible (9router/ngrok): URL, model apa adanya, timeout, error
venv/bin/python tests/test_llm_provider.py

# uji penulisan .env di runner Colab (kunci pengguna tidak boleh hilang)
venv/bin/python tests/test_env_writer.py

# uji subtitle: tidak ada cue overlap, teks muat di frame, header .ass benar
venv/bin/python tests/test_subtitles.py

# uji penggabungan klip (FFmpeg concat + encode ulang + verifikasi ffprobe)
venv/bin/python tests/test_merge.py

# uji face tracking: deteksi, lintasan, crop bergerak, fallback crop tengah
venv/bin/python tests/test_face_tracking.py

# diagnosis lingkungan Colab (GPU, pustaka CUDA, device di .env)
venv/bin/python autoclip_colab.py --check-env

# buat video uji 1-3 menit (butuh edge-tts)
venv/bin/pip install edge-tts && venv/bin/python make_test_video.py
```

### Menjalankan di Google Colab

Jangan-port langsung `main.py` ke Colab; pakai `autoclip_colab.py`:

```python
!python autoclip_colab.py -i "<URL>" --model <nama-model:free> \
    -- --max-clips 3 --keep-temp
```

File itu mengurus FFmpeg (apt tanpa `sudo`), `pip install -r requirements.txt` dengan
`sys.executable`, pustaka CUDA 12 + `LD_LIBRARY_PATH` untuk faster-whisper di GPU,
`.env` dari Colab Secrets (model wajib `:free`, API key tidak pernah di-log), retry CPU
bila GPU gagal, lalu zip hasil untuk diunduh. Semua aturan di AGENTS.md tetap berlaku.

**Face tracking di Colab:**

```python
!python autoclip_colab.py -i "<URL>" --model <nama-model:free> \
    --face-tracking \
    -- --face-sample-fps 20 --face-smooth 3
```

- Folder `assets/` **wajib** ikut ter-clone (isi model deteksi wajah
  `face_detection_yunet_2023mar.onnx`). Kalau tidak ikut, face tracking
  otomatis fallback ke crop tengah (tidak error).
- `autoclip_colab.py --check-env` mencetak baris `Wajah : yunet (227 KB) - akurat`
  (atau `haar` / `tidak ada`) sebagai pemeriksa cepat.
- Argumen setelah `--` diteruskan ke `main.py`; `--face-tracking` milik
  `autoclip_colab.py` menulis `FACE_TRACKING=true` ke `.env` (berlaku untuk
  percobaan berikutnya di runtime yang sama).
- Face tracking menambah sekitar 10–20 detik per klip (deteksi wajah jalan di
  CPU).

---

## PENGUJIAN

- Uji **tiap modul terpisah** (download, transkripsi, highlight, clip, subtitle),
  baru jalankan alur penuh.
- Mulai dari video pendek 1–3 menit.
- Di akhir laporan: apa yang berjalan, file hasil di `output/`, ringkasan
  `problem.md`/`fix.md`.