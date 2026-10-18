# fix.md — jurnal perbaikan AUTO CLIP

> Aturan: TULIS entri di sini **SETELAH** masalah di `problem.md` berhasil diperbaiki
> dan diuji ulang. Format: `## F-XXX | memperbaiki P-XXX`

## F-001 | memperbaiki P-ENV
- Perubahan (file dan apa yang diubah):
  - `AGENTS.md`: bagian LINGKUNGAN ditulis ulang sesuai kondisi nyata (lokal, bukan
    Colab; tanpa GPU; `venv/bin/python`; RAM 4 GB).
  - `src/config.py`: `WHISPER_COMPUTE_TYPE=auto` sudah otomatis memilih `int8` untuk CPU
    dan `float16` untuk CUDA (lihat `transcriber._resolve_compute_type`), jadi tidak perlu
    di-hardcode.
- Alasan: asumsi awal salah (mengira Colab) bisa menyebabkan pemilihan device/compute type
  yang salah dan pemakaian RAM berlebihan untuk model Whisper.
- Hasil pengujian ulang: `pip install -r requirements.txt` sukses di venv Python 3.12
  (faster-whisper 1.2.1, ctranslate2 4.8.3, mediapipe 1.1.1, yt-dlp 2026.8.19,
  openai 3.33.0, opencv 5.0.0.93, numpy 2.5.4). `ffmpeg`/`ffprobe` terdeteksi di PATH.
  Konsekuensi: pakai model Whisper `small` dengan int8 agar muat di RAM 4 GB.

## F-002 | memperbaiki P-002
- Perubahan (file dan apa yang diubah):
  - `src/highlight.py`: tambah fungsi `_scan_array_span()` yang memindai '[' ... ']' dengan
    memperhitungkan string & escaped quote, lalu `_extract_array()` mencoba kandidat secara
    berurutan: (1) array tertutup rapi saja, (2) teks penuh dari '[', (3) teks penuh +
    pelengkap kurung (`_balance`).
- Alasan: model gratis sering membungkus jawaban dengan kalimat pembuka/penutup sehingga
  JSON tidak bisa di-`loads` langsung. Memotong tepat pada ']' penutup memisahkan array
  dari teks sampingan tanpa mengubah isi JSON.
- Hasil pengujian ulang: 8 kasus uji parser semua benar —
  `fenced`, `with_prefix_suffix` (sebelumnya None), `trailing_hope`, `truncated`,
  `nested_bracket_in_str`, `wrapped_dict`, `garbage` (tetap None, benar), `empty` (→ []).
  Validasi: overlap dibuang, `start` > durasi video dibuang, nilai non-numerik dibuang.

## F-003 | memperbaiki P-001 (sumber video uji)
- Perubahan (file dan apa yang diubah):
  - `make_test_video.py` (file baru, alat uji): 4 bagian narasi Bahasa Indonesia
    disintesis dengan `edge-tts` (suara `id-ID-ArdiNeural`), digabung dengan `ffmpeg`,
    lalu dipadukan dengan video pola `testsrc2` 1280x720.
- Alasan: butuh video uji 1-3 menit dengan suara Indonesia yang ground truth-nya diketahui,
  supaya hasil transkripsi bisa diperiksa ketepatannya.
- Hasil pengujian ulang: `input/testvideo_id.mp4` — 72,2 detik, 1280x720, 23,0 MB,
  4 segmen narasi (hook + 3 topik). Transkripsi whisper cocok dengan naskah.

## F-004 | memperbaiki P-003 (kompatibilitas faster-whisper + PyAV)
- Perubahan (file dan apa yang diubah):
  - `src/transcriber.py`: tambah `_patch_av_compat()` yang dipanggil sekali saat import.
    Fungsi ini membungkus `av.open` sehingga argumen `metadata_errors` yang tidak
    dikenali dibuang (di-drop) sebelum diteruskan ke PyAV asli.
- Alasan: `av 19.0.1` menghapus parameter `metadata_errors` yang masih dipakai
  faster-whisper 1.2.1. Mem-pin versi `av` hanya memindahkan masalah (rentang
  inkompatibilitas lain bisa muncul), sedangkan shim aman untuk semua versi.
  `inspect.signature` tidak bisa dipakai karena `av.open` adalah built-in C
  (ValueError: no signature found), jadi kompatibilitas dideteksi dengan memanggil
  `av.open(b"", mode="r", metadata_errors="ignore")` dan menangkap `TypeError`.
- Hasil pengujian ulang: `shim av.open terpasang (av 19.0.1)`; `decode_audio()` berhasil
  -> ndarray float32 1.155.755 sampel (72,23 detik). Transkripsi penuh berhasil:
  23 segmen, 213 kata, bahasa `id` (confidence 1,0), timestamp per kata tersimpan.

## F-005 | memperbaiki P-004 (sumber foto wajah untuk uji)
- Perubahan (file dan apa yang diubah):
  - `assets/haarcascade_frontalface_default.xml` (baru, 930 KB): cascade Haar frontal
    dari repo resmi `opencv/opencv`.
- Alasan: untuk menguji face tracking dibutuhkan gambar berisi wajah; URL Wikimedia yang
  dicoba pertama salah nama file. Cascade Haar juga langsung dipakai sebagai detector
  (lihat F-006).
- Hasil pengujian ulang: cascade termuat (`loaded: True`), wajah terdeteksi pada 30/30
  frame video uji, rasio pusat-x 0,282 (wajah memang diletakkan di kiri, bukan tengah).

## F-006 | memperbaiki P-006 (MediaPipe 1.x tidak punya `solutions`)
- Perubahan (file dan apa yang diubah):
  - `src/clipper.py`: ganti detektor MediaPipe dengan Haar cascade OpenCV.
    Fungsi baru `_cascade_path()` mencari cascade di paket `cv2` lalu di `assets/`;
    `_face_x_center()` memakai `cv2.CascadeClassifier` + median posisi-x dari 7 sampel
    frame, dan tidak lagi menelan error secara diam-diam (setiap kegagalan di-`print`
    lalu jatuh ke crop tengah).
  - `requirements.txt`: `mediapipe` dihapus dari daftar wajib.
