"""Gabungkan beberapa klip jadi satu video vertikal.

Dipakai kalau pengguna mengaktifkan `--merge` / `MERGE_CLIPS=true`: semua klip
yang sudah jadi (lengkap dengan subtitle yang tertanam) disusun berurutan
menjadi satu file, misalnya `00_judulvideo_gabungan.mp4`.

Cara kerja:
  - daftar file ditulis untuk demuxer `concat` FFmpeg,
  - video di-encode ulang (libx264 + aac) supaya audio tetap sinkron dan
    transisi antar klip mulus (stream copy dari demuxer concat bisa membuat
    audio terpotong),
  - resolusi dikunci 1080x1920 dan fps dinormalkan,
  - hasil diverifikasi dengan ffprobe: harus ada stream video DAN audio.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .clipper import TARGET_H, TARGET_W

# Codec & parameter encode ulang.
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "160k"
CRF = "20"
PRESET = "veryfast"
FPS = 30


class MergeError(RuntimeError):
    """Gagal menggabungkan klip."""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-15:])
        raise MergeError(f"Perintah gagal ({proc.returncode}): {cmd[0]}\n{tail}")
    return proc


def probe_streams(path: Path) -> dict:
    """Info stream video/audio dari ffprobe."""
    proc = _run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height,duration",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ]
    )
    import json

    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    return {
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "width": next((s.get("width") for s in streams if s.get("codec_type") == "video"), None),
        "height": next((s.get("height") for s in streams if s.get("codec_type") == "video"), None),
        "duration": float((data.get("format") or {}).get("duration") or 0),
    }


def merge_clips(
    clips: list[Path],
    out_path: Path,
    target_w: int = TARGET_W,
    target_h: int = TARGET_H,
) -> Path:
    """Gabungkan `clips` (berurutan) jadi satu file di `out_path`.

    Raises:
        MergeError: kalau klip kurang dari 2, file tidak ada, atau FFmpeg/ffprobe
            gagal. Klip asli TIDAK pernah dihapus.
    """
    klip = [Path(c) for c in clips]
    if len(klip) < 2:
        raise MergeError(
            f"Penggabungan butuh minimal 2 klip, baru ada {len(klip)}.\n"
            "  Klip individual tetap ada di folder output/."
        )
    hilang = [str(c) for c in klip if not c.is_file()]
    if hilang:
        raise MergeError(
            "File klip tidak ditemukan: " + ", ".join(hilang)
            + "\n  Klip individual yang ada tetap dipertahankan."
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.parent / f".{out_path.stem}_concat.txt"
    try:
        # Demuxer concat butuh path absolut & escape tanda kutip.
        list_file.write_text(
            "".join(f"file '{c.resolve().as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n" for c in klip),
            encoding="utf-8",
        )
        vfilter = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={FPS},format=yuv420p"
        )
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-vf", vfilter,
            "-c:v", VIDEO_CODEC,
            "-preset", PRESET,
            "-crf", str(CRF),
            "-c:a", AUDIO_CODEC,
            "-b:a", AUDIO_BITRATE,
            "-ar", "48000",
            "-movflags", "+faststart",
            str(out_path),
        ]
        _run(cmd)
    finally:
        try:
            list_file.unlink()
        except OSError:
            pass

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise MergeError(
            f"File gabungan tidak terbentuk: {out_path}\n"
            "  Klip individual tetap ada di folder output/."
        )

    info = probe_streams(out_path)
    if not info["has_video"]:
        raise MergeError(
            f"File gabungan tidak punya stream video: {out_path}\n"
            "  Klip individual tetap ada di folder output/."
        )
    if not info["has_audio"]:
        raise MergeError(
            f"File gabungan tidak punya stream audio: {out_path}\n"
            "  Klip individual tetap ada di folder output/."
        )
    return out_path
