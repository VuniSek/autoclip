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

## F-020 | memperbaiki P-020 (`--skip-install` tidak lagi memaksa CPU)
- Perubahan (file dan apa yang diubah):
  - `autoclip_colab.py`:
    - `setup_cuda_libs(install: bool = True)`. Probe GPU (`gpu_name()` +
      `cuda_diagnostics()` + set `LD_LIBRARY_PATH`) **selalu** jalan; `install=False`
      hanya melewati `pip install`. Kalau pustakanya belum siap dan `install=False`,
      pesan peringatan menyuruh menjalankan sekali tanpa `--skip-install`.
    - `main()` langkah 3/5 tidak lagi `gpu = False` untuk `--skip-install`, melainkan
      `gpu = False if args.cpu else setup_cuda_libs(install=not args.skip_install)`.
      Langkah 2/5 (FFmpeg) tetap tidak berubah: `--skip-install` tetap berhenti kalau
      FFmpeg tidak ada.
  - `tests/test_cuda_diagnostics.py`: skenario 7 (3 kasus, GPU/`pip` dipalsukan).
  - `README.md` + `AGENTS.md`: catatan bahwa `--skip-install` tidak mematikan GPU.
- Alasan: pengguna yang sudah memasang pustaka CUDA sekali tidak punya cara memakai
  GPU lagi tanpa mengulang `apt-get` + `pip install` yang berat; sebelumnya jalur itu
  selalu berakhir di CPU tanpa probe sama sekali, jadi penyebabnya tidak terlihat.
- Hasil pengujian ulang:
  - `tests/test_cuda_diagnostics.py` lulus (7 skenario): `install=False` + pustaka
    siap -> `gpu=True` tanpa memanggil pip; `install=False` + pustaka belum siap ->
    `gpu=False` tanpa pip dan dengan peringatan; `install=True` -> pip dipanggil
    1 kali. `LD_LIBRARY_PATH` dipulihkan setelah uji.
  - `venv/bin/python autoclip_colab.py --check-env --skip-install` di mesin tanpa GPU:
    langkah 2/5 dan 3/5 tetap tampil benar, `.env` tidak berubah.
  - Regresi: `py_compile`, `main.py --help`, `autoclip_colab.py --help`,
    `test_bot_check`, `test_highlight` 7/7, `test_progress`,
    `test_transcribe_cuda_fallback` semuanya lulus.

## F-021 | memperbaiki sebagian P-021 (`libcublas.so.12` tidak terjangkau di Colab)
- Perubahan (file dan apa yang diubah):
  - `autoclip_colab.py`:
    - `nvidia_lib_dirs()` sekarang memindai **seluruh** `sys.path` (`site.getsitepackages()`,
      user site, dan tiap entri `sys.path`), termasuk tata letak `nvidia/cu12`,
      `nvidia/cu13`, `nvidia/lib`, plus `/usr/local/cuda*/lib64` dan
      `/usr/lib/x86_64-linux-gnu`. Sebelumnya hanya `nvidia.__file__`, sehingga paket
      yang terpasang di pohon site-packages lain tidak pernah terlihat.
    - Probe `CUDA_PROBE` punya `candidate_dirs()` yang sama dan `find_lib()` berjenjang:
      (1) andalkan loader seperti yang dilakukan ctranslate2; (2) kalau gagal, telusuri
      sendiri folder kandidat lalu muat lewat **path absolut** dengan `RTLD_GLOBAL`;
      (3) kalau file `.so` yang dicari memang tidak ada, laporkan versi lain yang
      terpasang (indikasi wheel CUDA 13, mis. `libcublas.so.13`).
    - `lib_loaded()` Textsros `ok` dan `loaded:<path>` sama-sama berarti termuat;
      `cuda_ready()` memakainya.
    - `explain_cuda_failure()` membedakan tiga kasus: `TIDAK ADA di folder mana pun`
      (+ versi lain yang terpasang + perintah `--force-reinstall`), `ada di <path> tapi
      gagal: <err>`, dan daftar "dimuat lewat path absolut".
    - `set_cuda_ld_path()` + `missing_sonames()` + `force_install_cuda_libs()`:
      bila sesudah pemasangan biasa file `.so.12` tetap tidak ada sama sekali,
      program escalating ke `pip install --force-reinstall --no-deps nvidia-cublas-cu12
      nvidia-cuda-runtime-cu12` lalu probe ulang.
  - `tests/test_cuda_diagnostics.py`: skenario 8 (tiga status baru + versi lain yang
    terpasang) dan skenario 9 (pemindaian seluruh `sys.path` memakai folder sementara).
- Alasan: data dari Colab menunjukkan `device_count > 0` (ctranslate2 sudah bicara
  dengan GPU) tetapi `libcublas/cudart/cublasLt.so.12` "cannot open shared object
  file" **setelah** pip memasang paket dan `LD_LIBRARY_PATH` di-set ke 16 folder,
  sedangkan `libcudnn.so.9` termuat. Uji mekanismenya di mesin lokal (A-D) membuktikan
  `LD_LIBRARY_PATH` dari `os.environ` memang sampai ke subprocess, jadi masalahnya bukan
  pewarisan environment melainkan **file-nya tidak ada di folder yang dipindai** atau
  **`nvidia.__file__` menunjuk pohon yang salah**. Keduanya ditutup di sini, dan
  sekarang program bisa membedakan "tidak ada" vs "ada tapi gagal dimuat".