- Alasan: `mediapipe 1.1.1` sudah menghapus modul `mediapipe.solutions` sama sekali
  (`AttributeError: module 'mediapipe' has no attribute 'solutions'`), dan `cv2 5.0`
  juga tidak lagi menyertakan berkas `.xml` cascade. Haar cascade bawaan OpenCV
  butuh nol unduhan model dan tetap open source.
- Hasil pengujian ulang: pada `temp/facevideo.mp4` (wajah di x≈0,28 dari lebar),
  `_face_x_center` mengembalikan `0.282`; filter berubah dari crop tengah
  (`crop=...:1167:0`) menjadi `crop=1080:1920:423:0` (jendela bergeser ke kiri mengikuti
  wajah). Frame hasil `temp/frame_face.png` menunjukkan wajah berada di tengah frame
  vertikal. Fallback tetap teruji pada `temp/testvideo_id.mp4` (pola tanpa wajah ->
  `_face_x_center` None -> crop tengah, dimensi tetap 1080x1920).

## F-007 | memperbaiki P-007 (subtitle dianggap tidak terlihat)
- Perubahan (file dan apa yang diubah): **tidak ada perubahan kode** — investigação
  menunjukkan ini keliru uji, bukan cacat program.
- Alasan: cue di `temp/burntest.ass` hanya aktif `0.00-1.95s`, sedangkan frame uji diambil
  pada `t=2.0s`, jadi memang sudah kosong. Filter `ass`, font, dan escaping path semua
  berfungsi (ffmpeg keluar dengan exit 0 tanpa pesan `fontselect`).
- Hasil pengujian ulang: ambil frame pada `t=0.5s` -> teks "saya aufgecet video ini"
  tampil dengan benar: putih tebal, bergaris tepi, maksimal 2 baris, di bagian
  tengah-bawah. Pelajaran: saat mengecek subtitle, selalu ambil frame **di dalam**
  rentang cue dari berkas `.ass`, bukan menebak waktu.

## F-008 | memperbaiki P-008 (subtitle meluber keluar frame)
- Perubahan (file dan apa yang diubah):
  - `src/subtitles.py` -> `write_ass()`: sekarang memakai `c["lines"]` (hasil pecahan 2
    baris dari `_split_lines()`) dan menggabungkannya dengan `\N`, bukan lagi menulis
    `c["text"]` sebagai satu baris panjang. Placeholder `\N` dilindungi sementara
    saat escape `{`/`}` supaya tidak ikut ter-escape.
- Alasan: header `.ass` memakai `WrapStyle: 2`, yaitu libass **tidak** membungkus teks
  otomatis dan hanya menghormati `\N`. Tanpa `\N`, teks panjang keluar dari frame 1080.
- Hasil pengujian ulang: pipeline dijalankan ulang penuh (`--reuse-transcript`), dua klip
  dihasilkan di `output/`. Frame `t=1.0s` kini menampilkan
  "Pernah gak kamu / mikir, kenapa kita susah" (2 baris, utuh di dalam frame) dan
  `t=6.0s` menampilkan "Nova Animadia complete / scratch rebuild from".
  Diverifikasi juga isi `.ass`: setiap `Dialogue` memuat `\N`.

## F-009 | pencatatan kegagalan LLM otomatis + jalur URL (pelengkap)
- Perubahan (file dan apa yang diubah):
  - `main.py`: tambah `record_problem()` yang menambahkan entri `## P-NNN` bernomor
    otomatis ke `problem.md` (dengan waktu, gejala, dugaan penyebab, status OPEN).
    Dipanggil pada `except highlight.HighlightError` sebelum program keluar dengan kode 5.
    Teks yang ditulis hanya pesan error, tidak pernah menyertakan API key.
  - `main.py`: tambah opsi CLI `--env` (memakai file .env alternatif) dan
    `--reuse-transcript` (memakai `temp/transcript.json`, melewati transkripsi).
  - `tests/mock_openrouter.py` + `tests/test_highlight.py` + `tests/.env.test` (baru):
    mock API OpenRouter lokal berbasis stdlib untuk menguji parser, retry, dan alur penuh
    tanpa API key sungguhan.
- Alasan: brief meminta kegagalan LLM berulang dicatat ke `problem.md` dan tidak boleh
  diam-diam mengganti model. `--env` diperlukan agar pengujian tidak menimpa `.env` user.
- Hasil pengujian ulang:
  - Skenario `garbage` -> 3 percobaan dengan jeda 2,4 dtk lalu 5,5 dtk, program berhenti
    dengan `EXIT=5`, entri `P-009` tertulis di `problem.md`, dan model tidak diganti.
    `grep` memastikan tidak ada API key bocor ke jurnal.
  - Skenario `ratelimit` (429 dua kali) -> berhasil pada percobaan ketiga (backoff 2,1 dtk
    lalu 4,3 dtk).
  - Jalur URL teruji nyata: `downloader.download()` mengunduh video YouTube
    "Big Buck Bunny" (durasi 635 detik) dan metadata ter-parse benar.
  - Alur penuh center-crop dan `--face-tracking` keduanya menghasilkan klip 1080x1920
    dengan subtitle terbakar dan wajah terpusat.

## F-010 | memperbaiki P-010 (penegakan model gratis jadi blokir keras)
- Perubahan (file dan apa yang diubah):
  - `src/config.py` -> `_validate()`: pengecekan `:free` dipindahkan dari daftar
    `warnings` ke daftar `problems`, sehingga `raise ConfigError` selalu menghentikan program.
    Pesan error menyebutkan model yang dipakai, cara memperbaikinya, dan tautan daftar
    model gratis. Blok kode `for w in warnings: print(...)` dan import `sys` yang sudah
    tidak terpakai ikut dihapus (dead code).
  - `AGENTS.md` bagian ATURAN KODE: ditegaskan bahwa model tanpa `:free` **wajib**
    menghentikan program, bukan hanya memberi peringatan.
- Alasan: syarat proyek adalah semua tool gratis. Dengan aturan lama, model berbayar
  hanya memicu peringatan lalu program tetap berjalan sehingga kuota berbayar bisa
  terpakai tanpa disadari. Permintaan eksplisit pengguna: blokir keras.
