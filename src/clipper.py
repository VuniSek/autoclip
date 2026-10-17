"""Potong segmen dengan FFmpeg dan ubah ke 9:16 (1080x1920).

Default: crop tengah. Jika FACE_TRACKING=true, coba MediaPipe FaceDetector
untuk mengikuti wajah; bila gagal -> fallback ke crop tengah.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

TARGET_W = 1080
TARGET_H = 1920


class ClipError(RuntimeError):
    pass


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-25:])
        raise ClipError(f"FFmpeg gagal ({proc.returncode}):\n{tail}")
    return proc


def get_video_size(video: Path) -> tuple[int, int]:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            str(video),
        ],
        capture_output=True, text=True,
    )
    data = json.loads(proc.stdout or "{}")
    try:
        st = data["streams"][0]
        return int(st["width"]), int(st["height"])
    except (KeyError, IndexError, ValueError) as exc:
        raise ClipError(f"Tidak bisa membaca ukuran video {video}") from exc


def center_crop_filter(sw: int, sh: int, out_w: int = TARGET_W, out_h: int = TARGET_H) -> str:
    """Filter crop tengah ke rasio 9:16.

    Strategi: scale sampai salah satu sisi pas ke target, lalu crop sisi
    lainnya di tengah. Kalau sumber sudah 9:16, cukup pad.
    """
    src_ratio = sw / sh
    dst_ratio = out_w / out_h
    if abs(src_ratio - dst_ratio) < 1e-3:
        return (
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    if src_ratio > dst_ratio:
        # Landscape: set tinggi = 1920, crop lebar 1080 di tengah
        scaled_w = int(round(out_h * src_ratio))
        scaled_w += scaled_w % 2  # genap
        x = max(0, (scaled_w - out_w) // 2)
        return f"scale={scaled_w}:{out_h},crop={out_w}:{out_h}:{x}:0,setsar=1"
    # Portrait/square: set lebar = 1080, crop tinggi 1920 di tengah
    scaled_h = int(round(out_w / src_ratio))
    scaled_h += scaled_h % 2
    y = max(0, (scaled_h - out_h) // 2)
    return f"scale={out_w}:{scaled_h},crop={out_w}:{out_h}:0:{y},setsar=1"


def _cascade_path() -> Path | None:
    """Cari file Haar cascade: dulu paket cv2, lalu folder assets/ proyek."""
    candidates: list[Path] = []
    try:
        import cv2

        base = Path(cv2.data.haarcascades)
        candidates.append(base / "haarcascade_frontalface_default.xml")
    except Exception:
        pass
    candidates.append(
        Path(__file__).resolve().parent.parent
        / "assets"
        / "haarcascade_frontalface_default.xml"
    )
    for c in candidates:
        if c.exists():
            return c
    return None


def _face_x_center(video: Path, start: float, duration: float) -> float | None:
    """Posisi horizontal pusat wajah (0..1) di dalam segmen. None bila tidak ketemu.

    Meng pakai Haar cascade dari OpenCV. Alasannya: mediapipe >= 1.0 menghapus
    modul ``mediapipe.solutions`` (Lihat problem.md P-006), sedangkan Haar
    cascade sudah ikut paket opencv dan tidak butuh unduhan model tambahan.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("[clipper] opencv tidak terpasang; face tracking dilewati.")
        return None

    cascade_file = _cascade_path()
    if cascade_file is None:
        print(
            "[clipper] Haar cascade tidak ditemukan "
            "(opsional: taruh assets/haarcascade_frontalface_default.xml)."
        )
        return None

    cascade = cv2.CascadeClassifier(str(cascade_file))
    if cascade.empty():
        print(f"[clipper] Haar cascade gagal dimuat: {cascade_file}")
        return None

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f"[clipper] video tidak bisa dibuka untuk deteksi wajah: {video}")
        return None
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        n_samples = 7
        step = max(1, int(fps * max(duration, 0.1) / n_samples))
        start_frame = int(start * fps)
        end_frame = start_frame + int(duration * fps) if duration else total
        xs: list[float] = []
        idx = start_frame
        while idx < end_frame and (total == 0 or idx < total):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
            )
            width = frame.shape[1] or 1
            for (x, y, w, h) in faces:
                xs.append(float((x + w / 2.0) / width))
            idx += step
        if not xs:
            return None
        return float(np.median(xs))  # median tahan noise
    except Exception as exc:  # noqa: BLE001
        # jangan ditelan diam-diam: beri tahu, lalu pakai crop tengah
        print(f"[clipper] deteksi wajah gagal ({exc}); fallback ke crop tengah.")
        return None
    finally:
        cap.release()


def face_crop_filter(video: Path, start: float, duration: float,
                     sw: int, sh: int, out_w: int = TARGET_W, out_h: int = TARGET_H) -> str | None:
    """Filter crop yang mengikuti wajah, atau None bila wajah tidak terdeteksi."""
    center = _face_x_center(video, start, duration)
    if center is None:
        return None
    src_ratio = sw / sh
    if src_ratio > out_w / out_h:
        # Landscape: scale tinggi, geser jendela crop mengikuti wajah
        scaled_w = int(round(out_h * src_ratio))
        scaled_w += scaled_w % 2
        x = int(round(center * scaled_w - out_w / 2))
        x = max(0, min(scaled_w - out_w, x))
        return f"scale={scaled_w}:{out_h},crop={out_w}:{out_h}:{x}:0,setsar=1"
    # Portrait: crop atas-bawah; wajah umumnya di bagian atas -> jaga offset kecil
    scaled_h = int(round(out_w / src_ratio))
    scaled_h += scaled_h % 2
    y = max(0, min(scaled_h - out_h, int(scaled_h * 0.08)))
    return f"scale={out_w}:{scaled_h},crop={out_w}:{out_h}:0:{y},setsar=1"


def cut_clip(
    video: Path,
    start: float,
    end: float,
    out_path: Path,
    face_tracking: bool = False,
    burn_subtitle: Path | None = None,
) -> Path:
    """Potong [start,end] dari video, ubah ke 9:16, simpan ke out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sw, sh = get_video_size(video)

    duration = max(0.5, end - start)
    vf = None
    used_face = False
    if face_tracking:
        vf = face_crop_filter(video, start, duration, sw, sh)
        if vf:
            used_face = True
    if vf is None:
        vf = center_crop_filter(sw, sh)

    filters = [vf]
    if burn_subtitle is not None:
        sub_path = str(burn_subtitle).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        filters.append(f"ass='{sub_path}'")
    vfilter = ",".join(filters)

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(video),
        "-vf", vfilter,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    try:
        _run(cmd)
    except ClipError:
        if used_face:
            # Fallback: crop tengah (sesuai aturan di AGENTS.md)
            print("[clipper] face tracking gagal saat render, fallback ke crop tengah.")
            vf_center = center_crop_filter(sw, sh)
            filters = [vf_center]
            if burn_subtitle is not None:
                sub_path = str(burn_subtitle).replace("\\", "/").replace(":", r"\:")
                filters.append(f"ass='{sub_path}'")
            cmd2 = list(cmd)
            cmd2[cmd2.index("-vf") + 1] = ",".join(filters)
            _run(cmd2)
        else:
            raise

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise ClipError(f"Klip kosong: {out_path}")
    return out_path


def make_silent_clip(video: Path, start: float, end: float, out_path: Path,
                     face_tracking: bool = False) -> Path:
    """Potong tanpa subtitle (dipakai bila subtitle terpisah)."""
    return cut_clip(video, start, end, out_path, face_tracking=face_tracking, burn_subtitle=None)