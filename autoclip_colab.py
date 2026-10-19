#!/usr/bin/env python3
"""AUTO CLIP - pembungkus sekali jalan untuk Google Colab.

File ini TIDAK berisi logika AUTO CLIP; dia hanya menyiapkan lingkungan Colab lalu
memanggil `main.py` yang sudah ada. Semua tool tetap gratis & open source.

Yang ditangani file ini:
  1. Menemukan proyek (sudah di folder yang sama / `--repo` untuk clone dari Git).
  2. Memasang FFmpeg + font (apt tanpa `sudo` - Colab sudah root).
  3. Memasang dependency Python dari `requirements.txt` memakai `sys.executable`
     (bukan `venv/`, karena Colab tidak memakai venv).
  4. Menyiapkan pustaka CUDA 12 untuk `ctranslate2` (faster-whisper di GPU), lalu
     memverifikasi `ctranslate2` benar-benar bisa melihat GPU.
  5. Menyusun `.env`: API key diambil dari Colab Secrets / variabel shell / prompt
     tersamar. Model wajib berakhiran `:free` (aturan sama dengan src/config.py).
  6. Menjalankan `main.py` dan meneruskan kode keluar + argumen CLI apa adanya.
  7. Mengambil hasil: menyalin ke Google Drive (opsional) lalu zip `output/`.

Cara pakai di Colab (notebook):

    # Opsi A: repo sudah ada di disk (mis. hasil git clone)
    !python autoclip_colab.py --input "https://www.youtube.com/watch?v=VIDEO_ID"

    # Opsi B: repo belum ada di Colab -> clone sekalian
    !python autoclip_colab.py --repo https://github.com/USER/autoclip.git \
        --input "https://www.youtube.com/watch?v=VIDEO_ID"

    # Opsi C: file video lokal ada di Google Drive
    from google.colab import drive
    drive.mount('/content/drive')
    !python autoclip_colab.py \
        --input "/content/drive/MyDrive/videos/videosaya.mp4" \
        --drive-dir "/content/drive/MyDrive/autoclip"

Setiap langkah bisa dikontrol:
    --skip-install   lewati apt-get + pip install (buat iterasi cepat)
    --check-env      hanya periksa lingkungan lalu keluar
    --no-download    jangan zip/unduh hasil
    --cpu            paksa CPU walau GPU tersedia
    -- <args>        argumen tambahan untuk main.py, mis.
                    -- --max-clips 3 --face-tracking --keep-temp
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import NoReturn

# ------------------------------------------------------------------ util dasar

START_TIME = time.time()
WIDTH = 70


def log(msg: str = "") -> None:
    print(f"[colab] {msg}" if msg else "[colab]", flush=True)


def step(n: int, total: int, msg: str) -> None:
    log("")
    log(f"=== [{n}/{total}] {msg} ===")


def rule(title: str = "") -> None:
    log("")
    log("=" * WIDTH)
    if title:
        log(title)
        log("=" * WIDTH)


def warn(msg: str) -> None:
    print(f"[colab] PERINGATAN: {msg}", flush=True)


def die(msg: str, code: int = 1) -> NoReturn:
    print(f"\n[colab] GAGAL: {msg}\n", flush=True)
    raise SystemExit(code)


def run(
    cmd: list[str],
    cwd: Path | None = None,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess:
    """Jalankan perintah; stdout/stderr langsung tampil di log Colab."""
    printable = " ".join(cmd)
    log(f"$ {printable}")
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        die(f"perintah gagal (exit {proc.returncode}): {printable}")
    return proc


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def in_colab() -> bool:
    """True kalau dijalankan di Google Colab (bukan di mesin lokal)."""
    if "google.colab" in sys.modules:
        return True
    return Path("/content").is_dir()


# ------------------------------------------------------------------ 1. proyek

GITHUB_SKELETON = """Buat repo di GitHub (https://github.com/new) dengan isi proyek ini:

    git init -b main
    git add -A                 # .env, venv/, output/, temp/ sudah diabaikan .gitignore
    git commit -m "AUTO CLIP"
    git remote add origin https://github.com/USER/autoclip.git
    git push -u origin main

Lalu di Colab:

    !python autoclip_colab.py --repo https://github.com/USER/autoclip.git \\
        --input "https://www.youtube.com/watch?v=VIDEO_ID" \\
        --model google/gemini-2.0-flash-exp:free
"""


def looks_like_project(path: Path) -> bool:
    return (path / "main.py").is_file() and (path / "src" / "config.py").is_file()


def is_repo_url(value: str) -> bool:
    """Bedakan URL git dari path filesystem (lihat problem.md P-012)."""
    return (
        "://" in value
        or value.startswith("git@")
        or value.startswith("git+")
    )


def normalize_repo_url(url: str) -> str:
    """Bolehceq HTTPS tanpa `.git`, tapi URL ber-skema / SSH tidak boleh diubah."""
    url = url.strip()
    if is_repo_url(url):
        return url
    return url if url.endswith(".git") else f"{url.rstrip('/')}.git"


def locate_project(script_dir: Path, explicit: str | None = None) -> Path | None:
    """Cari folder proyek yang berisi main.py + src/config.py.

    Urutan: --repo bila itu path lokal > $AUTOCLIP_REPO > folder script >
    /content/autoclip > subfolder /content yang cocok. Return None kalau tidak ketemu
    (URL git TIDAK diproyeksi jadi path - lihat problem.md P-012).
    """
    candidates: list[Path] = []
    if explicit and not is_repo_url(explicit):
        candidates.append(Path(explicit).expanduser())
    env_repo = os.environ.get("AUTOCLIP_REPO", "")
    if env_repo and not is_repo_url(env_repo):
        candidates.append(Path(env_repo).expanduser())
    candidates += [
        script_dir,
        script_dir.parent,
        Path.cwd(),
        Path.cwd() / "autoclip",
        Path("/content/autoclip"),
        Path("/content/AUTO-CLIP"),
    ]
    content = Path("/content")
    if content.is_dir():
        candidates.extend(sorted(p for p in content.iterdir() if p.is_dir()))

    for cand in candidates:
        if looks_like_project(cand):
            return cand.resolve()
    return None


def clone_destinations() -> list[Path]:
    """Kandidat folder tujuan clone, dari yang paling wajar dipakai.

    Di Colab selalu `/content/autoclip`. Di luar Colab: `./autoclip`, lalu folder
    di samping skrip.
    """
    if in_colab():
        return [Path("/content/autoclip"), Path(__file__).resolve().parent / "autoclip"]
    return [
        Path.cwd() / "autoclip",
        Path(__file__).resolve().parent / "autoclip",
    ]


def ensure_repo(repo_hint: str | None) -> Path:
    """Clone proyek dari --repo / $AUTOCLIP_REPO kalau belum ada di disk."""
    url = repo_hint or os.environ.get("AUTOCLIP_REPO") or ""

    # 1) repo mungkin sudah ada di lokasi standar (run kedua, atau clone manual)
    for cand in clone_destinations():
        if looks_like_project(cand):
            log(f"Repo sudah ada di {cand.resolve()} -> tidak di-clone ulang.")
            return cand.resolve()

    if not url:
        die(
            "Folder proyek AUTO CLIP tidak ditemukan (butuh main.py + src/config.py).\n"
            "  Cara memperbaiki:\n"
            "    1) taruh file ini di dalam folder repo AUTO CLIP, atau\n"
            "    2) jalankan ulang dengan --repo https://github.com/USER/autoclip.git\n"
            "       (atau set variabel lingkungan AUTOCLIP_REPO=<url>)\n\n"
            f"Contoh lengkap:\n{GITHUB_SKELETON}"
        )
    if not have("git"):
        die("git tidak ditemukan di PATH; clone repo secara manual lalu ulangi.")
    if not is_repo_url(url):
        local = Path(url).expanduser()
        if looks_like_project(local):
            log(f"--repo menunjuk folder lokal: {local.resolve()}")
            return local.resolve()
        if local.exists():
            die(
                f"--repo menunjuk folder lokal {local} yang bukan proyek AUTO CLIP\n"
                "  (butuh main.py + src/config.py). Perbaiki path-nya atau pakai URL git."
            )

    candidates = clone_destinations()
    free = [c for c in candidates if not c.exists()]
    if not free:
        die(
            "Semua folder tujuan clone sudah terisi tapi bukan proyek AUTO CLIP:\n"
            + "".join(f"  - {c}\n" for c in candidates)
            + "  Hapus salah satu atau jalankan ulang dengan --repo <path folder>."
        )
    dest = free[0]

    url = normalize_repo_url(url)
    log(f"Cloning {url} -> {dest}")
    run(["git", "clone", "--depth", "1", url, str(dest)])
    if not looks_like_project(dest):
        die(f"Clone selesai tapi {dest} tidak berisi main.py + src/config.py")
    log("Clone beres.")
    return dest


# ------------------------------------------------------------------ 2. FFmpeg

def setup_ffmpeg() -> None:
    """Pasang ffmpeg/ffprobe + font DejaVu (dipakai libass untuk subtitle)."""
    if have("ffmpeg") and have("ffprobe"):
        log("ffmpeg/ffprobe sudah ada -> lewati instalasi apt.")
        cache_fonts()
        return

    if os.name != "posix":
        die("FFmpeg tidak ditemukan dan sistem ini bukan Linux. Pasang manual lalu ulangi.")

    if os.geteuid() != 0:
        die(
            "Tidak bisa memasang FFmpeg otomatis karena bukan root.\n"
            "  Jalankan dulu di cell Colab: !apt-get update && apt-get install -y ffmpeg"
        )

    log("Memasang ffmpeg + fonts-dejavu + git (beberapa detik)...")
    run(["apt-get", "update", "-qq"], timeout=900)
    run(
        ["apt-get", "install", "-y", "-qq", "ffmpeg", "fonts-dejavu-core", "git"],
        timeout=1800,
    )

    for tool in ("ffmpeg", "ffprobe"):
        if not have(tool):
            die(f"{tool} masih tidak ditemukan setelah apt-get install.")

    cache_fonts()
    ver = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout
    first = ver.splitlines()[0] if ver.strip() else "tidak diketahui"
    log(f"FFmpeg siap: {first}")


def cache_fonts() -> None:
    """Segarkan cache font supaya libass tidak diam-diam gagal merender teks."""
    if have("fc-cache"):
        subprocess.run(["fc-cache", "-f"], capture_output=True, text=True)


# ------------------------------------------------------------------ 3. dependency

IMPORT_CHECK = "import dotenv, yt_dlp, faster_whisper, requests, cv2, numpy"


def python_deps_ok(project: Path) -> bool:
    """Cek cepat apakah semua paket utama sudah bisa diimpor."""
    proc = subprocess.run(
        [sys.executable, "-c", f"{IMPORT_CHECK}; print('ok')"],
        cwd=str(project), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # Error klasik Colab: cv2 terpasang tapi butuh libGL.so.1 yang tidak ada.
        if "libGL" in (proc.stderr or ""):
            warn("cv2 gagal import (libGL.so.1 tidak ada) -> pasang ulang versi headless.")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "--force-reinstall",
                 "opencv-python-headless"],
                capture_output=True, text=True,
            )
            return subprocess.run(
                [sys.executable, "-c", IMPORT_CHECK],
                cwd=str(project), capture_output=True, text=True,
            ).returncode == 0
        return False
    return True


def setup_python_deps(project: Path) -> None:
    """Pasang requirements.txt dengan python yang sedang dipakai (Colab: /usr/bin/python3)."""
    if python_deps_ok(project):
        log("Semua dependency Python sudah terpasang -> lewati pip install.")
        return

    req = project / "requirements.txt"
    if not req.is_file():
        die(f"{req} tidak ditemukan; tidak bisa memasang dependency.")

    log("Memasang dependency Python (bisa beberapa menit)...")
    run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
         "-r", str(req)],
        timeout=3600,
    )
    if not python_deps_ok(project):
        proc = subprocess.run(
            [sys.executable, "-c", IMPORT_CHECK],
            cwd=str(project), capture_output=True, text=True,
        )
        die(f"Dependency masih tidak lengkap setelah pip install:\n{(proc.stderr or '')[-1500:]}")


# ------------------------------------------------------------------ 4. GPU / CUDA

def gpu_name() -> str:
    if not have("nvidia-smi"):
        return ""
    proc = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True, text=True,
    )
    if proc.stdout.strip():
        return proc.stdout.strip().splitlines()[0].strip()
    return ""


def nvidia_lib_dirs() -> list[Path]:
    """Folder pustaka NVIDIA (ctranslate2 membutuhkannya di LD_LIBRARY_PATH).

    Dipindai dari SELURUH `sys.path` (site-packages, dist-packages, dan user site),
    bukan hanya dari `nvidia.__file__`: kalau pip memasang paket ke pohon lain,
    `nvidia.__file__` akan tetap menunjuk paket lama sehingga folder barunya tidak
    pernah ikut dipindai (lihat problem.md P-021).
    """
    import site

    dirs: list[Path] = []
    roots: list[Path] = []
    try:
        roots.extend(Path(p) for p in site.getsitepackages())
    except Exception:
        pass
    try:
        user_site = site.getusersitepackages()
        if isinstance(user_site, str):
            roots.append(Path(user_site))
    except Exception:
        pass
    roots.extend(Path(p) for p in sys.path if p)

    seen: set[str] = set()

    def tambah(path: Path) -> None:
        teks = str(path)
        if teks not in seen:
            seen.add(teks)
            dirs.append(path)

    for root in roots:
        nvidia = root / "nvidia"
        if not nvidia.is_dir():
            continue
        for pkg in sorted(nvidia.iterdir()):
            lib = pkg / "lib"
            if lib.is_dir():
                tambah(lib)
        # beberapa wheel menaruh semua .so langsung di nvidia/cu12/lib atau nvidia/lib
        for nama in ("cu12", "cu13", "lib"):
            lib = nvidia / nama
            if lib.is_dir():
                tambah(lib)

    for extra in ("/usr/local/cuda/lib64", "/usr/local/cuda-12/lib64",
                  "/usr/lib/x86_64-linux-gnu"):
        if Path(extra).is_dir():
            tambah(Path(extra))
    return dirs


CUDA_LIBS = ("libcublas.so.12", "libcudnn.so.9")
CUDA_OPTIONAL_LIBS = ("libcudart.so.12", "libcublasLt.so.12")

# Probe CUDA yang melaporkan-json apa pun yang salah, bukan cuma "gagal/tidak".
# Probe lama (lihat problem.md P-019) mengembalikan satu nilai False untuk tiga
# kondisi berbeda, dan pemeriksaan kedua dipanggil dengan quiet=True, jadi alasan
# sebenarnya tidak pernah sampai ke log.
CUDA_PROBE = r"""
import ctypes, glob, json, os, site, sys
info = {
    "python": sys.executable,
    "ld_path": os.environ.get("LD_LIBRARY_PATH", ""),
    "libs": {},
    "found": {},
    "missing": {},
    "errors": {},
}

def candidate_dirs():
    # Semua folder yang mungkin berisi .so NVIDIA: seluruh pohon site-packages
    # (bukan hanya nvidia.__file__), plus LD_LIBRARY_PATH, plus CUDA bawaan.
    roots = []
    try:
        roots.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        user = site.getusersitepackages()
        if isinstance(user, str):
            roots.append(user)
    except Exception:
        pass
    roots.extend(p for p in sys.path if p)
    dirs = []
    for root in roots:
        nvidia = os.path.join(root, "nvidia")
        if not os.path.isdir(nvidia):
            continue
        for pkg in sorted(os.listdir(nvidia)):
            d = os.path.join(nvidia, pkg, "lib")
            if os.path.isdir(d):
                dirs.append(d)
        for name in ("cu12", "cu13", "lib"):
            d = os.path.join(nvidia, name)
            if os.path.isdir(d):
                dirs.append(d)
    dirs.extend(p for p in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep) if p)
    dirs.extend(d for d in ("/usr/local/cuda/lib64", "/usr/local/cuda-12/lib64",
                            "/usr/lib/x86_64-linux-gnu") if os.path.isdir(d))
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out