- Hasil pengujian ulang (3 jalur konfigurasi):
  - model berbayar `saya/model-berbayar` -> ditolak, `EXIT=2`, pesan jelas.
  - model gratis `mock/test-model:free` -> lolos, konfigurasi termuat.
  - placeholder -> ditolak, `EXIT=2`, dua pesan (API key + model).
  - Regresi: alur penuh `EXIT=0` (2 klip 1080x1920 di `output/`), dan
    `tests/test_highlight.py` tetap **7/7 lulus**.
## F-011 | memperbaiki P-011 (AUTO CLIP bisa dijalankan di Google Colab)
- Perubahan (file dan apa yang diubah):
  - `autoclip_colab.py` (file baru, 745 baris): pembungkus sekali jalan untuk Colab
    yang TIDAK menduplikasi logika apa pun — dia menyiapkan lingkungan lalu memanggil
    `main.py` yang sudah ada. Isinya 8 bagian:
    1. **Proyek**: `locate_project()` mencari `main.py` + `src/config.py` di folder
       script, `$AUTOCLIP_REPO`, `/content/autoclip`, atau subfolder `/content`;
       `ensure_repo()` meng-clone dari `--repo` bila belum ada.
    2. **FFmpeg**: `setup_ffmpeg()` memasang `ffmpeg` + `fonts-dejavu-core` (font untuk
       libass) + `git` lewat `apt-get` tanpa `sudo`, lalu `fc-cache -f`; kalau
       `ffmpeg`/`ffprobe` sudah ada, apt dilewati.
    3. **Dependency Python**: `python_deps_ok()` mencoba `import dotenv, yt_dlp,
       faster_whisper, requests, cv2, numpy` dulu supaya iterasi tidak pip install
       berulang; error klasik Colab (`libGL.so.1` hilang → `cv2` gagal import)
       ditangani dengan pasang ulang `opencv-python-headless`.
    4. **GPU/CUDA**: `setup_cuda_libs()` memasang `nvidia-cublas-cu12`,
       `nvidia-cudnn-cu12==9.*`, `nvidia-cufft-cu12`, `nvidia-curand-cu12`, lalu
       menambahkan folder `*/lib` paket `nvidia` ke `LD_LIBRARY_PATH` + `ldconfig`.
       GPU dianggap bisa dipakai HANYA kalau `ctranslate2.get_cuda_device_count() > 0`,
       kalau tidak -> CPU `int8` (tidak asal enabled cuda lalu gagal).
    5. **`.env`**: `resolve_env()` memakai urutan `--api-key` > `.env` yang ada >
       variabel shell > Colab Secrets (`google.colab.userdata`) > prompt `getpass`
       (tersamar). Model tanpa `:free` ditolak keras dengan tautan daftar model gratis
       (aturan yang sama dengan `src/config.py`). `.env` yang sudah benar untuk device
       yang dipakai TIDAK ditulis ulang, jadi pengaturan milik user tidak tertimpa.
       Nilai device: GPU -> `cuda`/`float16`, CPU -> `cpu`/`int8`.
    6. **Pipeline**: `run_pipeline()` memanggil `main.py` lewat subprocess dengan `cwd`
       proyek; `run_pipeline_robust()` mengulang sekali di CPU bila keluar kode `4`
       (transkripsi gagal di GPU), lalu mengembalikan `.env` ke kondisi semula.
       Argumen tambahan ditulis setelah `--` dan diteruskan apa adanya.
    7. **Hasil**: `deliver()` mencadangkan hasil ke Google Drive (`--drive-dir`) dan
       membuat `autoclip_output_<timestamp>.zip` lalu memicu unduhan browser
       (`google.colab.files.download`), dengan fallback pesan manual bila bukan Colab.
    8. **Laporan**: `report()` memetakan kode keluar `main.py` ke artinya, menampilkan
       jumlah hasil + waktu, memberi saran khusus untuk kode `5` (rate limit, pakai
       `-- --reuse-transcript`), dan mengingatkan bahwa `/content` hilang saat runtime
       berakhir.
  - `README.md`: bagian 10 ditulis ulang (persiapan, 3 contoh pemakaian, tabel opsi
    `autoclip_colab.py`, daftar yang otomatis ditangani, peringatan runtime sementara);
    bagian 9 menambahkan `autoclip_colab.py`; jumlah jurnal di bagian bawah diperbarui.
  - `AGENTS.md`: `autoclip_colab.py` masuk diagram struktur + subbagian "Menjalankan di
    Google Colab".
  - `.gitignore`: `autoclip_output_*.zip` masuk daftar output.
  - `problem.md` P-011 dan entri ini ditulis sesuai aturan jurnal.
- Alasan: `main.py` sendiri sudah benar dan harus tetap bebas dari logika lingkungan; yang
  lingkungan Colab (tanpa `venv`, tanpa `.env`, tanpa `input/`, dengan GPU CUDA 12, dan
  dengan filesystem yang hilang saat runtime ditutup). Menambah file baru — bukan
  mengubah `main.py` — menjaga satu sumber kebenaran untuk logika pipeline, sesuai
  aturan AGENTS.md "jangan hardcode" dan "jangan ganti model diam-diam".