- Hasil pengujian ulang:
  - `tests/test_cuda_diagnostics.py` lulus (9 skenario). Perluasan baru: `loaded:<path>`
    dihitung termuat, `gagal:<path> -> err` ditampilkan lengkap, "TIDAK ADA" memuat
    pesan loader asli + versi lain yang terpasang + perintah `--force-reinstall`,
    dan `nvidia_lib_dirs()` menangkap `nvidia/*/lib` maupun `nvidia/cu12` dari
    `sys.path` buatan (3 folder terdeteksi).
  - Uji mekanismenya di mesin lokal (4 kasus A-D) tetap berlaku: `LD_LIBRARY_PATH`
    dari `os.environ` diteruskan ke subprocess (C) tetapi perubahan setelah
    `ctypes` dipakai tidak berlaku dalam proses yang sama (D) — alasannya
    `setup_cuda_libs()` selalu memindahkan `LD_LIBRARY_PATH` ke **subprocess** probe.
  - `venv/bin/python autoclip_colab.py --check-env --skip-install` di mesin tanpa GPU
    tetap jalan dan menampilkan 4 pustaka gagal; `.env` tidak berubah.
  - Regresi: `py_compile`, `test_highlight` 7/7, `test_progress`, `test_bot_check`,
    `test_transcribe_cuda_fallback`, `main.py --help`, `autoclip_colab.py --help` lulus.
- Catatan: akar masalah di Colab **masih belum terkonfirmasi** (P-021 OPEN) — mesin ini
  tidak punya GPU. Jalankan `--check-env` di Colab setelah `git pull`; baris
  "TIDAK ADA di folder mana pun" + "yang terpasang hanya versi lain" akan langsung
  menunjukkan apakah penyebabnya wheel CUDA 13 yang menutupi wheel CUDA 12.

## F-022 | memperbaiki P-022 (`openrouter/free` dianggap model berbayar)
- Perubahan (file dan apa yang diubah):
  - `src/config.py`: konstanta `FREE_ROUTER_MODELS = frozenset({"openrouter/free"})` +
    helper `model_is_free(model)` (sufiks `:free` **atau** router gratis);
    `_validate()` memakai helper itu, jadi aturan "blokir keras model berbayar"
    (P-010) tetap berlaku untuk model berbayar biasa.
  - `autoclip_colab.py`: `COLAB_FREE_ROUTERS` + `colab_model_is_free()` (salin dari
    `src/config.py` supaya runner Colab tetap bisa jalan sendiri) dipakai di
    `resolve_env()`. Pesan penolakan kini menyebut alternatif yang bisa langsung
    dipakai: router gratis `openrouter/free` atau model `:free` spesifik.
  - `tests/test_model_gratis.py` (baru, 3 bagian): 6 model gratis diterima, 5 model
    berbayar ditolak, keputusan `src/config.py` dan runner Colab identik untuk 11 model.
- Alasan: `openrouter/free` adalah router OpenRouter yang **hanya** meneruskan ke
  varian gratis, jadi tidak memakai kuota berbayar. Aturan lama hanya mengecek sufiks
  `:free`, sehingga model yang paling aman justru ditolak dan program berhenti sebelum
  pipeline jalan. Kuota berbayar tetap mustahil dipakai karena model biasa tanpa
  `:free` masih ditolak.
- Hasil pengujian ulang:
  - `tests/test_model_gratis.py` lulus: `model_is_free()` benar untuk
    `google/gemini-2.0-flash-exp:free`, `openrouter/free`, `OpenRouter/Free`,
    `  openrouter/free  ` (spasi + huruf besar) -> True; `openai/gpt-4o`,
    `anthropic/claude-sonnet-4`, `google/gemini-2.0-flash-exp`, `deepseek/deepseek-chat`,
    `""` -> False.
  - `load_config()` menerima keenam model gratis dan menolak kelima model berbayar
    dengan pesan yang menyebut aturan `:free`.
  - `autoclip_colab.py --check-env --model openrouter/free` -> "model gratis, valid";
    `--model openai/gpt-4o` -> berhenti dengan pesan yang menyebut router gratis dan
    model `:free` sebagai alternatif.
  - Regresi: `py_compile`, `test_highlight` 7/7, `test_progress`, `test_bot_check`,
    `test_transcribe_cuda_fallback`, `test_cuda_diagnostics` lulus.

## F-023 | memperbaiki P-023 (penulis `.env` membuang kunci pengguna)
- Perubahan (file dan apa yang diubah):
  - `autoclip_colab.py`:
    - `DEFAULTS` dilengkapi `MAX_SOURCE_HEIGHT=1080`, `DOWNLOAD_PROGRESS_SECONDS=15`,
      `YT_COOKIES_FILE=` (kunci yang dibaca `src/config.py` tapi tidak ada di
      `DEFAULTS`).
    - `ENV_ORDER` ditambah tiga kunci yang sama, jadi urutannya sama dengan
      `.env.example`.
    - Penulis `.env` menulis ulang **semua** kunci milik pengguna yang tidak dikenal
      program (yang tidak ada di `ENV_ORDER`), tidak membuangnya.
  - `tests/test_env_writer.py` (baru, 4 bagian): kunci pengguna tetap utuh, semua
    kunci `src/config.py` ada di `ENV_ORDER`, device mengikuti status GPU, model router
    gratis ditulis apa adanya.