DIRS = candidate_dirs()

def find_lib(soname):
    # 1) andalkan loader (paling akurat: meniruqyat ctranslate2)
    try:
        ctypes.CDLL(soname)
        return "ok", None
    except OSError as exc:
        pesan = str(exc)
    # 2) cari sendiri di folder kandidat
    for d in DIRS:
        for hit in sorted(glob.glob(os.path.join(d, soname))):
            try:
                ctypes.CDLL(hit, mode=ctypes.RTLD_GLOBAL)
                return "loaded:" + hit, None
            except OSError as exc2:
                return "gagal:" + hit + " -> " + str(exc2), None
    # 3) tidak ada; laporkan versi lain yang terpasang (indikasi wheel CUDA 13)
    lain = []
    for d in DIRS:
        lain.extend(sorted(glob.glob(os.path.join(d, "lib" + soname[3:-3] + "*"))))
    return pesan, sorted(os.path.basename(p) for p in lain)[:4]

try:
    import ctranslate2 as ct
    info["ctranslate2"] = getattr(ct, "__version__", "?")
    try:
        info["device_count"] = ct.get_cuda_device_count()
    except Exception as exc:
        info["device_count"] = -1
        info["errors"]["get_cuda_device_count"] = type(exc).__name__ + ": " + str(exc)