- Hasil pengujian ulang (di mesin lokal, tanpa GPU, dengan mock OpenRouter lokal):
  - `py_compile` OK; `--help` menampilkan 14 opsi dengan benar.
  - `--check-env` (+ `--skip-install`): menemukan proyek di `/home/qwerty/clip`,
    melaporkan `FFmpeg: True | FFprobe: True`, `GPU: tidak ada | ctranslate2 CUDA: False`.
  - Alur penuh: `autoclip_colab.py --input input/testvideo_id.mp4 --env-file
    tests/.env.test --skip-install -- --reuse-transcript --max-clips 2 --keep-temp`
    -> `main.py` keluar kode `0`, 2 klip 1080x1920 + `.srt`/`.ass` di `output/`
    (total 6 file, 19,3 MB), zip `autoclip_output_20261017_102217.zip` (6 entri di
    dalam `output/`), laporan akhir benar (87 detik).
  - `--drive-dir`: 6 file tersalin ke folder tujuan, isi zip diverifikasi dengan
    `unzip -l`.
  - Unit percobaan `resolve_env()` (4 kasus): model gratis → `.env` ditulis lengkap
    dengan `device=cpu`/`compute=int8`; model `anthropic/claude-3` (tanpa `:free`)
    → ditolak exit 1; API key placeholder + `--no-prompt` → ditolak exit 1;
    `gpu=True` → `WHISPER_DEVICE=cuda`, `WHISPER_COMPUTE_TYPE=float16`; `.env` yang
    sudah valid → byte-identik (tidak ditimpa).
  - Pemisahan argumen setelah `--` diverifikasi: `--reuse-transcript` masuk ke
    `main.py`, bukan ke argparse `autoclip_colab.py` (bug `argv[1:]` -> `argv[cut+1:]`
    ditemukan saat uji pertama dan langsung diperbaiki).
  - Keamanan: tidak ada API key yang muncul di output/log, hanya "tersamar".
- Catatan belum bisa diuji langsung: bagian GPU Colab (`setup_cuda_libs`) dan
  unduhan browser (`google.colab.files`) hanya bisa dibuktikan di Colab sungguhan;
  secara lokal keduanya aman karena sudah ada fallback CPU + pesan manual.

## F-012 | memperbaiki P-012 (jalur `git clone` dari GitHub)
- Perubahan (file dan apa yang diubah) — semua di `autoclip_colab.py` bagian "1. proyek":
  - Tambah `is_repo_url(value)` untuk membedakan URL git (`://`, `git@`, `git+`) dari
    path filesystem.
  - Tambah `normalize_repo_url(url)`: URL ber-skema atau SSH **tidak** diubah lagi;
    hanya URL HTTPS polos yang boleh kehilangan/bertambah `.git`.
  - `locate_project()` sekarang mengembalikan `Path | None` dan **tidak pernah**
    memproyeksi `--repo`/`$AUTOCLIP_REPO` jadi path. Kandidat lokal yang diperiksa:
    `--repo` bila path, `$AUTOCLIP_REPO` bila path, folder skrip, induk skrip,
    `Path.cwd()`, `cwd/autoclip`, `/content/autoclip`, `/content/AUTO-CLIP`, dan
    subfolder `/content`. Tidak ketemu -> `None`, bukan `die()`.
  - `ensure_repo(repo_hint)` dipisah dari `locate_project()` dan mengambil keputusan
    clone sendiri: (1) cek dulu apakah repo sudah ada di lokasi standar -> tidak clone ulang;
    (2) `--repo` yang berupa path lokal dipakai langsung; (3) `clone_destinations()`
    memberi daftar tujuan berurutan (`/content/autoclip` di Colab, kalau tidak
    `cwd/autoclip` lalu folder di samping skrip) dan hanya memilih yang belum ada;
    (4) baru `git clone --depth 1`; (5) verifikasi hasilnya berisi `main.py` +
    `src/config.py`.
  - Tambah pesan galat berisi contoh lengkap `git init`/`git push` (konstanta
    `GITHUB_SKELETON`) supaya user tidak tersesat saat repo belum ada.
  - Tambah guard: `--repo` menunjuk folder lokal yang ada tapi bukan proyek -> berhenti
    dengan pesan jelas, bukan mencoba `git clone path.git`.
  - `main()` menyesuaikan: `project = locate_project(...)`; kalau `None` ->
    `ensure_repo(args.repo)`.
  - `README.md`: bagian baru **10.0 "Upload ke GitHub lalu dipanggil dari Colab"**
    (perintah `git init/add/commit/push` + 2 cara pemakaian di Colab + syarat GPU dan
    Colab Secret); tabel opsi dan daftar "yang otomatis ditangani" diperbarui.
- Alasan: cara paling natural memakai Colab adalah `git clone` dari GitHub, jadi jalur
  itu harus benar dan harus teruji.oula Yang pertama kali diuji justru gagal: URL
  diperlakukan sebagai filesystem sehingga clone diarahkan ke `…/file:/tmp/.../autoclip`
  dan `.git` ditambahkan ke URL ber-skema. Pelajaran yang diterapkan: **URL dan path
  harus dibedakan secara eksplisit sejak awal**, bukan dengan relies `Path.resolve()`.
- Hasil pengujian ulang (repo git sungguhan dibuat di `/tmp/opencode/gitremote/repo`
  berisi 20 file hasil `git add -A` dari proyek ini, lalu 5 skenario diuji dengan
  `autoclip_colab.py` **yang disalin sendirian** ke folder kosong — meniru kondisi
  "user hanya mengunggah 1 file ke Colab"):
  1. Skrip sendirian + `--repo file:///…/repo` -> `Cloning … -> …/autoclip`, "Clone
     beres.", proyek dipakai. **Tidak ada lagi `.git` yang ditambahkan ke URL.**
  2. Jalankan lagi dengan perintah sama -> "Repo sudah ada di … -> tidak di-clone
     ulang"; `find` memastikan hanya **1** folder `.git` (sebelum perbaikan, run kedua
     justru clone ulang ke `autoclip-repo`).
  3. Clone manual oleh user (`git clone … autoclip`) lalu jalankan skrip tanpa
     `--repo` -> proyek ditemukan otomatis.
  4. Menjalankan skrip dari **dalam** repo hasil clone -> proyek = folder skrip.
  5. **Alur penuh dari clone**: `-i /home/qwerty/clip/input/testvideo_id.mp4
     --env-file …/tests/.env.test --skip-install --drive-dir …/drive
     -- --max-clips 2 --keep-temp` -> `SELESAI. 2 klip`, 6 file (19,3 MB), 6 file
     tersalin ke folder Drive, zip terbentuk, kode keluar `0`, 87 detik.
  - `normalize_repo_url()` diuji untuk 7 input: `https://…/autoclip`,
    `…/autoclip.git`, `…/autoclip/`, `git@github.com:…`, `ssh://…`, `file://…`, dan
    path lokal -> hanya yang HTTPS polos yang dapat `.git`.
  - Guard path lokal: `--repo /tmp/…/empty` -> berhenti dengan pesan "bukan proyek AUTO
    CLIP" (bukan `fatal: repository … does not exist`).
