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