- Alasan: `resolve_env()` menulis ulang `.env` setiap kali runner dijalankan, dan
  seluruh kunci di luar `ENV_ORDER` hilang seketika. Akibat yang nyata: nilai
  `MAX_SOURCE_HEIGHT=720` yang dirapikan pengguna kembali ke 1080p tanpa jejak.
  Pelajaran F-009/F-016: perubahan pada file milik pengguna harus terlihat dan tidak
  boleh menghapus apa pun yang tidak diketahui program.
- Hasil pengujian ulang:
  - `tests/test_env_writer.py` lulus: `MAX_SOURCE_HEIGHT=720`,
    `DOWNLOAD_PROGRESS_SECONDS=30`, `YT_COOKIES_FILE=/tmp/cookies.txt`, dan kunci
    buatan `MY_CUSTOM_KEY` semuanya tetap tertulis utuh; `gpu=True` -> device=cuda,
    compute=float16; `gpu=False` -> device=cpu; `openrouter/free` tersimpan apa adanya.
  - `src/config.py` punya 14 kunci, `ENV_ORDER` runner juga 14 (tidak ada yang kurang).
  - File `.env` lokal dikembalikan ke keadaan semula (model
    `google/gemma-4-31b-it:free`, device `auto`) setelah uji `--model` menimpanya;
    `load_config()` membacanya normal: model, `max_source_height=1080`,
    `download_progress_seconds=15`, `yt_cookies_file=''`.
  - Regresi: seluruh uji lain lulus, `py_compile` OK.

## F-024 | memperbaiki P-024 (retry verifikasi bot per player client)
- Perubahan (file dan apa yang diubah):
  - `src/downloader.py`:
    - `BOT_CHECK_FALLBACK_CLIENTS = ("tv", "ios", "web_safari")` + `EXTRA_CLIENT_EXAMPLES`
      + `fallback_clients()` (bisa dioverride lewat env `YT_PLAYER_CLIENTS`).
    - Retry sekarang **per client**, bukan satu permintaan gabungan `player_client=tv,ios`.
      Tiap percobaan dicetak (`mencoba ulang dengan player client: tv`, lalu
      `player client tv juga ditolak.`), dan kalau satu berhasil lognya menyebut client
      yang berhasil.
    - `bot_check_help()` menerima `tried_clients` dan menambahkan: daftar client yang
      sudah dicoba + perintah siap tempel untuk menguji client lain manual
      (`yt-dlp --extractor-args "youtube:player_client=mweb" ...`).
    - `build_extractor_args()` diubah mengembalikan **fragmen opts lengkap**
      (`{"extractor_args": {"youtube": [...]}}`) dan kedua pemanggilnya diperbarui.
      Sebelumnya fungsinya mengembalikan dict dalam, sehingga pemanggilan baru
      (`retry_opts.update(...)`) menaruh key top-level `youtube` — key yang
      **diabaikan yt-dlp**, artinya retry sebenarnya berjalan dengan client default
      (bug yang sama seperti catatan di F-016, terulang karena API-nya japit).
  - `.env.example` + `README.md`: `YT_PLAYER_CLIENTS` (opsional) dan baris troubleshooting
    yang menyebut daftar client + cara menambah client lain.
  - `autoclip_colab.py`: `DEFAULTS`/`ENV_ORDER` ditambah `YT_PLAYER_CLIENTS` agar tidak
    hilang saat `.env` ditulis ulang (P-023).
  - `tests/test_bot_check.py`: skenario 2 & 3 ditulis ulang (retry per client, daftar
    client di pesan), skenario 6 ditambah uji `fallback_clients()` + env override,
    dan `build_extractor_args()` diuji dalam bentuk opts lengkap.
- Alasan: menggabungkan beberapa client dalam satu permintaan membuat program tidak
  bisa memisahkan "client ditolak" dari "client tidak didukung", dan tidak ada cara
  memberi tahu pengguna client mana yang masih layak dicoba. Per client juga membuat
  jumlah permintaan tetap kecil (3-4), sesuai peringatan P-016 bahwa mengulang ke IP
  yang diblokir justru memperburuk.
- Hasil pengujian ulang:
  - `tests/test_bot_check.py` lulus (7 skenario): bot check -> retry `tv` (2 percobaan,
    `extractor_args={"youtube": ["player_client=tv"]}`) lalu berhasil; bot check
    terus-menerus -> `BotCheckError` yang menyebut ketiga client + perintah manual
    siap tempel; cookie dikirim -> tetap 1 percobaan; galat biasa -> `DownloadError`
    tanpa retry; `fallback_clients()` menghormati `YT_PLAYER_CLIENTS`.
  - Alur penuh `main.py` (file lokal + mock OpenRouter): 2 klip 1080x1920 + subtitle,
    exit 0.
  - Regresi: `py_compile`, `test_highlight` 7/7, `test_progress`, `test_transcribe_cuda_fallback`,
    `test_cuda_diagnostics`, `test_model_gratis`, `test_env_writer` lulus.