except Exception as exc:
    info["errors"]["import ctranslate2"] = type(exc).__name__ + ": " + str(exc)

for lib in %s:
    hasil, lain = find_lib(lib)
    info["libs"][lib] = hasil
    if hasil.startswith("loaded:"):
        info["found"][lib] = hasil.split(":", 1)[1]
    elif hasil.startswith("gagal:"):
        info["found"][lib] = hasil.split(" -> ", 1)[0].split(":", 1)[1]
    if lain:
        info["missing"][lib] = lain

try:
    import nvidia
    info["nvidia_dir"] = getattr(nvidia, "__file__", None) and os.path.dirname(nvidia.__file__)
except Exception as exc:
    info["errors"]["import nvidia"] = type(exc).__name__ + ": " + str(exc)
print(json.dumps(info))
""" % repr(CUDA_LIBS + CUDA_OPTIONAL_LIBS)


def cuda_diagnostics() -> dict:
    """Kumpulkan detail GPU/pustaka CUDA dari interpreter yang akan dipakai.

    Jalan sebagai subprocess supaya persis seperti kondisi main.py nanti
    (LD_LIBRARY_PATH ikut terambil dari environment proses ini).
    """
    proc = subprocess.run(
        [sys.executable, "-c", CUDA_PROBE],
        capture_output=True, text=True,
    )
    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {
        "python": sys.executable,
        "ld_path": os.environ.get("LD_LIBRARY_PATH", ""),
        "libs": {},
        "errors": {
            "probe": (proc.stderr or proc.stdout or "tanpa output").strip()[-400:]
            or f"keluar dengan kode {proc.returncode}"
        },
    }


def jumlah_ld_path(diag: dict) -> int:
    return len([p for p in (diag.get("ld_path") or "").split(os.pathsep) if p])


def lib_loaded(state: str) -> bool:
    """Status pustaka dari probe: 'ok' (loader) atau 'loaded:<path>' (muat paksa)."""
    return state == "ok" or state.startswith("loaded:")


def cuda_ready(diag: dict) -> bool:
    """True kalau ctranslate2 menghitung GPU dan pustaka wajibnya termuat."""
    if int(diag.get("device_count") or 0) <= 0:
        return False
    libs = diag.get("libs") or {}
    return all(lib_loaded(libs.get(lib, "")) for lib in CUDA_LIBS)


def explain_cuda_failure(diag: dict, gpu: str) -> str:
    """Satu blok teks yang menyebut penyebab kegagalan + cara memperbaikinya."""
    lines: list[str] = []
    count = diag.get("device_count")
    if diag.get("errors", {}).get("import ctranslate2"):
        lines.append(f"  ctranslate2 tidak bisa diimpor: {diag['errors']['import ctranslate2']}")
    if count is None:
        lines.append("  jumlah GPU tidak diketahui (probe gagal, lihat 'errors' di bawah).")
    elif int(count) <= 0:
        lines.append(
            "  ctranslate2 melihat 0 GPU, padahal nvidia-smi melihat "
            f"'{gpu}'. Artinya driver/pustaka CUDA tidak terbaca oleh ctranslate2."
        )
        lines.append(
            "    - coba: pip install nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 "
            "'nvidia-cudnn-cu12==9.*'"
        )
        lines.append("    - atau restart runtime Colab, lalu ulangi --check-env")
    broken = [
        (lib, state)
        for lib, state in (diag.get("libs") or {}).items()
        if not lib_loaded(state)
    ]
    if broken:
        if count is not None and int(count) > 0:
            lines.append(
                f"  GPU '{gpu}' terlihat oleh ctranslate2, tapi pustaka CUDA di bawah "
                "belum bisa dimuat."
            )
        lines.append("  Pustaka yang gagal dimuat:")
        for lib, state in broken:
            if state.startswith("gagal:"):
                path, _, err = state.partition(" -> ")
                lines.append(f"    - {lib}: ada di {path[len('gagal:'):]} tapi gagal: {err}")
            elif "cannot open shared object file" in state:
                lines.append(
                    f"    - {lib}: TIDAK ADA di folder mana pun yang dipindai "
                    f"({jumlah_ld_path(diag)} di LD_LIBRARY_PATH): {state}"
                )
                if (diag.get("missing") or {}).get(lib):
                    lines.append(
                        "      yang terpasang hanya versi lain: "
                        + ", ".join(diag["missing"][lib])
                        + " (ctranslate2 butuh .so.12)"
                    )
                lines.append(
                    "      perbaiki: pip install --force-reinstall --no-deps "
                    "nvidia-cublas-cu12 nvidia-cuda-runtime-cu12"
                )
            else:
                lines.append(f"    - {lib}: {state}")
    muat_paksa = diag.get("found") or {}
    if muat_paksa:
        lines.append("  Pustaka yang dimuat lewat path absolut:")
        lines += [f"    - {lib}: {path}" for lib, path in muat_paksa.items()]
    if diag.get("errors", {}).get("get_cuda_device_count"):
        lines.append(f"  get_cuda_device_count(): {diag['errors']['get_cuda_device_count']}")
    if diag.get("errors", {}).get("probe"):
        lines.append(f"  probe gagal: {diag['errors']['probe']}")
    nvidia_dir = diag.get("nvidia_dir")
    if nvidia_dir:
        lines.append(f"  paket nvidia terpasang di: {nvidia_dir}")
    else:
        lines.append("  paket pip nvidia-cublas/cudnn tidak terlihat di interpreter ini.")
    lines.append(f"  python: {diag.get('python', '?')}")
    return "\n".join(lines)


def ctranslate2_sees_cuda(quiet: bool = False) -> bool:
    """True kalau ctranslate2 benar-benar bisa menghitung di GPU.

    `get_cuda_device_count()` saja tidak cukup: fungsi itu tetap mengembalikan
    jumlah GPU walau cuBLAS/torch tidak bisa dimuat, sehingga wrapper pernah
    melaporkan "GPU dipakai" lalu pipeline crash dengan
    `libcublas.so.12 is not found` (lihat problem.md P-015). Karena itu pustaka
    yang dibutuhkan ctranslate2 ikut dicek lewat loader. Kalau gagal dan
    `quiet=False`, penyebab spesifiknya ikut dicetak (problem.md P-019).
    """
    diag = cuda_diagnostics()
    if cuda_ready(diag):
        return True
    if not quiet:
        warn(
            "GPU terdeteksi tapi ctranslate2 belum siap:\n"
            + explain_cuda_failure(diag, gpu_name() or "tidak ada")
        )
    return False


def install_cuda_libs() -> bool:
    """Pasang paket pip pustaka CUDA. Return True kalau semua benar-benar terpasang.

    `pip install -q` menyembunyikan hasilnya, sehingga program tidak pernah tahu
    apakah paketnya masuk ke interpreter yang sedang dipakai atau gagal diam-diam
    (lihat problem.md P-019). Karena itu output-nya ditangkap dan diperiksa lewat
    `import nvidia` + `cuda_diagnostics()`.
    """
    cmd = [
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
        "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*", "nvidia-cuda-runtime-cu12",
        "nvidia-cufft-cu12", "nvidia-curand-cu12",
    ]
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-10:]
        warn("pip gagal memasang pustaka CUDA:\n  " + "\n  ".join(tail))
        return False
    diag = cuda_diagnostics()
    if not diag.get("nvidia_dir"):
        warn(
            "pip selesai tapi paket `nvidia` tidak terlihat dari interpreter "
            f"{sys.executable}. Kemungkinan pip dan program memakai interpreter berbeda."
        )
        return False
    log(f"Paket pustaka CUDA terpasang di: {diag['nvidia_dir']}")
    return True


def set_cuda_ld_path() -> int:
    """Tambahkan semua folder pustaka NVIDIA ke LD_LIBRARY_PATH. Return jumlahnya."""
    existing = [p for p in os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep) if p]
    for d in nvidia_lib_dirs():
        if str(d) not in existing:
            existing.append(str(d))
    os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(existing)
    if have("ldconfig"):  # re-link .so baru supaya langsung ditemukan
        subprocess.run(["ldconfig"], capture_output=True, text=True)
    return len(existing)


def missing_sonames(diag: dict) -> list[str]:
    """Pustaka yang file .so-nya benar-benar tidak ada di mana pun."""
    return [
        lib
        for lib in CUDA_LIBS
        if "cannot open shared object file" in (diag.get("libs") or {}).get(lib, "")
    ]


def force_install_cuda_libs() -> None:
    """Pemasangan ulang paksa untuk kasus wheel CUDA 13 menutupi wheel CUDA 12.

    `pip install` biasa replied "already satisfied" padahal `libcublas.so.12` tidak
    pernah terpasang karena yang ada hanya `libcublas.so.13` (lihat problem.md P-021).
    """
    cmd = [
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
        "--force-reinstall", "--no-deps", "nvidia-cublas-cu12", "nvidia-cuda-runtime-cu12",
    ]
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        warn("pip --force-reinstall gagal:\n  " + "\n  ".join(tail))


def setup_cuda_libs(install: bool = True) -> bool:
    """Pastikan `ctranslate2` bisa memakai GPU. Return True kalau CUDA benar-benar kepakai.

    faster-whisper >= 1.1 dengan ctranslate2 4.x butuh cuBLAS 12 & cuDNN 9. Keduanya
    biasanya sudah terpasang di Colab tapi sering tidak ada di LD_LIBRARY_PATH.

    `install=False` dipakai oleh `--skip-install`: pustakanya boleh dipasang di
    percobaan sebelumnya, jadi cukup periksa + set LD_LIBRARY_PATH tanpa pip
    (lihat problem.md P-020).
    """
    gpu = gpu_name()
    if not gpu:
        log("Tidak ada GPU terdeteksi (nvidia-smi tidak ada) -> CPU, compute int8.")
        return False

    log(f"GPU terdeteksi: {gpu}")
    diag = cuda_diagnostics()
    if cuda_ready(diag):
        log(f"ctranslate2 siap: device_count={diag.get('device_count')}, pustaka CUDA termuat.")
    else:
        log("GPU belum bisa dipakai ctranslate2. Causa yang terdeteksi:")
        log(explain_cuda_failure(diag, gpu))
        if not install:
            warn(
                "--skip-install: pustaka CUDA tidak dipasang (dan tidak boleh dipasang "
                "karena --skip-install). Kalau ini percobaan pertama, jalankan tanpa "
                "--skip-install supaya pustakanya dipasang sekali."
            )
            return False
        log("Memasang pustaka CUDA untuk ctranslate2...")
        if not install_cuda_libs():
            log("Pustaka CUDA tidak terpasang lengkap -> lanjut dengan CPU (int8).")

    n_directions = set_cuda_ld_path()
    log(f"LD_LIBRARY_PATH diset ke {n_directions} folder pustaka NVIDIA")

    diag = cuda_diagnostics()
    if not cuda_ready(diag):
        hilang = missing_sonames(diag)
        if hilang and install:
            # Pustaka .so.12 tidak ada sama sekali: pasang ulang paksa supaya
            # wheel CUDA 13 yang menutupinya tidak mencegah wheel CUDA 12.
            warn(
                "File pustaka berikut tidak ditemukan di folder mana pun: "
                + ", ".join(hilang)
                + "\n  Memasang ulang paksa (--force-reinstall)..."
            )
            force_install_cuda_libs()
            n_directions = set_cuda_ld_path()
            log(f"LD_LIBRARY_PATH diset ke {n_directions} folder pustaka NVIDIA")
            diag = cuda_diagnostics()

    if cuda_ready(diag):
        log(
            "ctranslate2 OK: GPU dipakai (device=cuda, compute=float16) "
            f"- {diag.get('device_count')} GPU terlihat, "
            f"ctranslate2 {diag.get('ctranslate2', '?')}."
        )
        return True

    warn(
        "GPU ada tapi ctranslate2 tetap tidak bisa memakainya -> fallback ke CPU (int8).\n"
        "  Penyebab spesifik setelah memasang pustaka:\n"
        + explain_cuda_failure(diag, gpu)
        + "\n  Transkripsi lebih lambat, tetapi pipeline tetap jalan."
    )
    return False


# ------------------------------------------------------------------ 5. .env

PLACEHOLDERS = {
    "isi_api_key_di_sini", "isi_nama_model_gratis_di_sini", "", "none", "null",
    "changeme", "your_api_key_here", "your_model_here",
}

# Router OpenRouter yang hanya meneruskan ke model gratis (lihat problem.md P-022).
# Salinan dari `FREE_ROUTER_MODELS` di src/config.py supaya runner Colab tetap bisa
# jalan sendiri; `tests/test_model_gratis.py` menjaga keduanya tetap sama.
COLAB_FREE_ROUTERS = frozenset({"openrouter/free"})


def colab_model_is_free(model: str) -> bool:
    """Sufiks ':free' ATAU router gratis (lihat src/config.py::model_is_free)."""
    name = (model or "").strip().lower()
    return ":free" in name or name in COLAB_FREE_ROUTERS

ENV_ORDER = (
    "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL",
    "WHISPER_MODEL", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE",
    "CLIP_MIN_SECONDS", "CLIP_MAX_SECONDS", "MAX_CLIPS", "LANGUAGE", "FACE_TRACKING",
    "MAX_SOURCE_HEIGHT", "DOWNLOAD_PROGRESS_SECONDS", "YT_COOKIES_FILE",
    "YT_PLAYER_CLIENTS", "MERGE_CLIPS",
)

DEFAULTS = {
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "WHISPER_MODEL": "small",
    "WHISPER_DEVICE": "auto",
    "WHISPER_COMPUTE_TYPE": "auto",
    "CLIP_MIN_SECONDS": "30",
    "CLIP_MAX_SECONDS": "60",
    "MAX_CLIPS": "5",
    "LANGUAGE": "id",
    "FACE_TRACKING": "false",
    # Kunci tambahan: harus sama dengan yang dibaca src/config.py, kalau tidak
    # nilainya hilang setiap kali `.env` ditulis ulang (lihat problem.md P-023).
    "MAX_SOURCE_HEIGHT": "1080",
    "DOWNLOAD_PROGRESS_SECONDS": "15",
    "YT_COOKIES_FILE": "",
    "YT_PLAYER_CLIENTS": "",
    "MERGE_CLIPS": "false",
}


def colab_secret(name: str) -> str:
    """Baca variabel shell, lalu Colab Secrets (Settings > Secrets)."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:
        from google.colab import userdata  # type: ignore

        return (userdata.get(name) or "").strip()
    except Exception:
        return ""


