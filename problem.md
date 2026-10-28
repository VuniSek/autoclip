# problem.md — jurnal masalah AUTO CLIP

> Aturan: TULIS masalah di sini **DULU** sebelum memperbaiki kode.
> Status: `OPEN` -> `FIXED` (sudah berhasil) atau `FAILED` (3x percobaan gagal).

## P-ENV | verifikasi environment sebelum mulai kerja
- Waktu: 2026-10-17
- File/langkah terkait: LINGKUNGAN
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  nvidia-smi: command not found
  Python 3.12.3 | venv: /home/qwerty/clip/venv | 8 CPU | 4 GB RAM | ffmpeg 6.1.1
  ```
- Dugaan penyebab: brief mengasumsikan lingkungan Colab dengan GPU, ternyata mesin lokal tanpa GPU.
- Status: FIXED

## P-001 | tidak ada sumber video uji (TTS lokal tidak tersedia)
- Waktu: 2026-10-17
- File/langkah terkait: PENGUJIAN
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  $ which espeak espeak-ng festival flite pico2wave say
  (tidak ada output / tidak ditemukan)
  ```
- Dugaan penyebab: mesin tidak punya TTS lokal, jadi tidak bisa membuat video uji 1-3 menit
  dengan suara Indonesia tanpa mengunduh material dari internet.
- Status: FIXED
- Catatan akar masalah: diselesaikan dengan `edge-tts` (gratis & open source) untuk membuat
  suara Indonesia, lalu `make_test_video.py` menggabungkannya dengan video pola.
  Lihat F-003.

## P-002 | parser JSON highlight gagal saat ada teks sisipan sebelum/sesudah array
- Waktu: 2026-10-17
- File/langkah terkait: `src/highlight.py`, fungsi `_extract_array` (uji unit parser)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  with_prefix -> None
  isi masukan: 'Ini dia:\n[{"start":1,"end":40,"title":"A","reason":"x"}]\n总要!'
  (kasilain: fenced -> OK, truncated -> OK, garbage -> None (memang benar))
  ```
- Dugaan penyebab: `_extract_array` mengambil seluruh teks dari '[' pertama sampai akhir,
  lalu langsung `json.loads`. Kalau model menempelkan kalimat penutup (mis. "总要!" atau
  "Hope this helps!") setelah array, JSON jadi tidak valid dan tidak ada fallback yang
  memotong pada ']' penutup yang sesuai.
- Status: FIXED

## P-003 | faster-whisper gagal: PyAV 19 tidak kompatibel (`metadata_errors`)
- Waktu: 2026-10-17
- File/langkah terkait: `src/transcriber.py` -> `transcribe()`, uji modul transkripsi
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  File "venv/lib/python3.12/site-packages/faster_whisper/transcribe.py", line 876, in transcribe
      audio = decode_audio(audio, sampling_rate=sampling_rate)
  File "venv/lib/python3.12/site-packages/faster_whisper/audio.py", line 46, in decode_audio
      with av.open(input_file, mode="r", metadata_errors="ignore") as container:
  TypeError: open() got an unexpected keyword argument 'metadata_errors'
  src.transcriber.TranscriptionError: Transkripsi gagal: open() got an unexpected keyword argument 'metadata_errors'
  [transcribe] device=cpu compute_type=int8 model=small
  ```
- Dugaan penyebab: `faster-whisper 1.2.1` memanggil `av.open(..., metadata_errors="ignore")`,
  sedangkan `av 19.0.1` (terpasang otomatis, tidak di-pin) sudah menghapus parameter itu.
  Ini inkompatibilitas versi, bukan salah konfigurasi.
- Status: FIXED

## P-004 | gagal ambil foto wajah untuk uji face tracking
- Waktu: 2026-10-17
- File/langkah terkait: pengujian `FACE_TRACKING=true`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  $ curl -sL -A "autoclip-test/1.0" -o face.jpg "https://upload.wikimedia.org/.../800px-Woman_2_(Unsplash).jpg"
  -rw-r--r-- 1 qwerty qwerty 2009 face.jpg
  face.jpg: HTML document, ASCII text, with very long lines (443)
  ```
- Dugaan penyebab: permintaan ditolak server Wikimedia sehingga yang tersimpan halaman
  error HTML, bukan gambar.
- Status: FIXED
- Catatan akar masalah: ternyata **URL-nya salah nama file** (server membalas HTTP 400),
  bukan pemblokiran. Sumber yang berhasil: repo `opencv/opencv` di GitHub. Lihat F-005.

## P-005 | perintah FFmpeg uji video wajah gagal: opsi codec salah posisi
- Waktu: 2026-10-17
- File/langkah terkait: pembuatan `temp/facevideo.mp4` untuk uji face tracking (P-004)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  Unknown decoder 'libx264'
  Error opening input file sine=frequency=440:duration=8.
  Error opening input files: Decoder not found
  ls: cannot access 'temp/facevideo.mp4': No such file or directory
  ```
- Dugaan penyebab: opsi output (`-c:v libx264`, `-pix_fmt`, dll) ditulis sebelum input
  terakhir (`-f lavfi -i sine=...`), sehingga FFmpeg memperlakukannya sebagai opsi *input*
  dan mencarinya sebagai decoder.
- Status: FIXED

## P-006 | deteksi wajah selalu None walau ada wajah sungguhan di frame
- Waktu: 2026-10-17
- File/langkah terkait: `src/clipper.py` -> `_face_x_center()`, uji face tracking
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  pusat wajah (0..1): None | harapan ~0.247 (wajah di x=60..572 dari 1280)
  filter face: None
  OUT temp/face_clip.mp4 dimensi (1080, 1920)   # <- jalan, tapi hanya fallback crop tengah
  ```
- Dugaan penyebab: dua kemungkinan. (a) blok `except Exception: return None` di
  `_face_x_center` menelan error MediaPipe sehingga penyebab sebenarnya tidak terlihat;
  (b) API `mediapipe.solutions.face_detection` di mediapipe 1.1.1 berubah/tidak ada
  (mediapipe 1.x memindahkan solver ke `mediapipe.tasks`), sehingga pemanggilan detector
  melempar error yang langsung ditangkap.
- Status: FIXED

## P-007 | subtitle hasil bake tidak terlihat di frame video
- Waktu: 2026-10-17
- File/langkah terkait: `src/clipper.py` -> `cut_clip(burn_subtitle=...)`, `src/subtitles.py` -> `write_ass`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  # perintah ffmpeg sukses (exit 0) dan file mp4 terbentuk 1080x1920,
  # tetapi saat frame diekstrak tidak ada teks sama sekali:
  ffmpeg -y -ss 2 -i temp/test_clip_burn.mp4 -frames:v 1 temp/frame_burn.png
  # frame_burn.png = 225 KB, gambar penuh pola testsrc2, TANPA teks subtitle
  ```
- Dugaan penyebab: (a) file .ass tidak terbaca oleh filter `ass` (path/quoting), (b) libass
  gagal memuat font sehingga tidak menggambar teks, atau (c) cue tidak beririsan dengan
  waktu frame yang diambil.
- Status: FIXED
- Catatan akar masalah: **bukan bug kode**. Penyebabnya adalah (c) — saya mengambil frame
  pada `t=2.0s`, sedangkan cue di `temp/burntest.ass` hanya berlangsung `0.0-1.95s`.
  Ambil frame pada `t=0.5s` -> teks terlihat jelas. Lihat F-007.