- Catatan: verifikasi bot dari YouTube **tidak bisa dihilangkan** dari sisi program —
  itu reputasi IP. Yang diperbaiki di sini adalah banyaknya jalur yang dicoba dan
  kejelasan petunjuk yang diberikan. Jalur yang benar-benar berhasil: `cookies.txt`
  (butuh akun) atau mengunduh manual lalu memakai file lokal.

## F-025 | memperbaiki P-025 (runtime JS untuk yt-dlp + daftar client yang luas)
- Perubahan (file dan apa yang diubah):
  - `src/downloader.py`:
    - `detect_js_runtimes()` menyalakan runtime JS yang tersedia (`node`, `deno`,
      `bun`) lewat opts `js_runtimes`. Tanpa runtime JS, yt-dlp menyempitkan client
      default YouTube ke `visionos` saja (`_DEFAULT_JSLESS_CLIENTS`) dan solver EJS
      tidak aktif. Env `YT_JS_RUNTIMES` untuk memaksa (`auto`/`none`/`node,deno`).
      Log baru: `[unduh] runtime JS: node (client default yt-dlp lengkap)`.
    - `BOT_CHECK_FALLBACK_CLIENTS` = `("tv", "tv_simply", "ios", "mweb")`;
      `EXTRA_CLIENT_EXAMPLES` = `("android_vr", "web_embedded")` untuk perintah manual.
    - `build_extractor_args(player_client, skip_webpage=False)` memakai bentuk dict
      YouTube yang benar:
      `{"extractor_args": {"youtube": {"player_client": [...], "player_skip": [...]}}}`.
      Bentuk lama `{"youtube": ["player_client=..."]}` **diabaikan yt-dlp** — bug yang
      membuat retry berjalan dengan client default.
    - Percobaan ulang memakai `player_client` **tanpa** `player_skip=webpage`, dan pesan
      kesalahan memperingatkan bahwa opsi itu justru memicu verifikasi bot.
  - `tests/test_bot_check.py`: skenario 2/3 menyesuaikan bentuk opts baru; skenario 8
    baru untuk `detect_js_runtimes()` (auto/none/paksa) dan `skip_webpage`.
  - `.env.example` + `README.md`: `YT_JS_RUNTIMES` dan pembaruan baris troubleshooting.
- Alasan: pengguna melaporkan unduhan yang tadinya berhasil kini kena verifikasi bot.
  Pemeriksaan `git diff` membuktikan **permintaan pertama tidak berubah** oleh kode
  kita, jadi penyebabnya lingkungan: yt-dlp terbaru (2026.8.19) + tidak adanya runtime
  JS di Colab (hanya `deno` yang aktif bawaan) sehingga client default menyempit,
  dan/atau reputasi IP runtime tersebut. Hipotesis awal (`player_skip=webpage`) dicoba
  lalu **dibantah bukti lapangan** (lihat hasil pengujian) dan dibuang.
- Hasil pengujian ulang (uji ke YouTube sungguhan dari mesin ini, video Big Buck Bunny):
  ```
  [OK ] default + node                                   -> judul terbaca, 53 format
  [OK ] default tanpa runtime JS                          -> judul terbaca, 53 format
  [OK ] player_client=tv / tv_simply / ios / mweb          -> OK
  [OK ] player_client=android_vr / web_embedded / web_safari / visionos -> OK
  [GAGAL] player_client=tv + player_skip=webpage           -> BOT-CHECK
  [GAGAL] player_client=android_vr + player_skip=webpage   -> BOT-CHECK
  ```
  - Unduhan penuh memakai program kita: **BERHASIL** — `source.mp4`, 1280x720,
    635 detik, 81,6 MB, progress hook bekerja, log `runtime JS: node`.
  - `tests/test_bot_check.py` lulus (8 skenario): bentuk `extractor_args` benar,
    `detect_js_runtimes()` menghormati `auto`/`none`/`deno`, daftar client env
    bekerja, pesan galat menyebut semua client yang dicoba.
  - Regresi: `py_compile`, `test_highlight` 7/7, `test_progress`,
    `test_transcribe_cuda_fallback`, `test_cuda_diagnostics`, `test_model_gratis`,
    `test_env_writer` lulus; alur penuh `main.py` (file lokal + mock OpenRouter)
    menghasilkan 2 klip, exit 0.
- Catatan: ini **bukan** perbaikan untuk IP yang sudah diblokir. Kalau IP Colab-nya
  ditandai, tidak ada kode yang akan mengatasinya — yang perlu: `cookies.txt`, file
  lokal, atau runtime dengan IP lain (Colab baru / VPN). Yang bisa diperbaiki program
  adalah mencoba lebih banyak client dan memberi petunjuk yang benar.