def resolve_api_key(existing: str, args: argparse.Namespace) -> str:
    """API key dari: --api-key > .env > env shell > Colab Secrets > prompt tersamar."""
    key = (args.api_key or existing or colab_secret("OPENROUTER_API_KEY")).strip()
    if key and key.lower() not in PLACEHOLDERS:
        log("OPENROUTER_API_KEY: tersedia (tersamar, tidak ditampilkan).")
        return key
    if not args.allow_prompt:
        die(
            "OPENROUTER_API_KEY belum ada.\n"
            "  Tambahkan Colab Secret bernama OPENROUTER_API_KEY, atau jalankan dengan\n"
            "  --api-key ... , atau isi manual .env lalu ulangi."
        )
    log("OPENROUTER_API_KEY belum ada di .env / environment / Colab Secrets.")
    log("  Buat key gratis di https://openrouter.ai/keys, lalu simpan sebagai Colab")
    log("  Secret bernama OPENROUTER_API_KEY supaya tidak perlu mengetik tiap sesi.")
    key = getpass.getpass("  Tempel API key di sini (tidak akan ditampilkan): ").strip()
    if key.lower() in PLACEHOLDERS:
        die("API key yang dimasukkan tidak valid.")
    return key


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.split("#")[0].strip()
    return values


def resolve_env(project: Path, args: argparse.Namespace, gpu: bool) -> Path:
    """Pastikan file .env ada dan valid, lalu kembalikan path-nya."""
    if args.env_file:
        path = Path(args.env_file).expanduser().resolve()
        if not path.is_file():
            die(f"File .env yang diminta tidak ada: {path}")
        log(f"Memakai .env yang diberikan: {path}")
        return path

    path = project / ".env"
    existing = read_env(path)
    if existing:
        log(f".env sudah ada di {path} -> dipakai apa adanya (nilainya tidak diubah).")

    api_key = resolve_api_key(existing.get("OPENROUTER_API_KEY", ""), args)
    model = (args.model or existing.get("OPENROUTER_MODEL", "")).strip()

    if not model:
        die(
            "OPENROUTER_MODEL belum diisi dan tidak ada di .env.\n"
            "  Pilih satu model GRATIS dari https://openrouter.ai/models?max_price=0\n"
            "  lalu jalankan ulang, mis.: --model google/gemini-2.0-flash-exp:free"
        )
    if not colab_model_is_free(model):
        # Aturan sama dengan src/config.py: blokir keras model berbayar
        # (lihat problem.md P-010), router gratis tetap boleh (P-022).
        die(
            f"OPENROUTER_MODEL='{model}' tidak berakhiran ':free'.\n"
            "  Proyek ini hanya mengizinkan model GRATIS. Pilih salah satu:\n"
            f"  - router gratis yang otomatis pilih model free: {', '.join(sorted(COLAB_FREE_ROUTERS))}\n"
            "  - model gratis spesifik dari https://openrouter.ai/models?max_price=0\n"
            "    (mis. --model google/gemini-2.0-flash-exp:free)"
        )

    # .env sudah benar untuk device yang sekarang dipakai -> jangan tulis ulang.
    if (existing.get("OPENROUTER_API_KEY") == api_key
            and existing.get("OPENROUTER_MODEL") == model
            and bool(existing.get("WHISPER_DEVICE"))):
        log(f"OPENROUTER_MODEL: {model} (model gratis, valid)")
        return path

    values = dict(DEFAULTS)
    values.update(existing)
    values["OPENROUTER_API_KEY"] = api_key
    values["OPENROUTER_MODEL"] = model
    if args.whisper_model:
        values["WHISPER_MODEL"] = args.whisper_model
    if args.face_tracking:
        values["FACE_TRACKING"] = "true"
    elif args.no_face_tracking:
        values["FACE_TRACKING"] = "false"

    # GPU di Colab jauh lebih cepat; dipaksa CPU kalau GPU tidak benar-benar bisa dipakai.
    if gpu:
        values["WHISPER_DEVICE"] = "cuda"
        values["WHISPER_COMPUTE_TYPE"] = "float16"
    else:
        values["WHISPER_DEVICE"] = "cpu"
        values["WHISPER_COMPUTE_TYPE"] = "int8"

    text = "# .env untuk AUTO CLIP (dibuat oleh autoclip_colab.py)\n"
    for key in ENV_ORDER:
        text += f"{key}={values.get(key, DEFAULTS.get(key, ''))}\n"
    # Kunci milik pengguna yang tidak dikenal program tetap ditulis, jangan dibuang
    # (lihat problem.md P-023).
    for key in values:
        if key not in ENV_ORDER:
            text += f"{key}={values[key]}\n"
    path.write_text(text, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    log(f"OPENROUTER_MODEL: {model} (model gratis, valid)")
    log(f".env ditulis: device={values['WHISPER_DEVICE']}, "
        f"compute={values['WHISPER_COMPUTE_TYPE']}, whisper={values['WHISPER_MODEL']}")
    return path


# ------------------------------------------------------------------ 6. pipeline

def resolve_input(args: argparse.Namespace) -> str:
    source = (args.input or "").strip()
    if not source:
        die(
            "--input wajib diisi: URL video atau path file.\n"
            "  Contoh: --input \"https://www.youtube.com/watch?v=VIDEO_ID\""
        )
    if source.startswith(("http://", "https://", "www.")):
        return source

    path = Path(source).expanduser()
    if not path.is_file():
        die(
            f"File video tidak ditemukan: {source}\n"
            "  Di Colab, path absolut diawali /content/ atau /content/drive/."
        )
    if in_colab() and not path.is_absolute():
        path = Path("/content") / path
    return str(path)


def run_pipeline(project: Path, env_path: Path, source: str, extra: list[str]) -> int:
    cmd = [sys.executable, str(project / "main.py"), "--input", source, "--env", str(env_path)]
    cmd.extend(extra)
    rule("Menjalankan AUTO CLIP (log lengkap di bawah)")
    return subprocess.run(cmd, cwd=str(project)).returncode


def run_pipeline_robust(
    project: Path, env_path: Path, source: str, extra: list[str], gpu: bool
) -> int:
    """Kalau transkripsi di GPU gagal (kode 4), ulangi sekali di CPU.

    Bentuk fallback yang sama dengan aturan AGENTS.md: gagalkan terus terang, jangan
    diam-diam mengganti secretly setting lain.
    """
    code = run_pipeline(project, env_path, source, extra)
    if code != 4 or not gpu:
        return code

    warn("Langkah transkripsi gagal di GPU (kode 4) -> ulangi sekali di CPU.")
    original = env_path.read_text(encoding="utf-8")
    try:
        env_path.write_text(
            original
            .replace("WHISPER_DEVICE=cuda", "WHISPER_DEVICE=cpu")
            .replace("WHISPER_COMPUTE_TYPE=float16", "WHISPER_COMPUTE_TYPE=int8"),
            encoding="utf-8",
        )
        return run_pipeline(project, env_path, source, extra)
    finally:
        env_path.write_text(original, encoding="utf-8")


# ------------------------------------------------------------------ 7. hasil

RESULT_EXTS = {".mp4", ".srt", ".ass"}


def collect_outputs(output_dir: Path) -> list[Path]:
    if not output_dir.is_dir():
        return []
    return sorted(p for p in output_dir.iterdir() if p.is_file() and p.suffix.lower() in RESULT_EXTS)


def deliver(output_dir: Path, zip_it: bool, drive_dir: str | None) -> None:
    """Salin hasil ke Drive (kalau diminta) lalu zip + unduh ke browser."""
    files = collect_outputs(output_dir)
    if not files:
        warn(f"Tidak ada file hasil di {output_dir}")
        return

    rule("Ringkasan hasil")
    total = 0.0
    for p in files:
        mb = p.stat().st_size / 1_048_576
        total += mb
        log(f"  {p.name}  ({mb:.1f} MB)")
    log(f"Total {len(files)} file, {total:.1f} MB, di {output_dir}")

    if drive_dir:
        dest = Path(drive_dir).expanduser()
        dest.mkdir(parents=True, exist_ok=True)
        for p in files:
            shutil.copy2(p, dest / p.name)
        log(f"{len(files)} file disalin ke {dest}")

    if not zip_it:
        return

    zip_path = output_dir.parent / f"autoclip_output_{time.strftime('%Y%m%d_%H%M%S')}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for p in files:
            zf.write(p, arcname=f"output/{p.name}")
    log(f"Zip hasil: {zip_path} ({zip_path.stat().st_size / 1_048_576:.1f} MB)")

    try:
        from google.colab import files as colab_files  # type: ignore

        colab_files.download(str(zip_path))
        log("Unduhan ke browser dimulai. Tunggu selesai sebelum menutup tab.")
    except ImportError:
        log("Bukan Colab -> ambil file zip secara manual dari path di atas.")
    except Exception as exc:  # noqa: BLE001
        warn(f"Tidak bisa memicu unduhan otomatis ({exc}). Ambil file zip secara manual.")


# ------------------------------------------------------------------ 8. laporan

EXIT_MEANINGS = {
    0: "sukses",
    2: ".env belum lengkap atau model bukan :free",
    3: "ffmpeg/ffprobe tidak ditemukan",
    4: "gagal unduh video atau transkripsi",
    5: "gagal memilih highlight di OpenRouter (dicatat di problem.md)",
    6: "gagal memotong klip / membuat subtitle",
    130: "dibatalkan user",
}


def report(code: int, output_dir: Path, started: float) -> int:
    files = collect_outputs(output_dir)
    rule("Laporan akhir")
    log(f"Kode keluar main.py : {code} ({EXIT_MEANINGS.get(code, 'tidak dikenal')})")
    log(f"Jumlah hasil        : {len(files)} file di {output_dir}")
    log(f"Waktu               : {time.time() - started:.0f} detik")
    if code == 4:
        log("")
        log("Kalau pesan errornya 'Sign in to confirm you're not a bot', itu reputasi IP")
        log("Colab yang sedang diblokir, bukan file rusak. Yang bisa dilakukan:")
        log("  1) pakai file lokal: taruh video di /content/input/ lalu --input input/nama.mp4;")
        log("  2) kirim cookie YouTube: -- --cookies cookies.txt (export pakai extension");
        log("     'Get cookies.txt LOCALLY');")
        log("  3) runtime baru (Execution > Restart runtime) lalu ulangi URL yang sama;")
        log("  4) kalau tetap ditolak, tunggu beberapa jam atau ganti jaringan.")
    if code == 5:
        log("")
        log("Model gratis OpenRouter sering kena rate limit. Cara mengatasi:")
        log("  1) tunggu beberapa menit lalu ulangi dengan -- --reuse-transcript")
        log("     (transkripsi tidak diulang: hemat waktu dan kuota LLM);")
        log("  2) ganti model di .env dengan model :free lain;")
        log("  3) perkecil durasi video (mis. --max-seconds 40).")
    if code == 0 and not files:
        log("")
        warn("Kode 0 tapi output kosong. Periksa --max-seconds vs durasi video.")
    log("")
    log("Catatan Colab: runtime yang berhenti akan menghapus semua file di /content.")
    log("Unduh zip hasil (atau pakai --drive-dir) sebelum menutup tab.")
    return code


# ------------------------------------------------------------------ main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoclip_colab",
        description="Jalankan AUTO CLIP di Google Colab: install, config, pipeline, ambil hasil.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Argumen tambahan untuk main.py ditulis setelah --, "
               "mis. --max-clips 3 --keep-temp --verbose",
    )
    parser.add_argument("--input", "-i", help="URL video atau path file lokal (mis. /content/drive/...)")
    parser.add_argument("--repo", help="URL git repo AUTO CLIP (https://github.com/USER/autoclip.git) "
                                       "untuk di-clone kalau proyek belum ada di disk")
    parser.add_argument("--env-file", help="Pakai file .env tertentu, bukan .env di proyek")
    parser.add_argument("--api-key", help="API key OpenRouter (lebih aman pakai Colab Secrets)")
    parser.add_argument("--model", help="Nama model OpenRouter gratis, wajib berakhiran :free")
    parser.add_argument("--whisper-model", help="Model Whisper: tiny/base/small/medium/large-v3")
    parser.add_argument("--cpu", action="store_true", help="Paksa CPU walau GPU tersedia")
    parser.add_argument("--face-tracking", action="store_true", help="Crop mengikuti wajah")
    parser.add_argument("--no-face-tracking", action="store_true", help="Paksa crop tengah")
    parser.add_argument("--drive-dir", help="Folder Google Drive untuk menyalin hasil, "
                                            "mis. /content/drive/MyDrive/autoclip")
    parser.add_argument("--skip-install", action="store_true", help="Lewati apt-get + pip install")
    parser.add_argument("--no-download", action="store_true", help="Jangan zip/unduh hasil")
    parser.add_argument("--allow-prompt", action="store_true", default=True,
                        help="Boleh bertanya API key di terminal bila secret tidak ada (default)")
    parser.add_argument("--no-prompt", dest="allow_prompt", action="store_false",
                        help="Tanpa interaksi: hanya Colab Secrets / environment / argumen")
    parser.add_argument("--check-env", action="store_true",
                        help="Periksa lingkungan lalu keluar tanpa menjalankan pipeline")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra: list[str] = []
    if "--" in argv:
        cut = argv.index("--")
        argv, extra = argv[:cut], argv[cut + 1:]  # sisanya diteruskan ke main.py apa adanya
    args = build_parser().parse_args(argv)
    started = START_TIME

    rule("AUTO CLIP - runner untuk Google Colab")
    log(f"Python : {sys.version.split()[0]} ({sys.executable})")
    log(f"Colab  : {'ya' if in_colab() else 'tidak (mode lokal)'}")
    log(f"Folder : {Path.cwd()}")
    log(f"main.py : argumen tambahan {extra or '(tidak ada)'}")

    step(1, 5, "Menemukan proyek AUTO CLIP")
    project = locate_project(Path(__file__).resolve().parent, args.repo)
    if project is None:
        project = ensure_repo(args.repo)
    log(f"Proyek : {project}")
    for folder in ("input", "temp", "output"):
        (project / folder).mkdir(parents=True, exist_ok=True)

    step(2, 5, "FFmpeg")
    if args.skip_install:
        log("--skip-install: lewati apt-get.")
        if not (have("ffmpeg") and have("ffprobe")):
            die("FFmpeg tidak ada sedangkan --skip-install aktif.")
    else:
        setup_ffmpeg()

    step(3, 5, "Dependency Python + GPU")
    if args.skip_install:
        log("--skip-install: lewati pip install dependency Python.")
    else:
        setup_python_deps(project)
    # Probe GPU tetap jalan walau --skip-install: pustaka CUDA bisa saja sudah
    # terpasang dari percobaan sebelumnya, dan mengabaikannya akan memaksa CPU
    # tanpa alasan (lihat problem.md P-020).
    gpu = False if args.cpu else setup_cuda_libs(install=not args.skip_install)
    log(f"Mode   : {'GPU (cuda/float16)' if gpu else 'CPU (int8)'}")

    step(4, 5, "Konfigurasi .env (model wajib :free)")
    env_path = resolve_env(project, args, gpu)

    if args.check_env:
        rule("Pemeriksaan lingkungan selesai (--check-env)")
        log(f"Proyek  : {project}")
        log(f".env    : {env_path} (ada: {env_path.is_file()})")
        log(f"FFmpeg  : {have('ffmpeg')} | FFprobe: {have('ffprobe')}")
        gpu = gpu_name()
        diag = cuda_diagnostics()
        log(f"GPU     : {gpu or 'tidak ada'}")
        log(f"CUDA    : siap={cuda_ready(diag)} device_count={diag.get('device_count')}")
        log(f"ctranslate2 : {diag.get('ctranslate2', '?')} | python: {diag.get('python')}")
        for lib, state in (diag.get("libs") or {}).items():
            prefix = f"{lib}: "
            bersih = state[len(prefix):] if state.startswith(prefix) else state
            log(f"  {lib:<20} {bersih}")
        log(f"LD_LIBRARY_PATH : {diag.get('ld_path') or '(kosong)'}")
        if not cuda_ready(diag) and gpu:
            log("")
            log("Penyebab GPU tidak dipakai:")
            log(explain_cuda_failure(diag, gpu))
        log(f".env device      : {read_env(env_path).get('WHISPER_DEVICE', '(kosong)')}")
        return 0

    step(5, 5, "Pipeline")
    source = resolve_input(args)
    log(f"Sumber : {source}")
    code = run_pipeline_robust(project, env_path, source, extra, gpu)

    deliver(project / "output", zip_it=not args.no_download, drive_dir=args.drive_dir)
    return report(code, project / "output", started)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[colab] DIBATIKAN user")
        sys.exit(130)