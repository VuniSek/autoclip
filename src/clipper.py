"""Potong segmen dengan FFmpeg dan ubah ke 9:16 (1080x1920).

Default: crop tengah. Jika FACE_TRACKING=true, lacak wajah sepanjang segmen
(lintasan bergerak) lalu gerakkan jendela crop mengikuti wajah; bila wajah
tidak terdeteksi -> fallback ke crop tengah.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import TEMP_DIR
from .face_track import (
    DEFAULT_DETECT_WIDTH,
    DEFAULT_SAMPLE_FPS,
    DEFAULT_SMOOTH_WINDOW,
    FaceDetector,
    crop_positions,
    smooth_track,
    track_faces,
    write_sendcmd,
)

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
    """Cari file Haar cascade (dipakai kalau model YuNet tidak tersedia)."""
    from .face_track import HAAR_CASCADE_NAME, find_model_file

    return find_model_file(HAAR_CASCADE_NAME, allow_env=False)


def _face_x_center(video: Path, start: float, duration: float) -> float | None:
    """Posisi horizontal pusat wajah (0..1) di dalam segmen. None bila tidak ketemu.

    Ini cuma **posisi diam** (median lintasan). Untuk crop yang benar-benar
    bergerak mengikuti wajah, pakai :func:`plan_face_crop`.
    """
    detector = FaceDetector()
    if detector.backend == "none":
        print(
            "[clipper] tidak ada model deteksi wajah "
            "(taruh assets/face_detection_yunet_2023mar.onnx atau Haar cascade); "
            "face tracking dilewati."
        )
        return None

    track = track_faces(video, start, duration, detector, sample_fps=DEFAULT_SAMPLE_FPS)
    xs = [x for x in track.xs if x is not None]
    if not xs:
        return None
    try:
        sw, _sh = get_video_size(Path(video))
    except ClipError:
        return None
    if sw <= 0:
        return None
    return float(sorted(xs)[len(xs) // 2]) / float(sw)


def _escape_filter_path(path: Path) -> str:
    """Escape path untuk dipakai di dalam string filter FFmpeg."""
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


@dataclass
class FaceCrop:
    """Rencana crop yang mengikuti wajah (jendela crop bergerak)."""

    filter_str: str
    commands_file: Path | None = None
    samples: int = 0
    detected: int = 0
    backend: str = "none"

    def cleanup(self) -> None:
        """Hapus file perintah sementara (dipanggil setelah render)."""
        if self.commands_file and self.commands_file.exists():
            try:
                self.commands_file.unlink()
            except OSError:
                pass


def plan_face_crop(
    video: Path,
    start: float,
    duration: float,
    sw: int,
    sh: int,
    out_w: int = TARGET_W,
    out_h: int = TARGET_H,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    smooth_window: int = DEFAULT_SMOOTH_WINDOW,
    detect_width: int = DEFAULT_DETECT_WIDTH,
    commands_dir: Path | None = None,
) -> FaceCrop | None:
    """Rencana crop yang mengikuti wajah, atau None bila wajah tidak terdeteksi.

    Lintasan wajah dihitung dulu (deteksi -> pilih yang konsisten -> haluskan),
    lalu dijadikan perintah ``sendcmd`` untuk filter ``crop`` FFmpeg supaya
    jendela crop bergerak mengikuti wajah, bukan diam di satu tempat.
    """
    detector = FaceDetector(detect_width=detect_width)
    if detector.backend == "none":
        print(
            "[clipper] tidak ada model deteksi wajah "
            "(opsional: taruh assets/face_detection_yunet_2023mar.onnx); "
            "fallback ke crop tengah."
        )
        return None

    track = track_faces(video, start, duration, detector, sample_fps=sample_fps)
    if track.detected == 0:
        print("[clipper] wajah tidak terdeteksi; fallback ke crop tengah.")
        return None

    xs, ys = smooth_track(track, window=smooth_window)
    axis, positions, scaled_w, scaled_h = crop_positions(
        track, xs, ys, sw, sh, out_w, out_h
    )
    if not positions:
        print("[clipper] lintasan wajah kosong; fallback ke crop tengah.")
        return None

    cmd_dir = Path(commands_dir) if commands_dir else TEMP_DIR
    cmd_dir.mkdir(parents=True, exist_ok=True)
    cmd_path = cmd_dir / (
        f"facecmd_{int(round(start * 1000))}_{int(round(duration * 1000))}.cmd"
    )
    # Deadband: gerakan crop di bawah ~0,4% lebar frame hasil tidak terlihat,
    # tapi bikin encoder menghasilkan file jauh lebih besar (goyang 1-2 piksel
    # memaksa blok baru terus-menerus).
    deadband = max(2.0, out_w * 0.004)
    write_sendcmd(cmd_path, axis, positions, deadband=deadband)

    first = int(round(positions[0][1]))
    if axis == "x":
        vf = f"scale={scaled_w}:{scaled_h},crop={out_w}:{out_h}:x={first}:y=0,setsar=1"
    else:
        vf = f"scale={scaled_w}:{scaled_h},crop={out_w}:{out_h}:x=0:y={first},setsar=1"
    filter_str = f"sendcmd=f='{_escape_filter_path(cmd_path)}',{vf}"
    return FaceCrop(
        filter_str=filter_str,
        commands_file=cmd_path,
        samples=track.total,
        detected=track.detected,
        backend=detector.backend,
    )


def face_crop_filter(video: Path, start: float, duration: float,
                     sw: int, sh: int, out_w: int = TARGET_W, out_h: int = TARGET_H) -> str | None:
    """Filter crop STATIS yang mengikuti wajah, atau None bila tidak terdeteksi.

    Untuk crop yang bergerak mengikuti wajah, pakai :func:`plan_face_crop`.
    """
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
    face_sample_fps: float = DEFAULT_SAMPLE_FPS,
    face_smooth: int = DEFAULT_SMOOTH_WINDOW,
    face_detect_width: int = DEFAULT_DETECT_WIDTH,
) -> Path:
    """Potong [start,end] dari video, ubah ke 9:16, simpan ke out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sw, sh = get_video_size(video)

    duration = max(0.5, end - start)
    vf = None
    used_face = False
    face: FaceCrop | None = None
    if face_tracking:
        face = plan_face_crop(
            video,
            start,
            duration,
            sw,
            sh,
            sample_fps=face_sample_fps,
            smooth_window=face_smooth,
            detect_width=face_detect_width,
        )
        if face is not None:
            vf = face.filter_str
            used_face = True
            print(
                f"[clipper] face tracking: {face.detected}/{face.samples} sampel wajah "
                f"terdeteksi (detektor {face.backend}); crop bergerak mengikuti wajah."
            )
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
    except ClipError as exc:
        if used_face:
            # Fallback: crop tengah (sesuai aturan di AGENTS.md)
            print("[clipper] face tracking gagal saat render, fallback ke crop tengah.")
            print(f"[clipper] alasan: {str(exc).splitlines()[0]}")
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
    finally:
        if face is not None:
            face.cleanup()

    if not out_path.exists() or out_path.stat().st_size == 0:
        raise ClipError(f"Klip kosong: {out_path}")
    return out_path


def make_silent_clip(video: Path, start: float, end: float, out_path: Path,
                     face_tracking: bool = False) -> Path:
    """Potong tanpa subtitle (dipakai bila subtitle terpisah)."""
    return cut_clip(video, start, end, out_path, face_tracking=face_tracking, burn_subtitle=None)