- Catatan: `git clone` dari github.com sungguhan tidak diuji (butuh repo publik +
  jaringan ke GitHub); yang diuji adalah `git clone` dari repo git lokal melalui
  `file://`, yang memakai kode `git clone` yang persis sama.

## F-013 | memperbaiki P-013 (unduhan terlihat "stuck" di Colab)
- Perubahan (file dan apa yang diubah):
  - `src/downloader.py`:
    - Tambah `_human_size()` + `make_progress_hook(every=PROGRESS_INTERVAL)` sebagai
      `progress_hooks` untuk yt-dlp. Hook mencetak
      `[unduh] xx.x% 12.3 MB/50.0 MB 4.5 MB/s ETA 12s` maksimal tiap 2 detik, plus
      baris `selesai: <nama> (ukuran, WxH)` saat tiap format selesai. Tetap memakai
      `quiet/noprogress` supaya format baris konsisten dan log bersih.
    - Tambah `build_format(max_height)`: dengan batas tinggi memakai
      `bv*[height<=H]+ba/b[height<=H]/bv*+ba/best`; tanpa batas (None/0) tetap
      `bv*+ba/best`.
    - `download()` menambah parameter `max_height`, mencetak format yang dipakai,
      ditambah pesan "kalau lama tidak bergerak…", `fragment_retries: 5`, dan
      `socket_timeout: 30` supaya koneksi macet gagal dengan pesan, bukan menggantung.
    - `except Exception` di sekitar `extract_info` dibungkus jadi `DownloadError` dengan
      daftar penyebab (video privat, age restriction, YouTube memblokir IP) dan saran
      `!pip install -U yt-dlp`.
  - `src/config.py`: variabel baru `max_source_height` (default `1080`, `0` = tanpa
    batas) beserta dimasukkan ke `public_summary()` dan validasi `>= 360`.
  - `main.py`: log "(unduhan dari URL: progress…)" + "(batas resolusi sumber: 1080p)"
    dan mengirim `max_height=cfg.max_source_height` ke `downloader.download()`.
  - `.env.example`: baris `MAX_SOURCE_HEIGHT=1080`.
  - `README.md`: tabel `.env` + bagian troubleshooting memakai flag ini.
- Alasan: tanpa progress, unduhan 4K (679 MB) terlihat identik dengan hang — pengguna
  tidak bisa membedakan "jalan" dari "macet". Setelah progress ditampilkan, penyebabnya
  juga jelas: file 4K memangDicekUK besar. Karena hasil akhir hanya 1080x1920, membatasi
  tinggi sumber adalah perbaikan yang tepat sasaran (10× lebih ringan untuk video uji).
- Hasil pengujian ulang:
  - Hook sintetis (4 status downloading + finished): persentase, ukuran, kecepatan,
    dan ETA benar; kasus tanpa `total_bytes` dan `speed=0` handled (`?`).
  - Unduhan nyata Big Buck Bunny tanpa batas: 679 MB, progress tiap ~2 detik (reproduksi
    masalah: sangat lama, tanpa output sama sekali).
  - Unduhan sama dengan `max_height=720`: **68,0 MB, 1280x720** (10× lebih kecil),
    progress "0.0% -> 99.2% -> selesai" tampil normal.
  - Unduhan nyata "Me at the zoo" dengan batas 720: 320x240 (varian tertinggi yang
    tersedia), `finished` menampilkan resolusi -> hook bekerja juga tanpa estimasi total.
  - Percobaan pertama dengan video sama habis `HTTP Error 403: Forbidden` -> bukan bug
    kode (percobaan kedua setelah 20 detik berhasil, 1280x720). Jalur galat diuji
    langsung: pesannya rapi, menyebut kemungkinan blokir IP dan `!pip install -U yt-dlp`.
  - `build_format()` diuji untuk None/0/720/1080/2160; validasi config menolak
    `MAX_SOURCE_HEIGHT=200` dengan pesan jelas.
  - Alur penuh `main.py` dengan file lokal tetap `SELESAI. 1 klip`;
    `tests/test_highlight.py` **7/7 lulus**; `--verbose` menampilkan
    `MAX_SOURCE_HEIGHT = 1080`.
- Catatan: progress tidak bisa di-render di panel output statis Kolab, hanya di stream
  stdout — kalau cell di-scroll ke bawah, baris `[unduh] …` tetap ada di riwayat.

## F-014 | memperbaiki P-014 (progress unduhan tidak lagi dicetak tiap 2 detik)
- Perubahan (file dan apa yang diubah):
  - `src/downloader.py`: `PROGRESS_INTERVAL` 2.0 -> 15.0 detik dan ditambah
    `PROGRESS_STEP = 10.0` (persen). `make_progress_hook(every, step)` sekarang
    mencetak baris kalau **salah satu** terpenuhi: sudah `>= every` detik sejak
    baris terakhir, atau persentase naik `>= step` poin. Gate waktu dimatikan kalau
    `every <= 0`. `download()` menerima parameter baru `progress_seconds` dan
    mencetak frekuensi yang dipakai ("progress: max 1 baris tiap 15 detik").
  - `src/config.py`: variabel baru `download_progress_seconds`
    (`DOWNLOAD_PROGRESS_SECONDS`, default `15`), parser `_parse_float()`, validasi
    rentang 0..3600, dan masuk ke `public_summary()`. Sekalian dirapikan indentasi
    baris `max_source_height=` yang messed up.
  - `main.py`: opsi `--progress-seconds` (override dari `.env`), diteruskan ke
    `downloader.download()`.
  - `.env.example`: baris `DOWNLOAD_PROGRESS_SECONDS=15`.
  - `tests/test_progress.py` (baru): uji frekuensi baris dengan waktu simulasi.
  - `README.md`: tabel opsi, tabel `.env`, dan tabel masalah menyebut ini.
- Alasan: gate waktu saja tidak cukup untuk dua kasus yang berbeda. Video besar
  (1,3 GB) butuh jeda panjang supaya output tidak penuh; video kecil butuh
  progress tetap terlihat walaupun unduhannya selesai dalam hitungan detik. Karena itu
  gate-nya ganda: waktu **atau** kenaikan persentase.