## F-026 | memperbaiki P-026 (subtitle: cue overlap + teks keluar frame)
- Perubahan (file dan apa yang diubah):
  - `src/subtitles.py` (tulis ulang bagian layout/cue, API lama tetap sama):
    - Konstanta layout: `FONT_SIZE=72`, `MARGIN_L=MARGIN_R=80`, `MARGIN_V=420`,
      `OUTLINE=6`, `SHADOW=3`, `MAX_LINES=2`, `MIN_CUE_SECONDS=0.30`,
      `TEXT_AREA_WIDTH = 1080 - 80 - 80 - 2*(6+3) = 902px`.
    - `measure_text_width()` mengukur lebar teks dengan Pillow memakai file font
      DejaVu Sans Bold yang sama dengan libass; ada estimator cadangan konservatif
      (0,62 em/karakter) kalau Pillow tidak ada, jadi batas tidak pernah longgar.
    - `_split_lines()` sekarang wrap berdasarkan **lebar piksel**: baris pertama diisi
      selagi muat, sisanya baris kedua; kalau tidak muat, cari titik potong paling
      seimbang; kata tunggal yang terlalu lebar dipotong per karakter. Hasilnya
      maksimal 2 baris dan **tidak pernah** melewati lebar area teks.
    - `group_cues()` membagi cue memakai lebar (bukan hanya jumlah karakter) dan
      memanggil `fix_overlaps()`.
    - `fix_overlaps()` baru: cue diurutkan, cue berikutnya dipaksa mulai pada waktu
      selesai cue sebelumnya, cue sebelumnya dipotong bila perlu, durasi minimum
      0,30 detik dijaga. Inilah yang menghapus "dua teks tampil bersamaan".
    - `write_ass()` memakai konstanta layout baru; header tetap `PlayResX/Y=1080/1920`
      dan `WrapStyle: 2` (kita wrap sendiri).
  - `requirements.txt`: tambah `pillow>=10.0.0` (sebelumnya hanya ikut matplotlib,
    jadi tidak dijamin ada).
  - `tests/test_subtitles.py` (baru, 6 bagian): tidak ada cue overlap (dengan
    timestamp kata yang sengaja tumpang tindih), durasi minimum & urutan waktu,
    maksimal 2 baris + lebar baris <= area teks, header .ass benar (PlayRes,
    WrapStyle, FontSize, margin 60-80, MarginV, alignment), .srt tidak overlap, dan
    **render nyata** lewat FFmpeg+libass di atas latar hitam lalu pengukuran piksel
    teks.
- Alasan: batas lebar lama memakai jumlah karakter (22) padahal yang menentukan
  adalah piksel. Dengan FontSize 88 dan margin 90, lebar tersedia 900px, sedangkan
  22 karakter = 1144px dan baris fallback 28 karakter = 1492px. Karena itu teks
  selalu keluar frame. Selain itu `group_cues()` tidak pernah menjamin cue berikutnya
  mulai setelah cue sebelumnya selesai, sehingga timestamp kata yang tumpang tindih
  menghasilkan dua cue aktif bersamaan. Pelajaran dari F-008 (teks harus dipecah
  manual) diperluas: bukan cuma "pecah per \N", tapi pecah **berdasarkan lebar piksel
  yang terukur**, dan tumpang tindih harus dihapus di sumbernya.
- Hasil pengujian ulang:
  - Bukti render sebelum perbaikan (libass di atas latar hitam):
    `t=5,5s -> x=0..1079` (terpotong kiri+kanan), `t=24,2s -> x=1..1078`.
  - Bukti render sesudah perbaikan: `t=0,8 -> x=228..851`, `t=6,0 -> x=243..837`,
    `t=20,0 -> x=204..877`, `t=24,0 -> x=185..896` — semua di dalam frame, bagian
    bawah teks berhenti di y=1498 (di atas area UI platform, MarginV 420).
  - `.ass` hasil run nyata: 19 cue, **0 overlap**, lebar baris maks 896px (<= 902px),
    maksimal 2 baris per cue.
  - `tests/test_subtitles.py` lulus (6 bagian).
  - Alur penuh `main.py` (file lokal + mock OpenRouter): 2 klip 1080x1920 + subtitle
    terbakar, exit 0.
  - Regresi: `test_highlight` 7/7, `test_progress`, `test_bot_check`,
    `test_transcribe_cuda_fallback`, `test_cuda_diagnostics`, `test_model_gratis`,
    `test_env_writer` semuanya lulus.

