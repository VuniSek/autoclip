"""Unduh video dari URL (yt-dlp) atau pakai file lokal, plus ekstraksi audio."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .config import INPUT_DIR, TEMP_DIR

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".ts"}
URL_RE = re.compile(r"^(https?://|www\.)", re.IGNORECASE)


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


def download(source: str, workdir: Path | None = None) -> tuple[Path, dict]:
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
    opts = {
        "format": "bv*+ba/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 3,
        # Jangan kirim cookies/browser
        "cookiefile": None,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)
        if info is None:
            raise DownloadError(f"yt-dlp tidak mengembalikan info untuk {source}")
        path = Path(ydl.prepare_filename(info))

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