- Hasil pengujian ulang:
  - `tests/test_progress.py`: simulasi 100 event (1% per event, tiap 2 detik,
    total 1,3 GB) -> `every=2` (**perilaku lama**) 100 baris, `every=15` (default)
    **13 baris**, `every=60` 10 baris; `every=0` tepat 10 baris (tiap 10%);
    file kecil 8 MB (12,5% per event) tetap 8 baris; kasus tanpa `total_bytes`
    tidak crash. Semua pemeriksaan lulus.
  - Unduhan nyata `trailer_480p.mov` (10,5 MB): `every=2` -> 5 baris progress,
    `every=15` -> 4 baris, keduanya menampilkan 0% sampai 100% lalu
    "selesai: source.mov (10.5 MB)".
  - Alur penuh `main.py` dengan file lokal + mock OpenRouter dan
    `--progress-seconds 30 --verbose`: **2 klip** 1080x1920 + subtitle, `temp/`
    dibersihkan, tidak ada galat.
  - Validasi config: `DOWNLOAD_PROGRESS_SECONDS=-5` ditolak dengan pesan jelas;
    `abc` ditolak oleh `_parse_float`.
  - `tests/test_highlight.py` tetap **7/7 lulus**.

## F-015 | memperbaiki P-015 (GPU tanpa pustaka CUDA: fallback CPU, pesan jelas)
- Perubahan (file dan apa yang diubah):
  - `src/transcriber.py`:
    - Konstanta `CUDA_LIBS = ("libcublas.so.12", "libcudnn.so.9")` dan
      `missing_cuda_libs()` yang benar-benar memuat pustaka lewat `ctypes.CDLL`,
      serta `_is_cuda_error()` untuk mengenali galat pustaka/CUDA dari pesannya.
    - `_collect_segments()`: iterasi generator dipisah dari `model.transcribe()`.
    - `_transcribe_once()`: pembungkus try/except untuk pemanggilan **dan** iterasi.
      Urutan penanganan: (1) galat `vad_filter` -> ulangi tanpa vad seperti
      sebelumnya; (2) galat CUDA saat `device=cuda` -> muat ulang model di
      `cpu/int8` lalu transkripsi ulang **hanya** bila `WHISPER_DEVICE=auto`;
      (3) kalau `cuda` dipaksa user -> `TranscriptionError` berisi 3 cara
      memperbaiki (tanpa diam-diam mengganti perangkat); (4) galat lain ->
      `TranscriptionError: Transkripsi gagal: ...`.
    - `transcribe()`: sebelum memuat model, kalau `auto` memilih cuda tapi pustaka
      CUDA tidak termuat, langsung turun ke `cpu/int8` dengan log jelas. `device`
      hasil sebenarnya ikut ditulis ke `transcript.json`.
  - `autoclip_colab.py`: `ctranslate2_sees_cuda(quiet=False)` tidak lagi hanya
    mengecek jumlah GPU, tapi juga memuat `libcublas.so.12` + `libcudnn.so.9` lewat
    loader. Pemeriksaan setelah `LD_LIBRARY_PATH` diset memakai `quiet=True`.
  - `tests/test_transcribe_cuda_fallback.py` (baru): 5 skenario dengan GPU dipalsukan.
  - `README.md`: tabel masalah menambahkan baris `libcublas.so.12`.
- Alasan: `get_cuda_device_count()` tidak membuktikan apa pun soal pustaka —
  ia tetap mengembalikan jumlah GPU saat cuBLAS belum termuat, jadi deteksi GPU
  dan fallback CPU di dalam `transcribe()` tidak pernah aktif. Selain itu galat
  ctranslate2 muncul saat generator diiterasi, di luar jangkauan try/except yang
  lama; akibatnya program keluar dengan kode 1 (galat tak terukur) sehingga retry
  CPU di `run_pipeline_robust()` yang hanya memicu kode 4 tidak pernah jalan.
- Hasil pengujian ulang:
  - `tests/test_transcribe_cuda_fallback.py` (tanpa GPU, device cuda disimulasikan):
    kasus 1 (pustaka hilang, `auto`) -> model dimuat sekali `cpu/int8`, 2 segmen,
    `transcript.json` ber-`device=cpu`; kasus 2 (meledak saat iterasi, `auto`) ->
    `cuda/float16` lalu `cpu/int8`, hasil tetap 2 segmen; kasus 3 (`cuda` dipaksa) ->
    **tidak** fallback, pesan menyebut `libcublas.so.12`, `WHISPER_DEVICE=cpu`, dan
    `autoclip_colab.py`; kasus 4 (jalur cpu) tidak berubah; kasus 5 (galat non-CUDA,
    `ValueError: audio rusak`) -> `Transkripsi gagal: ...`. Semua lulus.
  - Alur penuh `main.py` dengan file lokal + mock OpenRouter: `device=cpu
    compute_type=int8`, 23 segmen, **2 klip** 1080x1920 + subtitle, exit 0.
  - `ctranslate2_sees_cuda()` dan `missing_cuda_libs()` di mesin tanpa GPU
    sama-sama `False` / daftar 2 pustaka -> tidak salah pilih perangkat.
  - `tests/test_highlight.py` **7/7 lulus**, `tests/test_progress.py` lulus,
    `autoclip_colab.py --help` jalan.
  - Perilaku Colab yang belum bisa diuji di mesin ini (GPU nyata): yang bisa
    diuji hanya probe pustaka lewat `ctypes` dan simulasi galatnya.