## F-027 | membuat P-027 (fitur gabung semua klip jadi satu video)
- Perubahan (file dan apa yang diubah):
  - `src/merger.py` (baru):
    - `merge_clips(clips, out_path)`: menulis daftar file untuk demuxer `concat`
      FFmpeg (path absolut, tanda kutip di-escape), lalu encode ulang:
      `libx264` (preset veryfast, CRF 20) + `aac` 160k/48kHz, `-movflags +faststart`,
      dengan filter `scale=1080:1920:force_original_aspect_ratio=decrease,
      pad=1080:1920:(ow-iw)/2:(oh-ih)/2, setsar=1, fps=30, format=yuv420p`.
      Encode ulang (bukan stream copy) dipakai supaya audio tetap sinkron dan
      transisi antar klip mulus.
    - `probe_streams()` (ffprobe) memeriksa hasil: **wajib** ada stream video DAN
      audio; kalau tidak, `MergeError` dilempar.
    - Tidak pernah menghapus klip individual; file daftar sementara dibersihkan di
      blok `finally`.
    - `MergeError` dengan pesan jelas: klip < 2, file tidak ditemukan, hasil kosong,
      atau stream kurang.
  - `src/config.py`: field `merge_clips` dari env `MERGE_CLIPS` (default false),
    tampil di `public_summary()`.
  - `main.py`:
    - argumen `--merge` dan `--no-merge`, plus `resolve_merge()` (CLI menang atas
      `.env`).
    - `merged_file_name()` menghasilkan `00_<slug-video>_gabungan.mp4` dari nama
      klip pertama.
    - setelah semua klip selesai: penggabungan dijalankan; kalau gagal hanya
      `[PERINGATAN]` + pesan, klip individual tetap utuh, dan program tetap exit 0
      (klip utama tetap berguna).
  - `autoclip_colab.py`: `MERGE_CLIPS` masuk `DEFAULTS` + `ENV_ORDER` (agar tidak
    hilang saat `.env` ditulis ulang, pola P-023). File gabungan otomatis ikut
    masuk ke salinan `--drive-dir` dan ke zip hasil karena `collect_outputs()`
    mengambil semua `.mp4` di `output/`.
  - `.env.example`: `MERGE_CLIPS=false`.
  - `tests/test_merge.py` (baru, 6 bagian).
- Alasan: permintaan pengguna adalah "satu file berisi semua klip". Yang penting
  dijaga: (a) video & audio harus utuh dan sinkron -> encode ulang + verifikasi
  ffprobe; (b) subtitle yang sudah tertanam di tiap klip harus tetap ada ->
  re-encode mempertahankan gambar; (c) kegagalan tidak boleh menghapus klip
  individual -> `merge_clips()` tidak pernah menghapus file sumber.
- Hasil pengujian ulang:
  - `tests/test_merge.py` lulus (6 bagian): 3 klip uji digabung -> video=True,
    audio=True, 1080x1920, durasi 6,0s = total klip; 1 klip -> `MergeError`
    "minimal 2 klip" dan klip tetap ada; klip hilang -> pesan "tidak ditemukan" dan
    klip lain tetap ada; urutan klip berpengaruh (warna frame terakhir berbeda
    kalau urutan dibalik); `merged_file_name()` -> `00_tesvideo_gabungan.mp4`.
  - Alur penuh `main.py --merge` (file lokal + mock OpenRouter): 2 klip +
    `00_testvideo-id_gabungan.mp4` (17,8 MB). ffprobe: h264 1080x1920 + aac,
    durasi 65,08s = 35s + 30s. Subtitle masih terbakar di file gabungan
    (frame t=2s: x=229..850, t=40s: x=192..888, keduanya di dalam frame).
  - Jalur Colab: `autoclip_colab.py ... -- --merge` -> file gabungan muncul di
    ringkasan, tersalin ke `--drive-dir`, dan ada di dalam zip
    (`output/00_testvideo-id_gabungan.mp4`).
  - Regresi: seluruh test lama lulus (lihat daftar di bagian F-026).

## F-028 | memperbaiki P-028 (face tracking: crop diam -> crop bergerak mengikuti wajah)
- Perubahan (file dan apa yang diubah):
  - `src/face_track.py` (file baru, ~470 baris):
    - `FaceDetector`: detektor utama **YuNet** (DNN, `cv2.FaceDetectorYN`,
      model `assets/face_detection_yunet_2023mar.onnx` 227 KB dari opencv_zoo),
      cadangan **Haar cascade** (`assets/haarcascade_frontalface_default.xml`).
      Frame diperkecil ke `FACE_DETECT_WIDTH` (default 640 px) supaya deteksi
      cepat, lalu koordinat dikembalikan ke skala asli. Wajah yang lebih kecil
      dari `min_face_ratio` dibuang (anti false positive).
    - `track_faces()`: sampel wajah pada interval tetap (default 10 Hz). Video
      dibaca **berurutan** (seek sekali di awal, lalu `grab()` untuk melompati
      frame yang tidak perlu) supaya posisi sampel presisi.
    - `_pick_face()`: memilih wajah **terbesar yang masih dekat** dengan posisi
      sebelumnya -> tidak berganti orang saat ada dua wajah di frame.
    - `smooth_track()`: celah diisi (interpolasi linear, tahan di ujung),
      outlier dibuang dengan filter median, lalu dirata-rata (jendela
      `FACE_TRACK_SMOOTH`, default 5).
    - `crop_positions()`: landscape -> crop bergerak **horizontal** (wajah dikejar
      ke tengah); portrait -> crop bergerak **vertikal** (wajah di 1/4 tinggi
      frame, bukan tengah, supaya ada ruang untuk subtitle).
    - `write_sendcmd()`: menulis file perintah `sendcmd` untuk filter `crop`
      FFmpeg. Tiap perintah **wajib** diakhiri `;` (tanpa itu FFmpeg menolak
      filenya: "Missing separator or extraneous data").
  - `src/clipper.py`:
    - `plan_face_crop()` (baru): menyusun rencana crop bergerak + file
      perintah, mengembalikan objek `FaceCrop` (filter + file + statistik).
    - `face_crop_filter()` (lama) tetap ada sebagai crop **statis** (posisi
      median), sekarang memakai detektor baru.
    - `cut_clip()` memakai `plan_face_crop()`; file perintah selalu dihapus
      setelah render (`finally`), dan kalau render gagal -> fallback crop tengah.
  - `src/config.py`: kunci baru `FACE_TRACK_SAMPLE_FPS` (default 10),
    `FACE_TRACK_SMOOTH` (default 5), `FACE_DETECT_WIDTH` (default 640) +
    validasi rentang + tampilannya di `public_summary()`.
  - `main.py`: ketiga nilai itu diteruskan ke `cut_clip()`.
  - `autoclip_colab.py`: ketiga kunci baru masuk `DEFAULTS` + `ENV_ORDER` supaya
    tidak hilang saat `.env` ditulis ulang (pola P-023).
  - `assets/face_detection_yunet_2023mar.onnx` (baru, 227 KB, opencv_zoo,
    Apache-2.0) + `assets/test_face_portrait.jpg` (fixture uji, potret resmi
    White House = domain publik) + `assets/README.md` (asal & lisensi).
  - `tests/test_face_tracking.py` (baru, 7 bagian).
  - `.env.example`, `README.md` (bagian "Crop yang Mengikuti Wajah" + tabel
    `.env` + troubleshooting), `AGENTS.md` (struktur, aturan kode, pengujian).