## P-008 | teks subtitle meluber keluar frame (terpotong kiri & kanan)
- Waktu: 2026-10-17
- File/langkah terkait: `src/subtitles.py` -> `write_ass()`, hasil bake pada klip di `output/`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  # frame t=1.0s dari output/01_testvideo-id_klip1_...scrol.mp4 (1080x1920):
  #   yang tampil hanya: "gak kamu mikir, kenapa ki"  <-- terpotong di kedua tepi
  # isi cue .ass:
  Dialogue: 0,0:00:00.00,0:00:02.20,Default,,0,0,0,,Pernah gak kamu mikir, kenapa kita susah
  ```
- Dugaan penyebab: `write_ass()` menulis `c["text"]` sebagai satu baris panjang dan mengabaikan
  `c["lines"]` hasil `group_cues()/_split_lines()`. Selain itu header memakai `WrapStyle: 2`,
  yang arti libass "jangan bungkus otomatis, hanya patuhi `\N`". Akibatnya teks dirender
  sebagai satu baris panjang yang melewati lebar 1080 dan terpotong.
- Status: FIXED

## P-009 | OpenRouter gagal memilih segmen highlight
- Catatan: entri ini **dihasilkan sendiri oleh program** saat uji skenario "garbage"
  (mock membalas teks non-JSON). Ini bukti fitur pencatatan otomatis berjalan, bukan
  kerusakan pada konfigurasi pengguna.
- Waktu: 2026-10-17 09:46
- File/langkah terkait: langkah 3 (highlight), model=mock/test-model:free
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  Gagal mendapatkan segmen highlight setelah 3 percobaan pada model 'mock/test-model:free'. Error terakhir: Tidak menemukan array JSON di balasan model (awal: 'Maaf, saya tidak dapat memenuhi permintaan itu karena saya adalah asisten yang membantu dan tidak dapat mengubah format jawaban.')
  ```
- Dugaan penyebab: Model gratis OpenRouter bisa rate limit atau membalas di luar format JSON setelah semua percobaan ulang habis.
- Status: FIXED (perilaku yang diharapkan: keluar dengan kode 5, dicatat di problem.md,
  dan model TIDAK diganti diam-diam)

- Waktu: 2026-10-17
- File/langkah terkait: `src/config.py` -> `_validate()` (baris 131-137)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  # tidak ada error — justru ini masalahnya:
  [PERINGATAN] OPENROUTER_MODEL='saya/opus-4.6' tidak berakhiran ':free'. Brief ini hanya
  mengizinkan model gratis.
  # ...program LANJUT ke langkah 3 dan memakai model berbayar.
  ```
- Dugaan penyebab: pengecekan `:free` masuk ke daftar `warnings` yang hanya di-`print`
  ke stderr, bukan ke daftar `problems` yang melakukan `raise ConfigError`. Jadi ada
  risiko program diam-diam memakai kuota berbayar padahal syarat proyek adalah gratis.
- Keputusan pengguna: diubah menjadi blokir keras (selalu hentikan program).
- Status: FIXED

## P-011 | proyek belum bisa jalan di Google Colab (tidak ada file pendukung)
- Waktu: 2026-10-17
- File/langkah terkait: entry point `main.py`, `requirements.txt`, bagian 10 `README.md`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  # tidak ada error runtime — ini kesenjangan fitur, belum ada file pendukung Colab.
  # Isi repo sekarang: venv/ (khusus mesin lokal), .env (lokal), input/testvideo_id.mp4.
  # Di Colab (/content) tidak ada venv, tidak ada .env, dan tidak ada input/.
  # Dokumentasi Colab di README bagian 10 hanya 3 baris perintah manual:
  #   !apt-get install -y ffmpeg
  #   !pip install -r requirements.txt
  #   !python main.py --input <URL>
  ```
- Gejala yang akan muncul kalau langkah manual itu tidak dilengkapi:
  ```
  # (a) transkripsi di GPU Colab gagal karena pustaka CUDA untuk ctranslate2 tidak ada
  ValueError: Could not find a valid cuDNN library (or prepend $(libcudnn/bin):$LD_LIBRARY_PATH to your PATH)
  # (b) .env tidak ada di Colab -> program berhenti
  [KONFIGURASI BELUM LENGKAP] File .env tidak ditemukan di /content/autoclip/.env.
  # (c) hasil klip tertinggal di /content/output dan hilang saat runtime ditutup
  ```
- Dugaan penyebab: proyek dirancang untuk mesin lokal tanpa GPU. Colab punya karakteristik
  sendiri: root tanpa `sudo`, CUDA 12 untuk `ctranslate2`, Colab Secrets untuk API key,
  sistem file ephemeral, dan hasil harus diunduh/salin ke Drive.
- Keputusan pengguna: buat satu file baru yang membungkus seluruh kebutuhan Colab
  (instalasi, konfigurasi, menjalankan pipeline, mengambil hasil).
- Status: FIXED (lihat `fix.md` F-011; file baru `autoclip_colab.py`)

## P-012 | jalur `--repo` (git clone dari GitHub) salah: URL diperlakukan sebagai path filesystem
- Waktu: 2026-10-17
- File/langkah terkait: `autoclip_colab.py` -> `locate_project()` + `ensure_repo()` (P-011)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [colab] === [1/5] Menemukan proyek AUTO CLIP ===
  [colab] Cloning file:///tmp/opencode/gitremote/repo.git -> /tmp/opencode/colab_sim/file:/tmp/opencode/gitremote/autoclip
  [colab] $ git clone --depth 1 file:///tmp/opencode/gitremote/repo.git /tmp/opencode/colab_sim/file:/tmp/opencode/gitremote/autoclip
  Cloning into '/tmp/opencode/colab_sim/file:/tmp/opencode/gitremote/autoclip'...
  fatal: '/tmp/opencode/gitremote/repo.git' does not appear to be a git repository
  fatal: Could not read from remote repository.
  [colab] GAGAL: perintah gagal (exit 128): git clone ...
  ```
- Dugaan penyebab: (a) `locate_project()` melakukan `.resolve()` pada `--repo`, sehingga
  URL `https://github.com/USER/repo.git` diproyeksi jadi path lokal; (b) `ensure_repo()`
  menurunkan folder tujuan dari `project.parent`, sehingga URL ikut jadi bagian path
  (`/content/file:/tmp/.../autoclip` — bukan `/content/autoclip`); (c) `ensure_repo()`
  menambahkan `.git` ke semua URL, padahal URL ber-skema (`file://`, `ssh://`,
  `git@host:`) tidak boleh diubah. Jadi cara paling umum di Colab — `git clone` dari
  GitHub lalu menjalankan skrip — belum benar-benar teruji.
- Status: FIXED (lihat `fix.md` F-012)

## P-013 | unduhan video di Colab terlihat "stuck" (tanpa progress sama sekali)
- Waktu: 2026-10-17
- File/langkah terkait: `src/downloader.py` -> `download()` (opsi yt-dlp), terlihat di
  langkah 1/5 "Mengambil video & mengekstrak audio"
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [colab] === [5/5] Pipeline ===
  [colab] Sumber : https://www.youtube.com/watch?v=k0xC_Y_xYnw
  AUTO CLIP - video panjang -> klip vertikal 9:16 bersubtitle
  ### [1/5] Mengambil video & mengekstrak audio ###
  (selama ini tidak ada output sama sekali; Colab tidak mengatur timeout)
  ```
  Panel file Colab saat itu:
  ```
  temp/
   - source.f616.mp4.part      <- unduhan BERJALAN (bukan macet)
   - source.f616.mp4.ytdl
  ```
- Temuan tambahan: file `temp/source.f616.mp4.part` **bergerak**,
  jadi unduhan berjalan; penyebab utamanya `format: "bv*+ba/best"` memilih video 4K
  (679 MB untuk "Big Buck Bunny") padahal hasil akhir hanya 1080x1920, sehingga lama
  sekali tanpa output.
- Dugaan penyebab: (a) `opts` yt-dlp menyalakan `"quiet": True`, `"no_warnings": True`,
  dan `"noprogress": True`, sehingga baris progress (persentase, kecepatan, ETA) yang
  semula dicetak yt-dlp ke stdout tidak pernah terlihat; (b) `main.py` tidak mencetak
  apa pun di langkah 1 selama menunggu, jadi tidak ada tanda hidup; (c) tidak ada
  `socket_timeout`, jadi koneksi yang macet tidak pernah gagal dengan pesan jelas;
  (d) `format` tanpa batas tinggi memilih varian 4K.
  Efeknya: proses yang sebenarnya sedang bekerja terlihat menggantung.
- Status: FIXED (lihat `fix.md` F-013)

## P-014 | progress unduhan terlalu sering dicetak (1 baris tiap ~2 detik)
- Waktu: 2026-10-17
- File/langkah terkait: `src/downloader.py` -> `make_progress_hook()` + `PROGRESS_INTERVAL`,
  terlihat di langkah 1/5 "Mengambil video & mengekstrak audio" (Colab)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
    [unduh] 81.0%  1.1 GB/1.3 GB  6.3 MB/s  ETA 42s
    [unduh] 82.1%  1.1 GB/1.3 GB  7.2 MB/s  ETA 38s
    [unduh] 83.2%  1.1 GB/1.3 GB  7.9 MB/s  ETA 33s
    [unduh] 84.1%  1.1 GB/1.3 GB  7.2 MB/s  ETA 32s
    ... (17 baris dalam ~30 detik, naik ~1,1% per baris)
    [unduh] 97.3%  1.3 GB/1.3 GB  6.6 MB/s  ETA 8s
  ```
  Keluhan pengguna: "tidak perlu terlalu banyak progres yang keluar".