## F-016 | memperbaiki P-016 (verifikasi bot YouTube)
- Perubahan (file dan apa yang diubah):
  - `src/downloader.py`:
    - `BotCheckError(DownloadError)` + `BOT_CHECK_MARKERS` + `looks_like_bot_check()`
      supaya pesan "Sign in to confirm you're not a bot" (dan variasinya, termasuk
      "Failed to extract any player response") dikenali sebagai kasus khusus, bukan
      galat unduhan generik. Pencocokan dilakukan pada huruf kecil, jadi kutip ASCII
      (`'`) dan kutip miring (`'`) sama-sama kena.
    - `BOT_CHECK_FALLBACK_CLIENTS = ("tv", "ios")` + `build_extractor_args()` +
      parameter baru `player_client`. Percobaan ulang memakai
      `extractor_args: {"youtube": ["player_client=tv,ios"]}` (bukan key top-level
      `youtube`, yang diabaikan yt-dlp) karena player client TV/iOS tidak butuh login.
    - `download()` dibungkus fungsi `fetch()` dan punya percobaan ulang **satu kali**:
      hanya saat bot check terdeteksi, cookie belum dikirim, dan `player_client`
      belum dipaksa. Kalau percobaan ulang gagal -> `BotCheckError`. Kalau cookie atau
      player client sudah dikirim -> langsung `BotCheckError` tanpa mengulang
      permintaan yang sama. Galat biasa (video privat, 429, 403) tetap
      `DownloadError` biasa dan tidak memicu percobaan ulang.
    - `resolve_cookies()` memvalidasi path `cookies.txt` sebelum dipakai; parameter
      baru `cookies_file` dan `cookies_from_browser`; yang dipakai dicetak sebagai
      `[unduh] cookie: <path>` (path saja, isi cookie tidak pernah dicetak).
    - `bot_check_help()` menyusun pesan berisi langkah yang bisa dilakukan: unduh
      manual ke `input/`, `--cookies cookies.txt` / `YT_COOKIES_FILE`,
      `pip install -U yt-dlp`, tunggu/ganti jaringan; plus versi singkat kalau cookie
      sudah dipakai (berarti IP memang diblokir).
  - `src/config.py`: variabel baru `yt_cookies_file` (`YT_COOKIES_FILE`, default
    kosong), masuk `public_summary()` sebagai `(kosong)`, dan divalidasi: path yang
    ditunjuk harus benar-benar ada sebagai file, kalau tidak `ConfigError` (keluar 2).
  - `main.py`: opsi baru `--cookies PATH` (override `.env`), diteruskan ke
    `downloader.download()`, dan blok `except downloader.BotCheckError` (ditempatkan
    di ATAS `except (DownloadError, TranscriptionError)` karena ia subclass-nya) yang
    mencetak `[ERROR VERIFIKASI BOT]` lalu keluar dengan kode 4. Blok ini sengaja
    tidak menulis entri baru ke `problem.md`: penyebabnya reputasi IP, jadi mencatat
    lagi hanya memenuhi jurnal dengan pengulangan masalah yang sama.
  - `tests/test_bot_check.py` (baru, 7 skenario): `yt_dlp` dipalsukan lewat
    `sys.modules`, jadi tidak ada request ke internet sama sekali.
  - `.env.example`: baris `YT_COOKIES_FILE=`. `README.md`: baris tabel `.env`, baris
    tabel opsi, dan baris troubleshooting untuk `Sign in to confirm you're not a bot`.
    `AGENTS.md`: opsi `--cookies` di tabel. `autoclip_colab.py` -> `report()`: saran
    khusus untuk kode keluar 4 akibat verifikasi bot (file lokal, `-- --cookies
    cookies.txt`, restart runtime, ganti jaringan).
  - `src/transcriber.py`: dua perbaikan kalimat (typo), tanpa perubahan logika.
  - Dua file uji yang isinya tumpang tindih (`tests/test_download_bot_check.py` dan
    `tests/test_bot_check.py`) digabung menjadi satu `tests/test_bot_check.py`; folder
    namesake di `temp/` ikut dibersihkan.
- Alasan:
  1. Dulu semua galat dibungkus satu pesan "Gagal mengunduh video dari URL ini" yang
     menyebut kemungkinan blokir IP tanpa memberi langkah konkret, dan `opts`
     mengunci `"cookiefile": None` sehingga tidak ada jalur cookie sama sekali
     (duga penyebab butir 2 di P-016).
  2. Pelajaran F-009 (kegagalan jangan ditangani diam-diam) diterapkan selaras:
     program mencoba satu jalur yang masuk akal tanpa login, lalu berhenti dengan
     instruksi manual — tanpa mengganti model, tanpa loop tanpa akhir.
  3. Percobaan ulang dibatasi satu kali dan hanya untuk kasus bot check supaya tidak
     menambah request ke IP yang sudah diblokir; mengulang justru memperburuk
     (P-016 butir 1).
- Hasil pengujian ulang:
  - `tests/test_bot_check.py` **lulus** (7 skenario): 3 pesan positif + 3 negatif
    terdeteksi benar; bot check -> percobaan ulang `player_client=tv,ios` lalu
    berhasil (2 percobaan, metadata benar); bot check total -> `BotCheckError` 13
    baris yang menyebut cookie, file lokal, dan reputasi IP; cookie sudah dikirim ->
    tepat 1 percobaan, tidak ada percobaan ulang sia-sia; video privat ->
    `DownloadError` biasa dengan 1 percobaan; `resolve_cookies()` menolak path
    hilang dan menerima file yang ada; `build_extractor_args()` benar untuk
    None/tv/tuple; file lokal tetap terpengaruh (durasi 2,0s, `is_url=False`).
  - Regresi: `tests/test_highlight.py` 7/7, `tests/test_progress.py` lulus,
    `tests/test_transcribe_cuda_fallback.py` lulus, `py_compile` semua file OK.
  - Alur penuh `main.py` (file lokal + mock OpenRouter, `--max-clips 2 --keep-temp`):
    23 segmen transkripsi, 2 segmen terpilih, **2 klip 1080x1920** + `.srt`/`.ass`
    di `output/`, exit 0.
- Catatan: yang tidak bisa dibuktikan di mesin ini adalah keadaan sebenarnya —
    apakah IP Colab tertentu sedang diblokir dan apakah player client `tv`/`ios`
    cukup untuk lolos. Yang diuji adalah logika keputusannya (deteksi pesan, percobaan
    ulang sekali, lalu pesan yang bisa ditindaklanjuti), dan tidak ada satu pun
    request nyata ke YouTube selama pengujian.