- Alasan:
  1. Akar masalahnya bukan "deteksinya kurang sensitf", tapi **crop-nya diam**:
     satu posisi median dipakai untuk seluruh durasi klip, jadi wajah yang
     bergerak langsung keluar frame. Perbaikannya harus membuat jendela crop
     **bergerak**, bukan hanya mendeteksi lebih sering.
  2. FFmpeg bisa menggerakkan jendela crop saat render lewat filter `sendcmd`
     + perintah `crop x <nilai>` (sudah diuji: crop bergeser tepat pada
     waktunya). Jadi tidak perlu encode ulang per frame.
  3. YuNet dipilih sebagai detektor utama karena Haar cascade hanya mengenali
     wajah frontal dan sering gagal pada wajah kecil/miring; modelnya kecil
     (227 KB), gratis, dan open source.
  4. Pelajaran F-026 (ukur, jangan kira-kira) diterapkan: lebar/posisi diuji
     dalam **piksel** terhadap ground truth Fixture, bukan dikagumi dari
     tampilan.
  5. Pelajaran P-023 (kunci `.env` boleh hilang kalau tidak dijaga) diterapkan:
     kunci baru langsung masuk `DEFAULTS`/`ENV_ORDER` runner Colab.
- Hasil pengujian ulang:
  - **Bukti "sebelum"** (video uji 1280x720, wajah bergerak x=80 -> x=900):
    crop lama diam di `crop=1080:1920:1216:0` -> wajah **hilang di 101 dari 200
    frame** hasil render (t=0..2 dan t=6..7 tidak ada wajah sama sekali).
  - **Bukti "sesudah"**: `[clipper] face tracking: 80/80 sampel wajah terdeteksi
    (detektor yunet); crop bergerak mengikuti wajah.` -> wajah ada di
    **200/200 frame**, posisi horizontal 0.458..0.547 (tengah = 0.500).
  - Galat lintasan vs ground truth: rata-rata **0,9 px**, maks 25,9 px
    (efek tepi jendela perataan di detik pertama).
  - `tests/test_face_tracking.py` **lulus (7 bagian)**: 60/60 sampel terdeteksi,
    galat lintasan rata-rata 6,2 px; render 1080x1920 dengan wajah di 150/150
    frame dan simpangan dari tengah maks 5,8%; file `sendcmd` 60 baris,
    semua diakhiri `;`, nilainya berubah-ubah (crop bergerak); video tanpa wajah
    -> `plan_face_crop` mengembalikan `None` dan hasil tetap 1080x1920 (crop
    tengah); perataan: celah terisi & deteksi liar 500 dibuang; sumber portrait
    -> perintah `crop y` bergerak (y=77 -> 480) dan hasil tetap 1080x1920.
  - Jalur cadangan: `FACE_MODEL_FILE` menunjuk file yang tidak ada ->
    backend otomatis `haar` (80/80 sampel terdeteksi); folder `assets/` kosong
    -> backend `none` -> `plan_face_crop` = None -> crop tengah.
  - Alur penuh `main.py` (file lokal + mock OpenRouter, `--face-tracking`):
    23 segmen transkripsi, 2 klip (380/380 dan 300/300 sampel wajah terdeteksi),
    hasil 1080x1920; pada klip 1 wajah ada di 950/950 frame dengan cx
    0.494..0.506 (tepat di tengah).
  - Regresi: `test_highlight` 7/7, `test_progress`, `test_bot_check`,
    `test_cuda_diagnostics`, `test_model_gratis`, `test_env_writer`,
    `test_transcribe_cuda_fallback`, `test_subtitles`, `test_merge` semuanya
    lulus; `main.py --help` dan `autoclip_colab.py --help` normal.
