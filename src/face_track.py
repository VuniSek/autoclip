"""Pelacakan wajah (face tracking) untuk crop vertikal 9:16.

Alur kerja modul ini:

1. **Deteksi** wajah pada sampel waktu yang tetap (bukan per frame, supaya
   murah). Detektor utama adalah YuNet (DNN, model ONNX di ``assets/``);
   Haar cascade OpenCV dipakai sebagai cadangan kalau modelnya tidak ada.
2. **Pemilihan** wajah yang konsisten antar waktu: wajah terbesar yang masih
   dekat dengan posisi sebelumnya, supaya tidak berganti orang saat ada dua
   wajah di frame.
3. **Perataan lintasan**: celah diisi (interpolasi), outlier dibuang dengan
   filter median, lalu dirata-rata. Hasilnya mulus, tidak "goyang".
4. **Crop bergerak**: lintasan diubah menjadi perintah ``sendcmd`` untuk
   filter ``crop`` FFmpeg, sehingga jendela crop benar-benar bergerak mengikuti
   wajah (bukan satu posisi diam seperti implementasi lama).

Semua koordinat yang keluar dari modul ini ada di **piksel video sumber**;
pembagian ke ruang koordinat hasil ``scale`` dilakukan di
:func:`crop_positions`.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"

YUNET_MODEL_NAME = "face_detection_yunet_2023mar.onnx"
HAAR_CASCADE_NAME = "haarcascade_frontalface_default.xml"

#: Batas bawah skor YuNet (semakin tinggi = lebih konservatif).
DEFAULT_SCORE_THRESHOLD = 0.6
#: Batas atas rasio ukuran wajah minimal terhadap lebar frame.
DEFAULT_MIN_FACE_RATIO = 0.03
#: Lebar frame (piksel) yang dipakai untuk deteksi. Frame lebih besar dikecilkan
#: supaya deteksi tetap cepat; koordinat dikembalikan ke skala asli.
DEFAULT_DETECT_WIDTH = 640
#: Kerapatan sampling deteksi (detik per sampel).
DEFAULT_SAMPLE_FPS = 10.0
#: Jendela perataan lintasan (sampel). Nilai ganjil.
DEFAULT_SMOOTH_WINDOW = 5


def _cv2():
    """Import cv2 secara lazy; None kalau tidak terpasang."""
    try:
        import cv2  # noqa: PLC0415

        return cv2
    except Exception:  # noqa: BLE001
        return None


@dataclass(frozen=True)
class FaceBox:
    """Kotak wajah di koordinat piksel video sumber."""

    x: float
    y: float
    w: float
    h: float
    score: float = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2.0

    @property
    def cy(self) -> float:
        return self.y + self.h / 2.0

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass
class FaceTrack:
    """Hasil pelacakan: satu entri per sampel waktu."""

    duration: float = 0.0
    sample_fps: float = DEFAULT_SAMPLE_FPS
    times: list[float] = field(default_factory=list)
    xs: list[float | None] = field(default_factory=list)
    ys: list[float | None] = field(default_factory=list)
    sizes: list[float] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)

    @property
    def detected(self) -> int:
        return sum(1 for v in self.xs if v is not None)

    @property
    def total(self) -> int:
        return len(self.times)


def find_model_file(name: str, allow_env: bool = True) -> Path | None:
    """Cari file model/cascade.

    Urutan: env (``FACE_MODEL_FILE``, hanya untuk model YuNet) -> ``assets/``
    -> paket cv2. Kalau env menunjuk file yang tidak ada, searching
    diabaikan supaya salah ketik tidak diam-diam mengganti model.
    """
    if allow_env:
        override = (os.getenv("FACE_MODEL_FILE") or "").strip()
        if override:
            candidate = Path(override).expanduser()
            return candidate if candidate.is_file() else None
    local = ASSETS_DIR / name
    if local.is_file():
        return local
    cv2 = _cv2()
    if cv2 is not None:
        try:
            packaged = Path(cv2.data.haarcascades) / name
            if packaged.is_file():
                return packaged
        except Exception:  # noqa: BLE001
            pass
    return None


class FaceDetector:
    """Deteksi wajah: YuNet (DNN) kalau modelnya ada, Haar cascade cadangan."""

    def __init__(
        self,
        detect_width: int = DEFAULT_DETECT_WIDTH,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        nms_threshold: float = 0.3,
        min_face_ratio: float = DEFAULT_MIN_FACE_RATIO,
    ) -> None:
        self.detect_width = max(160, int(detect_width))
        self.score_threshold = float(score_threshold)
        self.nms_threshold = float(nms_threshold)
        self.min_face_ratio = float(min_face_ratio)
        self.backend = "none"
        self._yunet = None
        self._cascade = None
        self._input_size: tuple[int, int] | None = None

        cv2 = _cv2()
        if cv2 is None:
            return

        model = find_model_file(YUNET_MODEL_NAME)
        if model is not None:
            try:
                self._yunet = cv2.FaceDetectorYN.create(
                    str(model),
                    "",
                    (320, 320),
                    self.score_threshold,
                    self.nms_threshold,
                    5000,
                )
                self.backend = "yunet"
                return
            except Exception as exc:  # noqa: BLE001
                print(f"[face] model YuNet gagal dimuat ({exc}); pakai Haar cascade.")

        cascade_file = find_model_file(HAAR_CASCADE_NAME, allow_env=False)
        if cascade_file is not None:
            try:
                cascade = cv2.CascadeClassifier(str(cascade_file))
                if not cascade.empty():
                    self._cascade = cascade
                    self.backend = "haar"
            except Exception as exc:  # noqa: BLE001
                print(f"[face] Haar cascade gagal dimuat ({exc}).")

    # -- deteksi -----------------------------------------------------------
    def detect(self, frame) -> list[FaceBox]:
        """Deteksi wajah pada satu frame BGR. Kembalikan kotak di skala asli."""
        cv2 = _cv2()
        if cv2 is None or frame is None:
            return []
        height, width = frame.shape[:2]
        if width <= 0 or height <= 0:
            return []

        scale = 1.0
        if self.detect_width and width > self.detect_width:
            scale = self.detect_width / float(width)
        if scale < 1.0:
            small = cv2.resize(
                frame,
                (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
                interpolation=cv2.INTER_AREA,
            )
        else:
            small = frame

        boxes = self._detect_small(cv2, small)
        out: list[FaceBox] = []
        for box in boxes:
            restored = FaceBox(
                box.x / scale, box.y / scale, box.w / scale, box.h / scale, box.score
            )
            if restored.w < self.min_face_ratio * width:
                continue  # terlalu kecil -> kemungkinan false positive
            out.append(restored)
        return out

    def _detect_small(self, cv2, small) -> list[FaceBox]:
        if self._yunet is not None:
            height, width = small.shape[:2]
            if self._input_size != (width, height):
                self._yunet.setInputSize((width, height))
                self._input_size = (width, height)
            ok, faces = self._yunet.detect(small)
            if not ok or faces is None:
                return []
            return [
                FaceBox(
                    float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
                )
                for f in faces
            ]
        if self._cascade is not None:
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            min_side = max(20, int(self.min_face_ratio * small.shape[1]))
            found = self._cascade.detectMultiScale(
                gray, 1.1, 5, minSize=(min_side, min_side)
            )
            return [FaceBox(float(x), float(y), float(w), float(h), 0.0) for x, y, w, h in found]
        return []


def _pick_face(
    faces: list[FaceBox],
    last_cx: float | None,
    last_size: float,
    frame_width: int,
    max_jump_ratio: float,
) -> FaceBox | None:
    """Pilih wajah yang konsisten dengan track sebelumnya.

    Kalau ada beberapa wajah, ambil yang **terbesar** di antara yang masih
    dekat dengan posisi terakhir — supaya tidak berganti orang. Kalau tidak ada
    yang dekat (wajah pindah cepat / detector sempat gagal), ambil yang
    terbesar saja supaya track bisa nyambung lagi.
    """
    if not faces:
        return None
    if last_cx is None:
        return max(faces, key=lambda f: f.area)

    max_jump = max(frame_width * max_jump_ratio, 3.0 * last_size)
    near = [f for f in faces if abs(f.cx - last_cx) <= max_jump]
    pool = near if near else faces
    return max(pool, key=lambda f: f.area)


def track_faces(
    video: Path | str,
    start: float,
    duration: float,
    detector: FaceDetector,
    sample_fps: float = DEFAULT_SAMPLE_FPS,
    max_jump_ratio: float = 0.25,
) -> FaceTrack:
    """Deteksi wajah pada sampel waktu tetap di dalam segmen ``[start, start+duration]``.

    Frame dibaca berurutan (seek satu kali di awal, lalu ``grab`` untuk melompati
    frame yang tidak perlu) supaya posisi sampel presisi dan cepat.
    """
    cv2 = _cv2()
    track = FaceTrack(duration=float(duration), sample_fps=float(sample_fps))
    if cv2 is None or detector is None or duration <= 0:
        return track

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return track

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if not fps or fps <= 0:
            fps = 25.0
        total_samples = max(1, int(math.ceil(duration * sample_fps)))
        start_frame = max(0, int(round(start * fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        # `grabbed` = indeks frame terakhir yang berhasil di-grab (retrieve()
        # mengembalikan frame itu, jadi harus di-grab dulu).
        grabbed = start_frame - 1
        last_cx: float | None = None
        last_size = 0.0

        for k in range(total_samples):
            want_time = k / sample_fps
            target = start_frame + int(round(want_time * fps))
            # grab() mengambil frame terakhir yang di-grab; retrieve() mengembalikan
            # frame itu. Jadi `grabbed` = indeks frame terakhir yang di-grab.
            while grabbed < target:
                if not cap.grab():
                    break
                grabbed += 1

            ok, frame = cap.retrieve()
            if not ok or frame is None:
                track.times.append(want_time)
                track.xs.append(None)
                track.ys.append(None)
                track.sizes.append(0.0)
                track.scores.append(0.0)
                break

            faces = detector.detect(frame)
            face = _pick_face(
                faces, last_cx, last_size, frame.shape[1], max_jump_ratio
            )
            track.times.append(want_time)
            if face is None:
                track.xs.append(None)
                track.ys.append(None)
                track.sizes.append(0.0)
                track.scores.append(0.0)
            else:
                track.xs.append(face.cx)
                track.ys.append(face.cy)
                track.sizes.append(face.w)
                track.scores.append(face.score)
                last_cx = face.cx
                last_size = face.w
    finally:
        cap.release()

    return track


def _fill_gaps(values: list[float | None]) -> list[float]:
    """Isi celah: interpolasi linear di tengah, tahan (hold) di ujung."""
    n = len(values)
    known = [i for i, v in enumerate(values) if v is not None]
    if not known:
        return []
    filled: list[float] = [0.0] * n
    for i in known:
        filled[i] = float(values[i])  # type: ignore[arg-type]
    for a, b in zip(known, known[1:]):
        if b - a <= 1:
            continue
        va = float(values[a])  # type: ignore[arg-type]
        vb = float(values[b])  # type: ignore[arg-type]
        for i in range(a + 1, b):
            ratio = (i - a) / float(b - a)
            filled[i] = va + (vb - va) * ratio
    first, last = known[0], known[-1]
    for i in range(0, first):
        filled[i] = float(values[first])  # type: ignore[arg-type]
    for i in range(last + 1, n):
        filled[i] = float(values[last])  # type: ignore[arg-type]
    return filled


def _median_filter(values: list[float], window: int) -> list[float]:
    """Filter median (jendela ganjil) untuk membuang deteksi liar."""
    if window <= 1 or len(values) < 3:
        return list(values)
    w = window if window % 2 == 1 else window + 1
    half = w // 2
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        chunk = sorted(values[lo:hi])
        out.append(chunk[len(chunk) // 2])
    return out


def _moving_average(values: list[float], window: int) -> list[float]:
    """Rata-rata bergerak (jendela-centered, tepi dijaga)."""
    if window <= 1 or len(values) < 2:
        return list(values)
    half = max(1, window // 2)
    out: list[float] = []
    for i in range(len(values)):
        lo = max(0, i - half)
        hi = min(len(values), i + half + 1)
        chunk = values[lo:hi]
        out.append(sum(chunk) / len(chunk))
    return out


def smooth_track(
    track: FaceTrack, window: int = DEFAULT_SMOOTH_WINDOW
) -> tuple[list[float], list[float]]:
    """Isi celah + haluskan lintasan. Return ``(xs, ys)`` satu nilai per sampel."""
    if not track.xs:
        return [], []
    xs = _fill_gaps(track.xs)
    ys = _fill_gaps(track.ys)
    if not xs:
        return [], []
    xs = _median_filter(xs, window)
    ys = _median_filter(ys, window)
    xs = _moving_average(xs, 3)
    ys = _moving_average(ys, 3)
    return xs, ys


def crop_positions(
    track: FaceTrack,
    xs: list[float],
    ys: list[float],
    src_w: int,
    src_h: int,
    out_w: int,
    out_h: int,
    face_height_ratio: float = 0.25,
) -> tuple[str, list[tuple[float, float]], int, int]:
    """Ubah lintasan menjadi posisi crop di ruang koordinat hasil ``scale``.

    Landscape (sumber lebih lebar dari 9:16): crop bergerak **horizontal**,
    wajah dikejar ke tengah frame. Portrait: crop bergerak **vertikal**,
    wajah ditempatkan pada 1/4 tinggi frame (bukan tengah) supaya ada ruang
    untuk subtitle.

    Return ``(axis, [(waktu, posisi), ...], scaled_w, scaled_h)``.
    """
    if not xs or not ys:
        return "x", [], out_w, out_h

    src_ratio = src_w / src_h
    dst_ratio = out_w / out_h
    positions: list[tuple[float, float]] = []

    if src_ratio > dst_ratio:
        scaled_w = int(round(out_h * src_ratio))
        scaled_w += scaled_w % 2
        scale_x = scaled_w / float(src_w)
        for t, x in zip(track.times, xs):
            pos = x * scale_x - out_w / 2.0
            pos = max(0.0, min(scaled_w - out_w, pos))
            positions.append((t, pos))
        return "x", positions, scaled_w, out_h

    scaled_h = int(round(out_w / src_ratio))
    scaled_h += scaled_h % 2
    scale_y = scaled_h / float(src_h)
    for t, y in zip(track.times, ys):
        pos = y * scale_y - out_h * face_height_ratio
        pos = max(0.0, min(scaled_h - out_h, pos))
        positions.append((t, pos))
    return "y", positions, out_w, scaled_h


def write_sendcmd(
    path: Path, axis: str, positions: list[tuple[float, float]], deadband: float = 1.0
) -> Path:
    """Tulis file perintah ``sendcmd`` untuk filter ``crop``.

    Format per baris: ``<waktu> crop <sumbu> <nilai>`` (waktu relatif terhadap
    awal klip, dalam detik). Setiap perintah **wajib** diakhiri tanda ``;``:
    file ``sendcmd`` dibaca sebagai satu daftar perintah yang dipisah ``;``,
    dan tanpa tanda itu FFmpeg menolak filenya ("Missing separator or
    extraneous data"). Perintah yang nilainya tidak berubah dilewati supaya
    filenya tetap kecil.
    """
    lines: list[str] = []
    previous: int | None = None
    for t, value in positions:
        rounded = int(round(value))
        if previous is not None and abs(rounded - previous) < deadband:
            continue
        lines.append(f"{t:.3f} crop {axis} {rounded};")
        previous = rounded
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path