## F-018 | memperbaiki P-018 (`main.py --help` crash karena `%` di teks bantuan)
- Perubahan (file dan apa yang diubah):
  - `main.py` -> `parse_args()`: teks bantuan `--progress-seconds` yang memuat
    "tiap 10%" ditulis jadi "tiap 10%%" (satu baris, dengan komentar singkat bahwa
    argparse mem-format `help` memakai operator `%`).
- Alasan: argparse selalu menjalankan `help_string % params` supaya `%(default)s`
  bisa dipakai, jadi setiap persen biasa di dalam teks bantuan harus diekspresikan
  sebagai `%%`. Huruf `%` ini sudah masuk sejak F-014 dan tidak ketahuan karena
  `--help` tidak pernah dijalankan sesudahnya — pelajaran yang sama seperti F-011
  dan F-013: setiap jalur baru harus dijalankan, bukan hanya ditulis.
- Hasil pengujian ulang:
  - `venv/bin/python main.py --help` sekarang tampil penuh: 11 opsi tercetak
    (`--input`, `--cookies`, `--progress-seconds`, dst.) dan teksnya membaca
    "0 = hanya tiap 10%." tanpa galat. Sebelumnya `ValueError: incomplete format`.
  - `venv/bin/python autoclip_colab.py --help` tetap jalan (tidak ada persen di
    teks bantuannya).
  - Regresi setelah perbaikan: `tests/test_bot_check.py` lulus (7 skenario),
    `tests/test_highlight.py` 7/7, `tests/test_progress.py` lulus,
    `tests/test_transcribe_cuda_fallback.py` lulus.
  - Alur penuh `main.py` (file lokal + mock OpenRouter): 22 segmen transkripsi,
    2 klip 1080x1920 + `.srt`/`.ass` di `output/`, exit 0.
  - Jalur cookie dari CLI diuji langsung: `--cookies <path yang tidak ada>` berhenti
    sebelum ada request apa pun dengan pesan "File cookies tidak ditemukan: ..." dan
    kode keluar **4**; `YT_COOKIES_FILE=<path yang tidak ada>` di `.env` berhenti
    lebih awal dengan `[KONFIGURASI BELUM LENGKAP]` (kode keluar 2).

## F-019 | pelengkap P-019 (diagnostik CUDA: penyebab, bukan sekadar "fallback")
- Perubahan (file dan apa yang diubah):
  - `autoclip_colab.py`:
    - `cuda_diagnostics()` menjalankan probe JSON di subprocess yang sama dengan
      interpreter pipeline, sehingga **seluruh** kondisi dilaporkan: `device_count`
      dari `ctranslate2.get_cuda_device_count()`, status tiap pustaka
      (`libcublas.so.12`, `libcudnn.so.9`, `libcudart.so.12`, `libcublasLt.so.12`)
      beserta pesan error loader, lokasi paket pip `nvidia`, dan `LD_LIBRARY_PATH`.
    - `cuda_ready(diag)` = device_count > 0 **dan** kedua pustaka wajib termuat.
    - `explain_cuda_failure(diag, gpu)` menyusun penjelasan per kondisi:
      GPU tidak terlihat (kontras dengan `nvidia-smi` + perintah perbaikan),
      pustaka gagal dimuat (nama + error), paket `nvidia` tidak terlihat
      (indikasi pip & program memakai interpreter berbeda), probe gagal total.
    - `install_cuda_libs()` menggantikan `pip -q`: output ditangkap, kode keluar
      diperiksa, lalu `import nvidia` dicek di interpreter yang sedang berjalan;
      `nvidia-cuda-runtime-cu12` ikut dipasang karena `libcudart.so.12` juga dibutuhkan.
    - `setup_cuda_libs()` mencetak diagnosis **sebelum** memasang, dan setelah
      memasang lagi mencetak penyebab spesifik bila tetap gagal (dulu cuma
      "fallback ke CPU (int8)" tanpa alasan). `ctranslate2_sees_cuda(quiet=)`
      dipertahankan sebagai pembungkus tipis yang ikut mencetak penjelasan.
    - `--check-env` sekarang mencetak device_count, versi ctranslate2, status tiap
      pustaka, `LD_LIBRARY_PATH`, penyebab bila belum siap, dan device yang
      tertulis di `.env`.
  - `tests/test_cuda_diagnostics.py` (baru, 6 skenario dengan dict probe disimulasikan).
  - `README.md`: baris troubleshooting GPU + perintah `--check-env`.
- Alasan: di P-019 program sudah memasang pustaka CUDA, tetap turun ke CPU, dan
  tidak ada satu baris pun yang menjelaskan kenapa — karena probe lama mengembalikan
  satu nilai `False` untuk tiga kondisi berbeda dan pemeriksaan kedua dipanggil
  dengan `quiet=True`. Tanpa penyebab, mitigasi (install ulang paket, restart
  runtime, ganti runtime) jadi tebakan.
- Hasil pengujian ulang:
  - `tests/test_cuda_diagnostics.py` **lulus** (6 skenario): kondisi sehat -> siap;
    pustaka hilang -> belum siap + nama pustaka & errornya; `device_count=0` ->
    kontras dengan `nvidia-smi` + perintah `pip install`; probe rusak -> program
    masih hidup dengan pesan; paket `nvidia` hilang -> dilaporkan; probe nyata di
    mesin lokal tidak membuat program jatuh.
  - `venv/bin/python autoclip_colab.py --check-env --skip-install` di mesin tanpa
    GPU: `CUDA : siap=False device_count=0`, keempat pustaka tampil dengan error
    loader, `.env` **tidak** berubah (md5 sebelum = sesudah), device yang terbaca
    `auto`.
  - Regresi: `main.py --help`, `autoclip_colab.py --help`, `py_compile`, dan
    seluruh uji lain (`test_bot_check`, `test_highlight` 7/7, `test_progress`,
    `test_transcribe_cuda_fallback`) tetap lulus.
- Catatan: akar masalah sebenarnya di Colab **belum terkonfirmasi** — mesin ini tidak
  punya GPU, jadi yang bisa diuji hanya logika diagnosikanya. P-019 tetap OPEN
  sampai `--check-env` dijalankan di Colab.