- Catatan: file `sendcmd` **wajib** diakhiri `;` — ini sempat membuat FFmpeg
  menolak filenya ("Missing separator or extraneous data found at the end of
  interval #0") dan program diam-diam memakai fallback crop tengah. Pelajaran:
  kalau hasil render tiba-tiba "fallback", periksa dulu pesan error FFmpeg-nya
  (kode lama hanya mencetak "face tracking gagal saat render").

## F-029 | memperbaiki P-029 (file hasil face tracking 3x lebih besar)
- Perubahan (file dan apa yang diubah):
  - `src/clipper.py` -> `plan_face_crop()`: deadband perintah `sendcmd` bukan lagi
    1 piksel tetap, tapi `max(2, out_w * 0.004)` -> ~4 piksel di frame hasil
    1080x1920 (0,4% lebar, di bawah batas penglihatan).
  - `src/face_track.py` -> `write_sendcmd()`: parameter `deadband` sekarang
    punya penjelasan (goyang kecil -> file jauh lebih besar).
- Alasan: deadband 1 piksel **di ruang hasil scale** (3414 piksel lebar untuk
  1280x720) sama dengan 0,37 piksel sumber, jadi noise deteksi wajah selalu
  lolos dan crop terus bergeser. deadband 0,4% lebar frame hasil cukup besar
  untuk memblokir noise, tapi tetap jauh di bawah yang terlihat.
- Hasil pengujian ulang:
  - Video uji dengan wajah **diam**, klip 38 detik: file hasil **9,2 MB ->
    2,9 MB** (kembali seperti crop statis), sedangkan posisi wajah tetap
    0,494..0,506 (tepat di tengah) dan terdeteksi di 950/950 frame.
  - `tests/test_face_tracking.py` tetap **LULUS** (7 bagian): lintasan bergerak
    (60 perintah, nilai berubah-ubah), wajah di 150/150 frame, simpangan dari
    tengah maks 5,8%.
- Catatan: pelajaran F-026 (ukur jangan kira-kira) lagi: masalah "file jadi
  besar" baru ketahuan karena **ukur ukuran file**, bukan karena dikeluh.

## F-028b | tambahan F-028 (opsi CLI face tracking + panduan cara pakai)
- Perubahan (file dan apa yang diubah):
  - `main.py`: tiga opsi CLI baru yang **menimpa** nilai `.env` untuk satu kali
    jalan: `--face-sample-fps`, `--face-smooth`, `--face-detect-width`.
    `resolve_face_settings()` collects nilai (CLI menang atas `.env`), log baris
    `#face: sampel=.../detik perataan=... lebar_deteksi=...px` dicetak kalau
    face tracking aktif, dan nilainya diteruskan ke `cut_clip()`.
  - `autoclip_colab.py`:
    - `face_model_report()` + baris baru di `--check-env`:
      `Wajah : yunet (227 KB) - akurat` (atau `haar` / `tidak ada`).
    - epilog `--help` menyebut `-- --face-sample-fps 20` sebagai contoh
      argumen yang diteruskan ke `main.py`.
  - `CARA_PAKAI.md` (file baru, 278 baris): resep perintah siap pakai —
    persiapan, cara paling sederhana, **cara crop ikut wajah** (+ cara
    menyetel kepekaan/keelusan), gabung klip, subtitle, hemat waktu, YouTube
    bot check, dan bagian **Google Colab** lengkap (persiapan, `--check-env`,
    clone, contoh perintah dengan `--face-tracking`, tabel aturan Colab,
    rate limit model gratis) + daftar lengkap semua opsi.
  - `README.md`: tabel "Yang Bisa Dilakukan" (fitur -> cara pakai), bagian
    "Crop yang Mengikuti Wajah" (tabel sebelum/sesudah, 4 langkah, tabel
    penyesuaian), bagian "Face tracking di Colab", baris troubleshooting
    model wajah, dan tautan ke `CARA_PAKAI.md`.
  - `AGENTS.md`: opsi CLI baru di tabel, bagian "Face tracking di Colab",
    `CARA_PAKAI.md` di struktur proyek.
- Alasan: pengaturan face tracking sebelumnya hanya bisa diubah lewat `.env`,
  jadi harus mengedit file tiap kali mau bereksperimen. Pola yang sudah ada
  di proyek (`--max-clips` menimpa `MAX_CLIPS`, `--progress-seconds` menimpa
  `DOWNLOAD_PROGRESS_SECONDS`) diterapkan juga ke face tracking, sehingga
  "--face-sample-fps 20" bisa dipakai tanpa menyentuh `.env` — termasuk lewat
  Colab (`-- --face-sample-fps 20`).
- Hasil pengujian ulang:
  - `main.py --help` menampilkan 3 opsi baru dengan benar; tidak ada galat
    argparse (pelajaran P-018: jalur baru harus dijalankan, bukan hanya ditulis).
  - Alur penuh `main.py --face-tracking --face-sample-fps 15 --face-smooth 7`:
    log `#face: sampel=15/detik perataan=7 lebar_deteksi=640px`, 570/570 sampel
    wajah terdeteksi, 1 klip 1080x1920.
  - Jalur Colab `autoclip_colab.py --face-tracking -- --face-sample-fps 12
    --face-smooth 3 --max-clips 1`: exit 0, 6 file hasil, zip terbentuk
    (11,5 MB).
  - `autoclip_colab.py --check-env --skip-install` menampilkan baris baru
    `Wajah : yunet (227 KB) - akurat`.
