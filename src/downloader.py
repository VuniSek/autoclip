"""Unduh video dari URL (yt-dlp) atau pakai file lokal, plus ekstraksi audio."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from .config import INPUT_DIR, TEMP_DIR

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".ts"}
URL_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)

# Batas atas frekuensi baris progress unduhan.
# Sadari bahwa baris dicetak kalau salah satu terpenuhi: >= PROGRESS_INTERVAL detik
# sejak baris terakhir, ATAU persentase naik >= PROGRESS_STEP poin. Yang kedua ini
# menjaga unduhan kecil tetap terlihat bergerak tanpa menunggu interval penuh,
# sedangkan yang pertama menjaga file besar tidak membanjiri output (P-014).
PROGRESS_INTERVAL = 15.0
PROGRESS_STEP = 10.0


class DownloadError(RuntimeError):
    pass


def is_url(source: str) -> bool:
    return bool(URL_RE.match(source.strip()))


def _run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-25:])
        raise DownloadError(f"Perintah gagal ({proc.returncode}): {cmd[0]}\n{tail}")
    return proc


def probe_duration(video: Path) -> float:
    """Durasi video dalam detik via ffprobe."""
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video),
        ]
    )
    data = json.loads(proc.stdout or "{}")
    try:
        return float(data["format"]["duration"])
    except (KeyError, ValueError, TypeError) as exc:
        raise DownloadError(f"Tidak bisa membaca durasi dari {video}") from exc


def _human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024 or unit == "GB":
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} GB"


def make_progress_hook(every: float = PROGRESS_INTERVAL, step: float = PROGRESS_STEP):
    """Hook progress yt-dlp -> cetak persentase/kecepatan/ETA ke stdout.

    Wajib karena opts memakai `noprogress=True`; tanpa hook ini proses unduhan
    terlihat menggantung sama sekali di Colab (lihat problem.md P-013).

    `every` = jarak waktu minimal antar baris (detik), `step` = kenaikan persen
    minimal yang tetap memaksa cetak. Salah satu saja terpenuhi -> baris dicetak,
    supaya baris pertama dan yang terakhir selalu muncul namun file besar tidak
    menghasilkan puluhan baris per menit (lihat problem.md P-014).
    `every <= 0` mematikan gate waktu, jadi hanya kenaikan persentase yang dicetak.
    """
    last = {"t": 0.0, "first": True, "pct": -1.0}

    def hook(d: dict) -> None:
        status = d.get("status")
        now = time.monotonic()
        if status == "downloading":
            got = float(d.get("downloaded_bytes") or 0)
            total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
            speed = float(d.get("speed") or 0)
            eta = d.get("eta")
            pct_value = (min(100.0, got / total * 100) if total > 0 else None)
            due_time = last["first"] or (every > 0 and now - last["t"] >= every)
            due_step = pct_value is not None and pct_value - last["pct"] >= step
            if not (due_time or due_step):
                return
            last["first"] = False
            last["t"] = now
            if pct_value is not None:
                last["pct"] = pct_value
                pct = f"{pct_value:5.1f}%"
                size = f"{_human_size(got)}/{_human_size(total)}"
            else:
                pct = "   ?  "
                size = f"{_human_size(got)}/-"
            speed_txt = f"{_human_size(speed)}/s" if speed else "   ?/s"
            eta_txt = f"{int(eta)}s" if eta is not None else "  ?s"
            print(
                f"  [unduh] {pct}  {size}  {speed_txt}  ETA {eta_txt}",
                flush=True,
            )
        elif status == "finished":
            filename = d.get("filename") or ""
            try:
                size_txt = _human_size(Path(filename).stat().st_size)
            except OSError:
                size_txt = "tidak diketahui"
            info = d.get("info_dict") or {}
            res = ""
            if info.get("width") and info.get("height"):
                res = f", {info['width']}x{info['height']}"
            print(f"  [unduh] selesai: {Path(filename).name} ({size_txt}{res})", flush=True)

    return hook


def build_format(max_height: int | None = None) -> str:
    """Pilih format dengan batas tinggi agar unduhan tidak rechazar file 4K raksasa.

    Tanpa batas, `best` bisa memilih video 4K ( hundreds MB ) padahal hasil akhir
    hanya 1080x1920 - unduhan jadi sangat lama tanpa ada yang kelihatan bergerak
    (lihat problem.md P-013).
    """
    if not max_height or max_height <= 0:
        return "bv*+ba/best"
    h = int(max_height)
    return f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/best"


def download(
    source: str,
    workdir: Path | None = None,
    max_height: int | None = None,
    progress_seconds: float | None = None,
) -> tuple[Path, dict]:
    """Siapkan video sumber.

    Returns (path_video, metadata) dengan metadata berisi 'duration' dan 'source'.
    """
    workdir = Path(workdir or TEMP_DIR)
    workdir.mkdir(parents=True, exist_ok=True)

    if not is_url(source):
        local = Path(source).expanduser()
        if not local.exists():
            # Coba cari di folder input/
            candidate = INPUT_DIR / local.name
            if candidate.exists():
                local = candidate
            else:
                raise DownloadError(
                    f"File lokal tidak ditemukan: {source}\n"
                    f"Taruh file ke folder input/ atau berikan path absolut."
                )
        return local.resolve(), {
            "source": str(local.resolve()),
            "duration": probe_duration(local),
            "is_url": False,
        }

    # --- URL: pakai yt-dlp ---
    try:
        import yt_dlp
    except ImportError as exc:
        raise DownloadError(
            "yt-dlp belum terpasang. Jalankan: pip install yt-dlp"
        ) from exc

    outtmpl = str(workdir / "source.%(ext)s")
    fmt = build_format(max_height)
    every = PROGRESS_INTERVAL if progress_seconds is None else float(progress_seconds)
    opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        # Progress dicetak sendiri lewat hook di bawah supaya formatnya konsisten.
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [make_progress_hook(every=every)],
        "retries": 3,
        "fragment_retries": 5,
        # Jangan menggantung diam-diam: koneksi yang macet harus gagal dengan pesan.
        "socket_timeout": 30,
        # Jangan kirim cookies/browser
        "cookiefile": None,
    }
    print(f"  [unduh] mulai: {source}", flush=True)
    print(f"  [unduh] format: {fmt}", flush=True)
    print(
        f"  [unduh] progress: max 1 baris tiap {every:g} detik "
        "(atau tiap 10% kalau lebih cepat)",
        flush=True,
    )
    print(
        "  [unduh] kalau lama tidak bergerak, cek ukuran file .part di folder temp/; "
        "tekan Ctrl+C untuk membatalkan",
        flush=True,
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source, download=True)
            if info is None:
                raise DownloadError(f"yt-dlp tidak mengembalikan info untuk {source}")
            path = Path(ydl.prepare_filename(info))
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(
            f"Gagal mengunduh video dari URL ini: {exc}\n"
            "  Penyebab yang sering: video privat/terhapus, age restriction, atau\n"
            "  YouTube memblokir IP Colab. Coba: pakai file lokal, atau perbarui\n"
            "  yt-dlp: !pip install -U yt-dlp"
        ) from exc

    if not path.exists():
        candidates = sorted(workdir.glob("source.*"))
        if not candidates:
            raise DownloadError(f"File hasil unduhan tidak ditemukan di {workdir}")
        path = candidates[0]

    duration = float(info.get("duration") or 0) or probe_duration(path)
    meta = {
        "source": source,
        "title": info.get("title") or "video",
        "duration": duration,
        "is_url": True,
        "uploader": info.get("uploader"),
    }
    return path.resolve(), meta


def extract_audio(video: Path, audio_path: Path | None = None) -> Path:
    """Ekstrak audio mono 16 kHz ke WAV (format yang disukai Whisper)."""
    audio_path = Path(audio_path or TEMP_DIR / "audio.wav")
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    if audio_path.exists():
        audio_path.unlink()
    _run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(audio_path),
        ]
    )
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise DownloadError(f"Ekstraksi audio gagal, file kosong: {audio_path}")
    return audio_path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None