- Dugaan penyebab: F-013 membuat progress dicetak setiap `PROGRESS_INTERVAL = 2.0` detik
  agar unduhan tidak terlihat "stuck" (P-013). Nilai 2 detik terlalu rapat untuk file besar:
  video 1,3 GB dengan kecepatan ~7 MB/s menghasilkan ~20 baris per menit, jadi output
  Colab jadi penuh dan sulit dibaca. Tidak ada pengaturan apa pun untuk frekuensi ini.
- Status: FIXED (lihat `fix.md` F-014)

## P-015 | transkripsi di Colab gagal: `libcublas.so.12 is not found` (GPU tidak bisa dipakai)
- Waktu: 2026-10-17
- File/langkah terkait: `src/transcriber.py` -> `transcribe()` (loop `for seg in segments_iter`),
  `_resolve_device()`; `autoclip_colab.py` -> `ctranslate2_sees_cuda()` / `run_pipeline_robust()`;
  terlihat di langkah 2/5 "Transkripsi dengan faster-whisper" (Colab, GPU aktif)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  === [2/5] Transkripsi dengan faster-whisper ===
  [transcribe] device=cuda compute_type=float16 model=small
  [transcribe] shim av.open terpasang (av 19.0.1)
  Warning: You are sending unauthenticated requests to the HF Hub. ...
  [ERROR TIDAK TERDUKUR] Library libcublas.so.12 is not found or cannot be loaded
  Traceback (most recent call last):
    File "/content/autoclip/main.py", line 235, in main
      all_outputs.extend(process_one(src, cfg, args, index=i))
    File "/content/autoclip/main.py", line 148, in process_one
      transcript = transcriber.transcribe(
    File "/content/autoclip/src/transcriber.py", line 150, in transcribe
      for seg in segments_iter:  # generator, bisa lambat
    File "/usr/local/lib/python3.13/dist-packages/faster_whisper/transcribe.py", line 1851, in restore_speech_timestamps
      for segment in segments:
    File "/usr/local/lib/python3.13/dist-packages/faster_whisper/transcribe.py", line 1190, in generate_segments
      encoder_output = self.encode(segment)
    File "/usr/local/lib/python3.13/dist-packages/faster_whisper/transcribe.py", line 1400, in encode
      return self.model.encode(features, to_cpu=to_cpu)
  RuntimeError: Library libcublas.so.12 is not found or cannot be loaded
  ```
- Dugaan penyebab (4 lapis, semuanya perlu ditutup):
  1. `for seg in segments_iter` tidak dibungkus try/except, padahal `model.transcribe()`
     mengembalikan generator yang baru benar-benar berjalan saat diiterasi. Galat
     pustaka CUDA muncul di sana, jadi tidak pernah jadi `TranscriptionError`.
  2. Akibat (1), `main.py` jatuh ke catch-all -> `[ERROR TIDAK TERDUKUR]` dan kode
     keluar **1**, padahal fallback CPU di `run_pipeline_robust()` hanya memicu
     kode keluar **4**. Jadi retry CPU tidak pernah terjadi.
  3. `_resolve_device("auto")` hanya mengecek `ctranslate2.get_cuda_device_count() > 0`.
     Fungsi itu tetap mengembalikan 1 walau cuBLAS/torch tidak bisa dimuat, jadi
     program tetap memilih `cuda` lalu crash. `ctranslate2_sees_cuda()` di
     `autoclip_colab.py` punya masalah sama: ia melaporkan "GPU dipakai" padahal
     pustakanya belum termuat.
  4. Tidak ada fallback di dalam `transcribe()`: sekali salah pilih perangkat, proses
     mati total walaupun CPU (int8) selalu bisa jalan.
- Status: FIXED (lihat `fix.md` F-015)

## P-016 | YouTube refusing download: "Sign in to confirm you're not a bot"
- Waktu: 2026-10-17
- File/langkah terkait: `src/downloader.py` -> `download()` (blok `except Exception`),
  langkah 1/5 "Mengambil video & mengekstrak audio" (Colab)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  ERROR: [youtube] wDKyVtbdEsc: Sign in to confirm you're not a bot. Use --cookies-from-browser
  or --cookies for the authentication. See
  https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp for how to
  manually pass cookies. Also see
  https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies for tips on
  effectively exporting YouTube cookies
  [ERROR UNDUH/TRANSKRIPSI] Gagal mengunduh video dari URL ini: ERROR: [youtube] wDKyVtbdEsc:
  Sign in to confirm you're not a bot. ...
  ```
  Keluhan pengguna: "kenapa padahal tadi gak ada" (video yang sama sebelumnya bisa diunduh).
- Dugaan penyebab:
  1. Ini bukan bug kode dan bukan perubahan dari F-014/F-015. YouTube menilai
     reputasi **IP** dan frekuensi request; IP Colab sering sudah ditandai atau diblokir.
     Video yang sebelumnya berhasil dari IP lain, atau sebelum IP kena kuota, jadi
     sekarang ditolak. Terus mencoba video lain hanya akan memperburuk.
  2. `opts` yt-dlp sengaja mengunci `"cookiefile": None` dan tidak pernah mengirim
     `--cookies-from-browser`, jadi ketika YouTube meminta autentikasi tidak ada
     jalur untuk mengirim cookie sama sekali.
  3. Pesan galat tidak dikenali sebagai kasus khusus, sehingga pengguna hanya melihat
     "Gagal mengunduh video dari URL ini" tanpa tahu itu masalah IP/cookie.
- Status: FIXED (lihat `fix.md` F-016)
- Catatan: ini masalah reputasi IP, bukan bug kode. Perbaikannya membuat program
  mengenali kasusnya, mencoba satu jalur tanpa login, lalu berhenti dengan petunjuk
  yang bisa dilakukan user (file lokal / cookie / tunggu / ganti jaringan).

## P-017 | OpenRouter gagal memilih segmen highlight
- Waktu: 2026-10-17 15:26
- File/langkah terkait: langkah 3 (highlight), model=mock/test-model:free
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  Gagal mendapatkan segmen highlight setelah 3 percobaan pada model 'mock/test-model:free'. Error terakhir: HTTPConnectionPool(host='127.0.0.1', port=8792): Max retries exceeded with url: /api/v1/chat/completions (Caused by NewConnectionError("HTTPConnection(host='127.0.0.1', port=8792): Failed to establish a new connection: [Errno 111] Connection refused"))
  ```
- Dugaan penyebab: Model gratis OpenRouter bisa rate limit atau membalas di luar format JSON setelah semua percobaan ulang habis.
- Status: FIXED
- Catatan: entri ini dihapus setelah ditinjau ulang. Semuanya adalah kesalahan
  pengaturan pengujian, bukan masalah program: mock OpenRouter dijalankan di port
  default `8765` sedangkan `tests/.env.test` menunjuk port `8792`
  (`HTTPConnection refused`), dan file `temp/` sengaja dikosongkan sebelum
  pengujian ulang P-016 sehingga `--reuse-transcript` tidak terpakai. Setelah mock
  dijalankan di port yang benar, alur penuh sukses 2 klip. Pelajaran: cek dulu
  apakah alamat/port pada `.env` uji cocok dengan yang dipakai skrip sebelum
  menyimpulkan program rusak.

## P-018 | `main.py --help` crash: `ValueError: incomplete format`
- Waktu: 2026-10-18
- File/langkah terkait: `main.py` -> `parse_args()`, teks bantuan opsi `--progress-seconds`
  (baris ~100)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  $ venv/bin/python main.py --help
  Traceback (most recent call last):
    File "/usr/lib/python3.12/argparse.py", line 298, in _expand_help
      return self._get_help_string(action) % params
             ~~~~~~~~~~~~~~~~~~~^^^^^^^^
  ValueError: incomplete format
  ```
  Gejalanya: `main.py --help` selalu gagal, jadi tidak ada cara melihat daftar opsi
  dari terminal. Semua opsi lain tidak tampil.
- Dugaan penyebab: argparse mem-format setiap teks bantuan dengan operator `%`
  (`help % params`) supaya bisa menulis `%(default)s`. Teks bantuan `--progress-seconds`
  memuat karakter persen biasa untuk menulis "tiap 10%", yaitu:
  `"... (default DOWNLOAD_PROGRESS_SECONDS=15). 0 = hanya tiap 10%."`
  `%` diikuti spasi dianggap format tidak lengkap -> `ValueError`.
  Huruf ini ikut terpasang sejak F-014 (baris progress) tapi tidak ketahuan karena
  `--help` tidak pernah dijalankan setelahnya.
- Status: FIXED (lihat `fix.md` F-018)

## P-019 | Colab: GPU Tesla T4 terdeteksi tapi ctranslate2 tetap turun ke CPU
- Waktu: 2026-10-18
- File/langkah terkait: `autoclip_colab.py` -> `ctranslate2_sees_cuda()` + `setup_cuda_libs()`,
  hasil akhirnya terlihat di `src/transcriber.py` -> `[transcribe] device=cpu compute_type=int8`
  (langkah 2/5, Colab T4, `WHISPER_DEVICE=cpu` tertulis di `.env`)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  Successfully installed av-19.0.1 ctranslate2-4.8.3 faster-whisper-1.2.1 onnxruntime-1.31.0 yt-dlp-2026.8.19
  [colab] GPU terdeteksi: Tesla T4, 15360 MiB
  [colab] PERINGATAN: GPU terdeteksi tapi pustaka CUDA belum termuat -> memasang nvidia-cublas-cu12 dan nvidia-cudnn-cu12
  [colab] Memasang pustaka CUDA untuk ctranslate2...
  [colab] $ /usr/bin/python3 -m pip install -q --disable-pip-version-check nvidia-cublas-cu12 nvidia-cudnn-cu12==9.* nvid...
  [colab] LD_LIBRARY_PATH diset ke 16 folder pustaka NVIDIA
  [colab] PERINGATAN: GPU ada tapi ctranslate2 tidak bisa memakainya -> fallback ke CPU (int8).
  [colab] Transkripsi lebih lambat, tetapi pipeline tetap jalan.
  ```
  Gejalanya: audio 3505 detik diproses di CPU padahal T4 tersedia, padahal
  pustaka CUDA sudah dipasang dan `LD_LIBRARY_PATH` sudah di-set.
- Dugaan penyebab (belum terverifikasi, perlu diagnostik di Colab):
  1. `ctranslate2_sees_cuda()` menggabungkan tiga kemungkinan kegagalan jadi satu
     nilai `False` tanpa alasan: `get_cuda_device_count() == 0`, `libcublas.so.12`
     gagal dimuat, atau `libcudnn.so.9` gagal dimuat. Probe kedua dipanggil dengan
     `quiet=True`, jadi justru saat inilah alasan sebenarnya hilang dari log.
  2. Probe melakukan `ct.get_cuda_device_count()` **lebih dulu**; kalau panggilan itu
     melempar (mis. `libcudart.so.12` tidak ketemu loader), seluruh probe keluar
     non-zero dan hasilnya disamakan dengan "pustaka belum termuat".
  3. `pip install -q` menyembunyikan apakah paket nvidia benar-benar terpasang,
     sehingga tidak ada yang memastikan `import nvidia` di interpreter yang sedang
     berjalan menunjuk folder yang barusan diisi pip.
  4. `ctypes.CDLL("libcudnn.so.9")` ikut gagal kalau salah satu dependensinya
     (mis. `libcublasLt.so.12`) tidak ada di jalur loader, meski cudnn-nya sendiri ada.
- Perbaikan sementara (lihat `fix.md` F-019): `ctranslate2_sees_cuda()` diganti
  `cuda_diagnostics()` + `cuda_ready()` + `explain_cuda_failure()` yang melaporkan
  **penyebab** apa pun yang gagal (jumlah GPU, tiap pustaka + error loader, lokasi
  paket pip), dan `install_cuda_libs()` sekarang memverifikasi hasil pip
  (`import nvidia`) alih-alih `pip -q` yang menutupi kegagalan.
- Cara memastikan akar masalahnya di Colab (sekali jalan, tanpa mengunduh video):
  ```
  !python autoclip_colab.py --check-env
  ```
  Baris `CUDA : siap=... device_count=...` dan daftar pustaka menunjukkan apakah
  masalahnya "GPU tidak terlihat" atau "pustaka tidak termuat".
- Status: OPEN (menunggu hasil `--check-env` di Colab; program sekarang sudah
  menampilkan penyebabnya sendiri)

## P-020 | `--skip-install` memaksa CPU tanpa pernah memeriksa GPU
- Waktu: 2026-10-18
- File/langkah terkait: `autoclip_colab.py` -> `main()` langkah 3/5 "Dependency Python
  + GPU", `setup_cuda_libs()`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [colab] === [3/5] Dependency Python + GPU ===
  [colab] --skip-install: lewati pip install.
  [colab] Mode   : CPU (int8)
  ```
- Gejalanya: di Colab yang pustaka CUDA-nya **sudah** terpasang, menjalankan dengan
  `--skip-install` (dipakai untuk percobaan kedua, hemat waktu) selalu berakhir
  di `Mode : CPU (int8)`, padahal `setup_cuda_libs()` bisa langsung memastikan GPU.
  Tidak ada probe GPU sama sekali pada jalur itu.
- Dugaan penyebab: di `main()`, `--skip-install` tidak hanya melewati `pip install`
  tetapi juga menentukan `gpu = False` secara hard-code, tanpa memanggil
  `setup_cuda_libs()`. Konsekuensinya pengguna tidak punya cara memasang pustaka
  CUDA sekali jalan lalu memakai GPU pada percobaan berikutnya tanpa mengulang
  `apt-get`/`pip install` yang berat.
- Perbaikan (lihat `fix.md` F-020): `setup_cuda_libs(install=True|False)` dan
  `main()` sekarang selalu menjalankan probe GPU; `--skip-install` hanya
  mematikan **pip**, bukan probe. Kalau pustakanya sudah ada, hasilnya
  `Mode : GPU (cuda/float16)`; kalau belum, pesannya menyuruh jalan tanpa
  `--skip-install` sekali saja untuk memasang pustakanya.
- Status: FIXED (lihat `fix.md` F-020)

## P-021 | Colab: `libcublas.so.12` tetap tidak ditemukan padahal paket nvidia terpasang
- Waktu: 2026-10-18
- File/langkah terkait: `autoclip_colab.py` -> `nvidia_lib_dirs()` + `cuda_diagnostics()` +
  `setup_cuda_libs()`, terlihat di langkah 3/5 "Dependency Python + GPU"
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [colab] GPU terdeteksi: Tesla T4, 15360 MiB
  [colab] GPU belum bisa dipakai ctranslate2. Causa yang terdeteksi:
  [colab]   GPU 'Tesla T4, 15360 MiB' terlihat oleh ctranslate2, tapi pustaka CUDA di bawah belum bisa dimuat loader.
  [colab]   Pustaka yang gagal dimuat loader:
  [colab]     - libcublas.so.12: cannot open shared object file: No such file or directory
  [colab]     - libcudart.so.12: cannot open shared object file: No such file or directory
  [colab]     - libcublasLt.so.12: cannot open shared object file: No such file or directory
  [colab]   paket nvidia terpasang di: /usr/local/lib/python3.13/dist-packages/nvidia
  [colab] $ /usr/bin/python3 -m pip install --disable-pip-version-check nvidia-cublas-cu12 nvidia-cudnn-cu12==9.* nvidia-cuda-runtime-cu12 nvidia-cufft-cu12 nvidia-curand-cu12
  [colab] Paket pustaka CUDA terpasang di: /usr/local/lib/python3.13/dist-packages/nvidia
  [colab] LD_LIBRARY_PATH diset ke 16 folder pustaka NVIDIA
  [colab]   (penjelasan diulang dengan hasil yang sama -> tetap CPU)
  ```
  Perhatikan: `libcudnn.so.9` **tidak** ada di daftar gagal (berarti termuat), tetapi
  `libcublas.so.12`, `libcudart.so.12`, `libcublasLt.so.12` gagal.
- Temuan uji mekanismenya di mesin lokal (tidak ada GPU):
  ```
  A: tanpa LD_LIBRARY_PATH                 -> "cannot open shared object file"   (diharapkan)
  B: LD_LIBRARY_PATH diset di shell        -> lib ditemukan, lalu gagal di DEPENDENSINYA
  C: os.environ['LD_LIBRARY_PATH'] di parent -> subprocess        -> lib ditemukan juga
  D: ubah os.environ SETELAH ctypes dipakai -> GAGAL (ld.so membaca LD_LIBRARY_PATH hanya
                                              sekali, saat proses mulai)
  ```
  Kesimpulan: `LD_LIBRARY_PATH` yang diset di `setup_cuda_libs()` **memang** sampai ke
  probe, jadi penyebabnya bukan itu (uji B dan C membuktikan jalurnya bekerja).
- Dugaan penyebab (belum terverifikasi, perlu satu probe tambahan di Colab):
  1. Folder yang dipindai berasal dari `nvidia.__file__` saja. Kalau pip memasang
     paket ke pohon site-packages yang lain (mis. `/root/.local/lib/python3.13/
     site-packages/nvidia`) sementara `import nvidia` menunjuk ke
     `dist-packages/nvidia` yang sudah ada sebelumnya, `nvidia_lib_dirs()` tidak
     pernah melihat file barunya. Ini yang paling mungkin karena lokasi yang
     dicetak tetap `dist-packages/nvidia` sebelum **dan** sesudah `pip install`.
  2. Nama file di dalam folder berbeda dari soname yang dicari: wheel CUDA 13
     (`nvidia-cublas`) menyediakan `libcublas.so.13`, sedangkan ctranslate2 4.8.3
     butuh `.so.12`. Kalau `pip install` deem "already satisfied" oleh versi
     CUDA 13 yang sudah ada, `libcublas.so.12` tidak pernah terpasang.
  3. Loader menolak membuka file itu karena dependensinya belum ada — tapi pesan
     untuk kasus itu menyebut nama dependensinya, bukan nama pustaka yang dicari
     (lihat uji B), jadi kemungkinan ini kecil.
- Perbaikan yang dikerjakan (lihat `fix.md` F-021):
  1. `nvidia_lib_dirs()` memindai **seluruh** `sys.path` (termasuk user site),
     bukan hanya `nvidia.__file__`.
  2. Probe baru melaporkan file yang benar-benar ditemukan per pustaka
     (`libcublas.so*` di folder mana) dan mencoba memuatnya lewat path absolut,
     sehingga "tidak ada" vs "ada tapi gagal dimuat" tidak lagi tertukar.
  3. Kalau soname tidak ketemu tapi file-nya ada, pustaka itu dimuat paksa dengan
     `RTLD_GLOBAL` dari path absolut, lalu `ctranslate2` memakainya tanpa perlu
     mencariname lewat loader lagi.
- Cara memastikan di Colab:
  ```
  !python autoclip_colab.py --check-env
  ```
- Status: OPEN

## P-022 | model `openrouter/free` ditolak padahal gratis
- Waktu: 2026-10-18
- File/langkah terkait: `autoclip_colab.py` -> `resolve_env()` (pengecekan `:free`)
  dan `src/config.py` -> `_validate()`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [colab] GAGAL: OPENROUTER_MODEL='openrouter/free' tidak berakhiran ':free'.
    Proyek ini hanya mengizinkan model GRATIS. Daftar model gratis:
    https://openrouter.ai/models?max_price=0
  ```
  Program berhenti sebelum pipeline jalan sama sekali.
- Dugaan penyebab:
  1. Aturan proyek (P-010) hanya menguji sufiks `:free`. `openrouter/free` adalah
     **router** OpenRouter yang memang hanya meneruskan ke varian gratis, jadi ia
     tidak memakai kuota berbayar meski tidak berakhiran `:free`. Cek sufiks saja
     membuat model yang paling aman justru tertolak.
  2. Pesan error tidak memberi alternatif yang bisa langsung dipakai, jadi pengguna
     hanya melihat "tidak berakhiran ':free'" tanpa pilihan lain.
  3. Pengecekan ada di dua tempat (`autoclip_colab.py` dan `src/config.py`) sehingga
     perbaikannya harus dilakukan dua kali agar tidak berbeda perilaku.
- Perbaikan (lihat `fix.md` F-022): `src/config.py` menyimpan
  `FREE_ROUTER_MODELS = {"openrouter/free"}` + helper `model_is_free()`; kedua tempat
  memakainya, dan pesan error kini menyarankan model gratis yang valid.
- Status: FIXED (lihat `fix.md` F-022)

## P-023 | penulisan `.env` di Colab membuang kunci yang tidak ada di `ENV_ORDER`
- Waktu: 2026-10-19
- File/langkah terkait: `autoclip_colab.py` -> `resolve_env()` (blok penulisan
  `.env`) + `ENV_ORDER`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  # .env SEBELUM (13 baris, hasil salinan .env.example):
  OPENROUTER_API_KEY=...
  OPENROUTER_MODEL=...
  ...
  MAX_SOURCE_HEIGHT=1080
  DOWNLOAD_PROGRESS_SECONDS=15
  YT_COOKIES_FILE=

  # .env SESUDAH ditulis autoclip_colab.py (12 baris):
  # .env untuk AUTO CLIP (dibuat oleh autoclip_colab.py)
  OPENROUTER_API_KEY=...
  ...
  FACE_TRACKING=false
  # -> MAX_SOURCE_HEIGHT, DOWNLOAD_PROGRESS_SECONDS, YT_COOKIES_FILE HILANG
  ```
- Dugaan penyebab: `ENV_ORDER` hanya berisi 11 kunci (dari `OPENROUTER_API_KEY` sampai
  `FACE_TRACKING`), sedangkan `.env.example` (dan `src/config.py`) sudah punya 3 kunci
  tambahan: `MAX_SOURCE_HEIGHT`, `DOWNLOAD_PROGRESS_SECONDS`, `YT_COOKIES_FILE`.
  Penulis `.env` hanya menulis kunci yang ada di `ENV_ORDER`, jadi nilai pengguna di
  kunci lain **dihapus tanpa jejak** setiap kali runner menulis ulang `.env`.
  Akibatnya, mis. `MAX_SOURCE_HEIGHT=720` yang dirapikan pengguna hilang dan unduhan
  kembali ke 1080p.
- Perbaikan (lihat `fix.md` F-023): `ENV_ORDER` dilengkapi dengan semua kunci yang
  dipakai `src/config.py`, dan penulis `.env` mempertahankan kunci tambahan milik
  pengguna (yang tidak dikenal program) alih-alih membuangnya.
- Status: FIXED (lihat `fix.md` F-023)

## P-024 | retry verifikasi bot memakai satu permintaan gabungan `player_client=tv,ios`
- Waktu: 2026-10-19
- File/langkah terkait: `src/downloader.py` -> `download()` (blok retry bot check) +
  `BOT_CHECK_FALLBACK_CLIENTS`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [unduh] kalau lama tidak bergerak, cek ukuran file .part di folder temp/; tekan Ctrl+C untuk membatalkan
  ERROR: [youtube] dE3ReotqynY: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the authentication. See ...
    [unduh] YouTube meminta verifikasi bot (IP ini ditandai).
    [unduh] mencoba ulang dengan player client: tv,ios
  ERROR: [youtube] dE3ReotqynY: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the authentication. See ...
  ```
  Di Colab, video yang tadinya bisa diunduh kembali ditolak dengan verifikasi bot.
- Dugaan penyebab:
  1. Verifikasi bot ini memang ada di luar kendali program (reputasi IP Colab), dan
     cookie lokal tidak tersedia di Colab — itu tidak bisa diperbaiki di kode.
  2. Yang **bisa** diperbaiki: percobaan ulang dilakukan sekali dengan
     `player_client=tv,ios` dalam satu permintaan. Kalau `tv` sendiri yang ditolak
     (mis. versi yt-dlp tertentu tidak mendukungnya), `ios` yang sebenarnya bisa
     lolos ikut gagal karena keduanya disatukan. Program jadi tidak tahu client mana
     yang masih layak dicoba, dan pengguna tidak diberi perintah yang bisa langsung
     dijalankan.
  3. Pesan galat yang muncul di log adalah output yt-dlp mentah; program belum
     menambahkan daftar per client yang sudah dicoba ke pesan akhirnya.
- Perbaikan (lihat `fix.md` F-024):
  1. Retry dilakukan **per client** (`tv`, lalu `ios`, lalu `web_safari`), bukan satu
     permintaan gabungan, dan tiap percobaan dicetak terpisah.
  2. `BotCheckError` memuat daftar client yang sudah dicoba + perintah siap tempel
     untuk menguji client lain secara manual + opsi cookie/file lokal.
  3. `BOT_CHECK_FALLBACK_CLIENTS` dapat dikonfigurasi lewat env `YT_PLAYER_CLIENTS`
     (mis. `tv,ios,web_safari,mweb`) tanpa mengubah kode.
- Status: FIXED (lihat `fix.md` F-024)

## P-025 | unduhan yang dulu berhasil kini kena verifikasi bot (regresi lingkungan, bukan kode)
- Waktu: 2026-10-19
- File/langkah terkait: `src/downloader.py` -> `build_ydl_opts()`/opts yt-dlp
  (`js_runtimes`, `extractor_args`), `requirements.txt` (`yt-dlp>=2025.1.1`)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  ERROR: [youtube] dE3ReotqynY: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the authentication.
    [unduh] YouTube meminta verifikasi bot (IP ini ditandai).
    [unduh] mencoba ulang dengan player client: tv
  ERROR: [youtube] dE3ReotqynY: Sign in to confirm you’re not a bot. ...
  ```
  Keluhan pengguna: "sebelumnya tanpa gitu bisa, 2 atau 1 versi sebelum perubahan terakhir".
- Pemeriksaan apakah kode saya penyebabnya (jawaban: **bukan**):
  ```
  $ git diff e8a9caa..HEAD -- src/downloader.py | grep -E 'format|outtmpl|merge_output|quiet|noprogress|retries|socket|cookiefile'
  # tidak ada perubahan pada permintaan unduhan pertama
  ```
  Opsi permintaan pertama (format, outtmpl, merge, quiet, retries, socket_timeout,
  cookiefile) **identik** dengan versi sebelum F-016. Semua perubahan saya hanya menambah
  percobaan SETELAH bot check terjadi, jadi tidak mungkin menyebabkan permintaan
  pertama ditolak.
- Temuan dari kode yt-dlp yang terpasang (2026.8.19):
  ```
  _DEFAULT_CLIENTS        = ('visionos', 'web')
  _DEFAULT_JSLESS_CLIENTS = ('visionos',)
  self.params['js_runtimes'] = self.params.get('js_runtimes', {'deno': {}})
  # hanya 'deno' yang aktif secara bawaan; node/bun/quickjs harus diaktifkan manual
  # yt-dlp sendiri memakai kombinasi ini untuk video uji YouTube-nya:
  'extractor_args': {'youtube': {'player_client': ['ios'], 'player_skip': ['webpage']}}
  ```
- Dugaan penyebab (sangat mungkin, belum 100% terverifikasi di Colab):
  1. `requirements.txt` memakai `yt-dlp>=2025.1.1` **tanpa batas atas**, jadi setiap
     runtime Colab baru memasang yt-dlp terbaru (2026.8.19). Perilaku default client
     YouTube berubah beberapa kali dalam 2025-2026.
  2. Hanya `deno` yang aktif secara bawaan, sedangkan Colab **tidak punya deno**
     (tapi punya Node.js v20). Tanpa runtime JS, yt-dlp menyempitkan client default
     ke `visionos` saja (`_DEFAULT_JSLESS_CLIENTS`), yaitu client yang paling sering
     kena verifikasi bot.
  3. Permintaan *watch page* (HTML) adalah pemicu umum verifikasi bot. yt-dlp
     sendiri menghindari ini dengan `player_skip=webpage`. Hipotesis ini sempat
     dicoba, lalu dibantah oleh bukti lapangan (lihat di bawah).
- Bukti lapangan (diuji langsung ke YouTube dari mesin ini, video Big Buck Bunny):
  ```
  [OK ] default + node                                  -> judul terbaca, 53 format
  [OK ] default tanpa runtime JS                         -> judul terbaca, 53 format
  [OK ] player_client=tv          (tanpa skip webpage)  -> OK
  [OK ] player_client=tv_simply   (tanpa skip webpage)  -> OK
  [OK ] player_client=ios          (tanpa skip webpage)  -> OK
  [OK ] player_client=mweb         (tanpa skip webpage)  -> OK
  [OK ] player_client=android_vr   (tanpa skip webpage)  -> OK
  [OK ] player_client=web_embedded (tanpa skip webpage)  -> OK
  [OK ] player_client=web_safari   (tanpa skip webpage)  -> OK
  [OK ] player_client=visionos     (tanpa skip webpage)  -> OK
  [GAGAL] player_client=tv         + player_skip=webpage -> BOT-CHECK
  [GAGAL] player_client=android_vr + player_skip=webpage -> BOT-CHECK
  ```
  Kesimpulan: hipotesis butir 3 **SALAH** untuk kasus kita. `player_skip=webpage`
  justru memicu verifikasi bot (tanpa data halaman watch, client butuh PO token).
  Yang benar: memaksa `player_client` **tanpa** `player_skip`.
  Unduhan penuh dengan program kita juga berhasil: `source.mp4`, 1280x720, 635 detik,
  81,6 MB, dengan log `runtime JS: node`.
- Kesimpulan akhir: program kita sehat (terbukti unduhan nyata sukses). Kegagalan di
  Colab adalah **reputasi IP** runtime tersebut, bukan regresi kode. Perbaikan yang
  tetap berguna: menyalakan runtime JS (client default tidak menyempit) dan memberi
  daftar client yang luas untuk dicoba.
- Perbaikan (lihat `fix.md` F-025):
  1. `detect_js_runtimes()` menyalakan runtime JS yang tersedia (`node`, `deno`, `bun`)
     lewat opts `js_runtimes`, sehingga client default yt-dlp tidak menyempit ke
     `visionos` dan solver EJS ikut aktif (env `YT_JS_RUNTIMES` untuk mengoverride).
  2. Percobaan ulang memakai `player_client=<client>` **tanpa** `player_skip=webpage`
     (berdasarkan matriks bukti di atas), dengan daftar client
     `tv`, `tv_simply`, `ios`, `mweb` (dapat diatur lewat `YT_PLAYER_CLIENTS`).
  3. Pesan kesalahan menjelaskan bahwa `player_skip=webpage` **tidak boleh** dipakai.
- Status: FIXED (lihat `fix.md` F-025)

## P-026 | subtitle klip: cue overlap dan teks keluar frame
- Waktu: 2026-10-19
- File/langkah terkait: `src/subtitles.py` -> `group_cues()`, `_split_lines()`,
  `write_ass()` (header `ASS_HEADER`); hasil bake di `output/*.ass` + `output/*.mp4`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  a) dua teks tampil bersamaan (subtitle saling menumpuk)
  b) sebagian teks keluar frame (terpotong di kiri/kanan/bawah)

  # .ass hasil run terakhir (output/01_testvideo-id_klip1_...scrol.ass)
  Style: Default,DejaVu Sans,88,&H00FFFFFF,...,1,6,3,2,90,90,420,1
  Dialogue: 0,0:00:19.84,0:00:21.64,Default,,0,0,0,,So, we ditched it\Nto throw everything away and
  Dialogue: 0,0:00:23.80,0:00:26.14,Default,,0,0,0,,Ito as formon, and\Nhonestly, the first to mon
  ```
- Bukti pengukuran (libass render di atas latar hitam, 1080x1920):
  ```
  s0.6.png   x=49..1029   (lebar  980px)   y=1337..1497
  s20.2.png  x=13..1068   (lebar 1055px)   y=1336..1498
  s24.2.png  x=1..1078    (lebar 1077px)   TERPOTONG KIRI + TERPOTONG KANAN
  s5.5.png   x=0..1079    (lebar 1079px)   TERPOTONG KIRI + TERPOTONG KANAN
  ```
  Lebar area teks yang tersedia = 1080 - MarginL 90 - MarginR 90 = **900px**.
  Lebar baris di file .ass (DejaVu Sans Bold 88px, diukur dengan PIL):
  ```
  'to throw everything away and'  -> 1492,8 px  (28 karakter)  LEBIH
  'bag, that is an architektura'   -> 1367,8 px  (28 karakter)  LEBIH
  'Nophaya nimadia complete'       -> 1349,9 px  (24 karakter)  LEBIH
  'Every senior developer'         -> 1144,4 px  (22 karakter)  LEBIH
  ```
  Bahkan baris 22 karakter (batas `MAX_CHARS_PER_LINE`) sudah **1144px > 900px**.
- Bukti overlap cue (timestamp kata tumpang tindih, hal yang memang terjadi di
  transkripsi kata Whisper):
  ```
  words: a*30 (0.00-0.50), b*30 (0.40-0.90), c*20 (0.90-1.20)
  cue 0.00-0.50 : 'aaaa...'      cue 0.40-0.90 : 'bbbb...'   <- OVERLAP 0,10 detik
  ```
  Dua cue aktif bersamaan -> dua teks tampil bersamaan.
- Dugaan penyebab (pasti, sudah terverifikasi di atas):
  1. `group_cues()` memakai `end = kata terakhir` dan `start = kata berikutnya` tanpa
     pernah memastikan `start_cue_berikut >= end_cue_sebelumnya`. Saat dua kata
     tumpang tindih (percakapan cepat), cue overlap -> dua teks aktif bersamaan.
  2. Batas lebar pakai **jumlah karakter** (`MAX_CHARS_PER_LINE = 22`,
     `MAX_CHARS_PER_CUE = 46`), bukan lebar piksel. Dengan FontSize 88 dan margin
     90, lebar yang tersedia hanya 900px, sedangkan 22 karakter = 1144px. Semua
     batas karakter terlalu longgar -> teks terpotong di kiri/kanan.
  3. `_split_lines()` bisa **melewati** batasnya sendiri: kalau tidak ada titik potong
     yang seimbang, fallback memotong di tengah -> baris jadi 27-28 karakter
     (1492px), jelas keluar frame.
  4. `MAX_CHARS_PER_CUE = 46` tidak konsisten dengan 2 x 22 karakter, sehingga satu
     cue bisa berisi 46 karakter dalam satu baris (2100px).
  5. Margin kiri/kanan 90px (kebutuhan 60-80px) dan FontSize 88 (terlalu besar untuk
     2 baris muat di 900px) memperbesar masalah.
  6. Tidak ada pengukuran font sama sekali: program tidak tahu berapa px sebuah baris.
     Pillow (PIL) belum menjadi dependensi (hanya ikut matplotlib).
- Perbaikan (lihat `fix.md` F-026):
  1. `measure_text_width()` mengukur lebar teks dengan Pillow + font DejaVu Sans Bold
     yang sama dengan yang dipakai libass; ada estimator cadangan bila Pillow tidak
     terpasang, dan `pillow` ditambahkan ke `requirements.txt`.
  2. `_split_lines()` memakai lebar piksel: wrap maksimal 2 baris, titik potong
     seimbang, dan kata yang terlalu panjang dipotong per karakter.
  3. `group_cues()` divisive cue berdasarkan lebar (2 baris muat) dan
     **menjamin tidak ada overlap**: `start` cue berikutnya dipaksa >= `end` cue
     sebelumnya, cue diurutkan, durasi minimum dijaga.
  4. Header .ass: `PlayResX/Y` 1080/1920, `FontSize` 72, `MarginL/MarginR` 80,
     `MarginV` 420 (di atas area UI platform), `WrapStyle` 2 (kita wrap sendiri).
  5. Test baru `tests/test_subtitles.py`: tidak ada overlap, maksimal 2 baris, lebar
     tiap baris <= area teks, header benar, dan render nyata diuji ke frame video.
- Status: FIXED (lihat `fix.md` F-026)

## P-027 | belum ada fitur menggabungkan semua klip jadi satu video
- Waktu: 2026-10-19
- File/langkah terkait: `main.py` (CLI + alur), `src/config.py` (kunci `.env`),
  `autoclip_colab.py` (penulis `.env` + zip/Drive), modul baru `src/merger.py`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  # bukan error: permintaan fitur
  # "setelah semua klip selesai, gabungkan semua .mp4 di output/ berurutan menjadi
  #  satu file, misalnya output/00_<judulvideo>_gabungan.mp4"
  ```
- Dugaan penyebab / kebutuhan:
  1. Program hanya menghasilkan klip terpisah; tidak ada cara mendapatkan satu file
     berisi semua klip untuk diunggah ulang.
  2. `.env` belum punya kunci `MERGE_CLIPS`, dan `ENV_ORDER` di runner Colab juga
     belum memuatnya — kalau tidak dijaga, setting baru bisa hilang saat `.env`
     ditulis ulang (pola yang sama seperti P-023).
  3. Penggabungan harus aman: kalau klipnya cuma satu atau FFmpeg gagal, file klip
     individual **tidak boleh** hilang, dan hasilnya harus diverifikasi (stream
     video + audio) sebelum dianggap sukses.
- Perbaikan (lihat `fix.md` F-027):
  1. `src/merger.py`: `merge_clips()` memakai demuxer concat FFmpeg + encode ulang
     (libx264 + aac, fps 30, skala/pad ke 1080x1920), memverifikasi hasilnya dengan
     ffprobe (harus ada stream video DAN audio), dan tidak pernah menghapus klip.
  2. `main.py`: `--merge` / `--no-merge`, plus langkah penggabungan setelah semua
     klip selesai; file named `00_<slug>_gabungan.mp4`.
  3. `src/config.py`: `MERGE_CLIPS` (default false) + tampilannya di
     `public_summary()`.
  4. `autoclip_colab.py`: `MERGE_CLIPS` masuk `DEFAULTS`/`ENV_ORDER`; file gabungan
     otomatis ikut tersalin ke `--drive-dir` dan masuk zip hasil.
  5. `tests/test_merge.py` (baru, 6 bagian).
- Status: FIXED (lihat `fix.md` F-027)

## P-028 | face tracking tidak akurat (wajah keluar frame saat orang bergerak)
- Waktu: 2026-10-22 00:45
- File/langkah terkait: `src/clipper.py` -> `_face_x_center()` + `face_crop_filter()`,
  langkah 4/5 "Membuat subtitle dan memotong klip 9:16" (`FACE_TRACKING=true`)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  Keluhan pengguna: "face tracking kurang akurat"

  # Uji: video 1280x720, 8 detik, wajah bergerak x=80 -> x=900 (102,5 px/detik)
  $ venv/bin/python -c "... _face_x_center(v, 0.0, 8.0) ..."
  LAMA: pusat wajah (0..1) = 0.5142578125 -> crop diam di tengah
  LAMA: filter = scale=3414:1920,crop=1080:1920:1216:0,setsar=1

  # posisi wajah di frame hasil render (0.5 = tengah frame; 1080 px = 1.0):
  t=0.0s  WAJAH TIDAK TERDETEKSI
  t=1.0s  WAJAH TIDAK TERDETEKSI
  t=2.0s  WAJAH TIDAK TERDETEKSI
  t=3.0s  cx=0.233
  t=4.0s  cx=0.489
  t=5.0s  cx=0.741
  t=6.0s  WAJAH TIDAK TERDETEKSI
  t=7.0s  WAJAH TIDAK TERDETEKSI
  ```
  Wajah hilang dari frame selama +/- 5 detik dari klip 8 detik (oleh karena itu
  "kurang akurat" padahal program tidak error sama sekali).
- Dugaan penyebab:
  1. **Crop-nya diam, bukan pelacak yang bergerak.** `_face_x_center()` menghitung
     **median** dari 7 sampel posisi wajah, lalu `face_crop_filter()` memakai
     **satu** nilai `x` statis untuk seluruh durasi klip. Orang yang bergerak
     (atau kamera yang berputar) langsung keluar dari jendela crop.
  2. **Sampel terlalu jarang dan tidak presisi.** 7 titik per klip (jarak ~1,1
     detik) memakai `cap.set(CAP_PROP_POS_FRAMES)` untuk tiap sampel, jadi
     posisi frame bisa meleset ke frame terdekat.
  3. **Tidak ada konsistensi temporal.** Semua wajah yang terdeteksi (bisa lebih
     dari satu orang, atau false positive Haar) langsung masuk ke perhitungan
     median, sehingga hasil bisa berayun antar orang.
  4. **Tidak ada perataan lintasan**, jadi kalau nanti crop digerakkan, semua
     guncangan noise ikut terbawa.
  5. **Detektor Haar frontal saja.** Wajah miring/profil, wajah kecil, dan
     pencahayaan buruk gagal dideteksi; `cv2 5.0` bahkan sudah tidak
     menyertakan cascade `.xml` (lihat P-006), jadi program hanya bisa
     mengandalkan berkas `assets/`.
  6. **Tidak ada batas kecepatan gerak crop**, jadi lonjakan deteksi sesaat
     (salah deteksi) akan membuat kamera terlempar.
- Perbaikan (lihat `fix.md` F-028):
  1. `src/face_track.py` (baru): deteksi wajah per sampel waktu dengan **YuNet**
     (DNN, model ONNX 227 KB di `assets/`, Haar cascade sebagai cadangan),
     pemilihan wajah yang konsisten antar waktu, pengisian celah, dan perataan
     lintasan (median + rata-rata bergerak).
  2. Jendela crop **bergerak**: lintasan diubah menjadi perintah `sendcmd`
     (`<waktu> crop x <nilai>;`) untuk filter `crop` FFmpeg, jadi wajah
     dikejar ke tengah frame sepanjang klip — bukan satu posisi diam.
  3. Sumber portrait dilacak **vertikal** (wajah di 1/4 tinggi frame, bukan
     tengah) supaya ada ruang untuk subtitle.
  4. Fallback tetap ada: wajah tidak terdeteksi -> crop tengah; render gagal
     -> crop tengah; tidak ada model -> crop tengah.
  5. Kunci `.env` baru: `FACE_TRACK_SAMPLE_FPS`, `FACE_TRACK_SMOOTH`,
     `FACE_DETECT_WIDTH` (juga masuk `DEFAULTS`/`ENV_ORDER` runner Colab).
  6. `tests/test_face_tracking.py` (baru, 7 bagian).
- Status: FIXED (lihat `fix.md` F-028)

## P-029 | file hasil face tracking 3x lebih besar karena crop "goyang" 1-2 piksel
- Waktu: 2026-10-22 01:45
- File/langkah terkait: `src/face_track.py` -> `write_sendcmd()` (deadband),
  `src/clipper.py` -> `plan_face_crop()`, langkah 4/5 potong klip
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  # bukan error: ukuran file hasil naik drastis
  # video uji 1280x720, wajah DIAM (tidak bergerak), 38 detik klip
  # sebelum deadband:
  output/01_testvideo-id-face_klip1_....mp4   9.2 MB
  # sesudah deadband:
  output/01_testvideo-id-face_klip1_....mp4   2.9 MB
  ```
  Wajahnya tetap sama persis di tengah frame (cx 0,494..0,506 di kedua kasus),
  jadi bukan soal akurasi — tapi ukuran file naik 3x dan tiap frame harus
  di-encode ulang karena posisinya bergeser 1-2 piksel tiap sampel.
- Dugaan penyebab: `write_sendcmd()` memakai deadband 1 piksel **di ruang
  koordinat hasil scale** (yang untuk 1280x720 adalah 3414 piksel lebar, jadi
  1 piksel hasil scale = 0,37 piksel sumber). Noise deteksi wajah ±1-2 piksel
  selalu melewati deadband itu, jadi crop berpindah-pindah terus. Setiap
  pergeseran minuscule memaksa encoder membuat makroblok baru -> CRF 20 di
  frame 1080x1920 jadi jauh lebih boros.
- Perbaikan (lihat `fix.md` F-029).
- Status: FIXED (lihat `fix.md` F-029)

## P-030 | model gabungan 9router ditolak karena tidak berakhiran `:free`
- Waktu: 2026-10-27
- File/langkah terkait: `src/config.py` -> `_validate()` (+ `model_is_free()`),
  `autoclip_colab.py` -> `resolve_env()` (+ `colab_model_is_free()`),
  `src/highlight.py` -> `_call_once()`, `OPENROUTER_BASE_URL` di `.env`
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [KONFIGURASI BELUM LENGKAP] OPENROUTER_MODEL='<nama-combo-9router>' tidak berakhiran ':free'.
  Proyek ini hanya mengizinkan model GRATIS. Ganti nilainya di .env dengan nama model
  yang berakhiran ':free' (contoh: 'google/gemini-2.0-flash-exp:free').
  ```
  Padahal `OPENROUTER_BASE_URL` sudah diarahkan ke gateway 9router
  (`http://localhost:20128/v1` atau URL ngrok). Program berhenti sebelum pipeline jalan.
- Dugaan penyebab:
  1. Penegakan model gratis (P-010/P-022) hanya mengenal dua bentuk: sufiks `:free`
     dan router `openrouter/free`. Model yang disajikan gateway OpenAI-compatible
     milik pengguna (9router) memakai nama provider/combo apa adanya, jadi tidak
     pernah lolos.
  2. Pengecekan tidak melihat `OPENROUTER_BASE_URL`, padahal endpoint-nya sudah bukan
     OpenRouter resmi. Akibatnya aturan yang seharusnya melindungi kuota OpenRouter
     ikut memblokir endpoint lokal/tunnel milik pengguna.
  3. Pengecekan ada di dua tempat (`src/config.py` dan `autoclip_colab.py`) sehingga
     keduanya harus diubah dengan aturan yang sama.
  4. Timeout LLM masih hard-code 120 detik, padahal combo 9router dengan fallback
     bisa lebih lama; respons error gateway juga bisa datang dengan HTTP 200
     (`{"error": ...}`) tanpa `choices`, yang pesannya belum jelas.
- Perbaikan (lihat `fix.md` F-030): pengecekan `:free` hanya berlaku untuk
  OpenRouter resmi (`is_openrouter()`); gateway sendiri memakai model apa adanya
  lewat `model_is_free(model, base_url)`; `OPENROUTER_TIMEOUT` bisa diatur; pesan
  error menyebut host endpoint dan menangani respons error gateway dengan jelas.
- Status: FIXED (lihat `fix.md` F-030)

## P-031 | proxy membalas SSE/stream walau `stream=false` + halaman peringatan ngrok
- Waktu: 2026-10-28
- File/langkah terkait: `src/highlight.py` -> `_call_once()` (permintaan
  `POST {base_url}/chat/completions`), endpoint gateway OpenAI-compatible
  (9router via `localhost:20128` atau tunnel ngrok)
- Pesan error / gejala (salin apa adanya, tanpa API key):
  ```
  [highlight] percobaan 1/3 gagal: Respons <host> bukan JSON: data: {"id":"...","choices":[{"delta":{"content":"...
  ```
  atau body berisi halaman HTML peringatan ngrok (`<html>ngrok warning</html>`)
  sehingga dianggap "bukan JSON" walau HTTP 200.
- Dugaan penyebab:
  1. Sebagian proxy/gateway memaksa streaming meski permintaan tidak meminta
     (`stream` tidak dikirim / diabaikan), jadi body balasan berupa SSE
     (`data: {...}` per baris + `data: [DONE]`), bukan satu objek JSON.
  2. `resp.json()` langsung dipakai tanpa cadangan, sehingga body SSE selalu
     dianggap gagal parse.
  3. Endpoint lewat tunnel ngrok mengembalikan halaman peringatan browser untuk
     klien tanpa header khusus; header `ngrok-skip-browser-warning` belum dikirim.
- Perbaikan (lihat `fix.md` F-031).
- Status: FIXED (lihat `fix.md` F-031)
