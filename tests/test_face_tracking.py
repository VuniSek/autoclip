"""Uji face tracking (crop 9:16 yang mengikuti wajah).

Yang diuji:
  1. Deteksi wajah pada sampel waktu menghasilkan lintasan yang **mengikuti
     gerak nyata** wajah (bukan diam di tengah).
  2. Render dengan crop bergerak membuat wajah tetap **di tengah frame**
     sepanjang klip.
  3. Kalau wajah tidak ada -> fallback ke crop tengah (aturan AGENTS.md).
  4. Perataan lintasan: celah terisi, deteksi liar dibuang.
  5. Format file perintah ``sendcmd`` benar (tiap perintah diakhiri ``;``).
  6. Sumber portrait -> crop bergerak vertikal, wajah di bagian atas.

Fixture video dibuat sungguhan dengan FFmpeg: potret resmi dari White House
(domain publik) digeser pelan dari kiri ke kanan.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import face_track  # noqa: E402
from src.clipper import cut_clip, plan_face_crop  # noqa: E402

FIXTURE_IMG = ROOT / "assets" / "test_face_portrait.jpg"
W, H = 1280, 720
FPS = 25
DURASI = 6.0
#: Wajah bergerak dari x=60 ke x=900 selama DURASI detik.
X_AWAL, X_AKhir = 60.0, 900.0
#: Posisi pusat wajah di dalam gambar fixture (dihitung dari kotak YuNet).
WAJAH_DALAM_GAMBAR = 0.47


def buat_video_wajah(path: Path) -> None:
    """Video 1280x720 dengan wajah yang bergerak dari kiri ke kanan."""
    gerak = f"{X_AWAL}+{(X_AKhir - X_AWAL)}*t/{DURASI}"
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=gray:s={W}x{H}:d={DURASI}:r={FPS}",
        "-loop", "1", "-framerate", str(FPS), "-t", str(DURASI), "-i", str(FIXTURE_IMG),
        "-filter_complex",
        f"[1]scale=260:260[f];[0][f]overlay=x='{gerak}':y=200",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"gagal membuat video uji: {proc.stderr[-400:]}")


def buat_video_tanpa_wajah(path: Path) -> None:
    """Video tanpa wajah (pola tes) untuk menguji fallback crop tengah."""
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"testsrc2=s={W}x{H}:d=2:r={FPS}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"gagal membuat video tanpa wajah: {proc.stderr[-400:]}")


def posisi_wajah_di_video(path: Path) -> list[float | None]:
    """Posisi horizontal pusat wajah (0..1) per frame, None kalau tidak ada."""
    import cv2

    model = ROOT / "assets" / "face_detection_yunet_2023mar.onnx"
    det = cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.6, 0.3, 5000)
    cap = cv2.VideoCapture(str(path))
    out: list[float | None] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        det.setInputSize((w, h))
        ok2, faces = det.detect(frame)
        if not ok2 or faces is None:
            out.append(None)
            continue
        best = max(faces, key=lambda b: float(b[2]) * float(b[3]))
        out.append((float(best[0]) + float(best[2]) / 2.0) / w)
    cap.release()
    return out


def main() -> int:
    failures: list[str] = []
    print("=== Uji face tracking (crop mengikuti wajah) ===\n")

    if not FIXTURE_IMG.exists():
        print(f"GAGAL: fixture wajah tidak ada: {FIXTURE_IMG}")
        return 1
    if shutil.which("ffmpeg") is None:
        print("GAGAL: ffmpeg tidak ada di PATH.")
        return 1

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        video = work / "wajah_bergerak.mp4"
        buat_video_wajah(video)
        print(f"[1] Video uji dibuat: {video.name} "
              f"(wajah bergerak x={X_AWAL:.0f} -> {X_AKhir:.0f})")

        # -- 2. deteksi + lintasan -----------------------------------------
        print("\n[2] Deteksi wajah per sampel waktu")
        detector = face_track.FaceDetector()
        print(f"  detektor  : {detector.backend}")
        if detector.backend == "none":
            failures.append("tidak ada detektor wajah yang bisa dipakai")
        track = face_track.track_faces(video, 0.0, DURASI, detector, sample_fps=10.0)
        print(f"  sampel    : {track.total}, terdeteksi {track.detected}")
        if track.detected < track.total * 0.8:
            failures.append(
                f"wajah hanya terdeteksi di {track.detected}/{track.total} sampel"
            )

        xs, ys = face_track.smooth_track(track, window=5)
        if len(xs) != track.total:
            failures.append("lintasan tidak lengkap (jumlah nilai != jumlah sampel)")
        # Posisi wajah sebenarnya: gambar bergerak + offset wajah di dalam gambar
        err = []
        for t, x in zip(track.times, xs):
            # pusat wajah di sumber = posisi gambar + offset wajah di dalam gambar
            harapan = X_AWAL + (X_AKhir - X_AWAL) * t / DURASI + WAJAH_DALAM_GAMBAR * 260
            err.append(abs(x - harapan))
        rata = sum(err) / len(err) if err else 999
        maks = max(err) if err else 999
        print(f"  galat lintasan: rata-rata {rata:.1f} px, maks {maks:.1f} px")
        if rata > 25:
            failures.append(f"lintasan wajah meleset jauh (rata-rata {rata:.1f} px)")

        # -- 3. render dengan crop bergerak ----------------------------------
        print("\n[3] Render klip dengan crop bergerak")
        out = work / "klip_wajah.mp4"
        cut_clip(video, 0.0, DURASI, out, face_tracking=True)
        if not out.exists():
            failures.append("klip hasil render tidak ada")
        else:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                capture_output=True, text=True,
            )
            ukuran = probe.stdout.strip()
            print(f"  output    : {ukuran}")
            if ukuran != "1080,1920":
                failures.append(f"resolusi klip harus 1080x1920, dapat {ukuran}")

            posisi = posisi_wajah_di_video(out)
            ada = [p for p in posisi if p is not None]
            print(f"  wajah di frame hasil: {len(ada)}/{len(posisi)}")
            if len(ada) < len(posisi) * 0.9:
                failures.append(
                    f"wajah hilang di {len(posisi) - len(ada)} frame hasil "
                    "(crop tidak mengikuti wajah)"
                )
            if ada:
                dev = max(abs(p - 0.5) for p in ada)
                print(f"  simpangan dari tengah: maks {dev * 100:.1f}%")
                if dev > 0.15:
                    failures.append(
                        f"wajah tidak tetap di tengah frame (simpangan {dev * 100:.1f}%)"
                    )
        # -- 4. file perintah sendcmd ---------------------------------------
        print("\n[4] Isi file perintah sendcmd")
        plan = plan_face_crop(video, 0.0, DURASI, W, H)
        if plan is None or plan.commands_file is None:
            failures.append("plan_face_crop tidak menghasilkan file perintah")
        else:
            isi = plan.commands_file.read_text(encoding="utf-8")
            baris = [b for b in isi.strip().splitlines() if b.strip()]
            print(f"  perintah  : {len(baris)} baris, contoh {baris[0]!r}")
            if not all(b.rstrip().endswith(";") for b in baris):
                failures.append("setiap perintah sendcmd harus diakhiri ';'")
            nilai = [int(b.split()[-1].rstrip(";")) for b in baris]
            if len(set(nilai)) < 5:
                failures.append("perintah crop tidak bergerak (nilainya sama semua)")
            if plan.detected < plan.samples * 0.8:
                failures.append("terdeteksi wajah terlalu sedikit")
            plan.cleanup()
            if plan.commands_file.exists():
                failures.append("file perintah tidak dihapus setelah dipakai")

        # -- 5. fallback tanpa wajah ----------------------------------------
        print("\n[5] Video tanpa wajah -> fallback crop tengah")
        polos = work / "tanpa_wajah.mp4"
        buat_video_tanpa_wajah(polos)
        plan2 = plan_face_crop(polos, 0.0, 2.0, W, H)
        if plan2 is not None:
            failures.append("harus fallback (None) kalau wajah tidak terdeteksi")
        else:
            print("  rencana   : None (fallback ke crop tengah) - benar")
        out2 = work / "klip_tanpa_wajah.mp4"
        cut_clip(polos, 0.0, 2.0, out2, face_tracking=True)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out2)],
            capture_output=True, text=True,
        )
        if probe.stdout.strip() != "1080,1920":
            failures.append(f"klip fallback harus 1080x1920, dapat {probe.stdout.strip()}")
        else:
            print("  output    : 1080,1920 (crop tengah) - benar")

        # -- 6. perataan lintasan (unit) ------------------------------------
        print("\n[6] Perataan lintasan: celah terisi & deteksi liar dibuang")
        nilai_mentah = [100.0, 101.0, None, 103.0, 104.0, 500.0, 106.0, None, 108.0]
        track2 = face_track.FaceTrack(
            duration=1.0,
            sample_fps=10.0,
            times=[i / 10 for i in range(len(nilai_mentah))],
            xs=list(nilai_mentah),
            ys=list(nilai_mentah),
        )
        xs2, _ = face_track.smooth_track(track2, window=3)
        if len(xs2) != len(nilai_mentah):
            failures.append("celah tidak diisi (jumlah nilai berubah)")
        elif any(v is None for v in xs2):
            failures.append("masih ada celah yang tidak terisi")
        elif max(xs2) > 200:
            failures.append("deteksi liar (500) tidak dibuang oleh filter median")
        else:
            print(f"  hasil rata : {[round(v, 1) for v in xs2]}")

        # -- 7. sumber portrait -> crop vertikal -----------------------------
        print("\n[7] Sumber portrait -> crop bergerak vertikal")
        potret = work / "potret.mp4"
        # 720x1600 (lebih tinggi dari 9:16) -> ada ruang untuk crop vertikal
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-f", "lavfi", "-i", f"color=c=gray:s=720x1600:d=2:r={FPS}",
             "-loop", "1", "-framerate", str(FPS), "-t", "2", "-i", str(FIXTURE_IMG),
             "-filter_complex", "[1]scale=300:300[f];[0][f]overlay=x=210:y='200+800*t/2'",
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
             str(potret)],
            capture_output=True, text=True, check=False,
        )
        plan3 = plan_face_crop(potret, 0.0, 2.0, 720, 1600)
        if plan3 is None:
            failures.append("wajah tidak terdeteksi di video portrait")
        else:
            isi = plan3.commands_file.read_text(encoding="utf-8")
            baris = [b for b in isi.strip().splitlines() if b.strip()]
            print(f"  perintah   : {baris[0]!r} ... {baris[-1]!r}")
            if " crop y " not in isi:
                failures.append("sumber portrait harus memakai sumbu y (vertikal)")
            nilai_y = [int(b.split()[-1].rstrip(";")) for b in baris]
            if len(set(nilai_y)) < 2:
                failures.append("crop vertikal tidak bergerak mengikuti wajah")
            out3 = work / "klip_potret.mp4"
            cut_clip(potret, 0.0, 2.0, out3, face_tracking=True)
            probe3 = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out3)],
                capture_output=True, text=True,
            )
            if probe3.stdout.strip() != "1080,1920":
                failures.append(
                    f"klip portrait harus 1080x1920, dapat {probe3.stdout.strip()}"
                )
            plan3.cleanup()

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan face tracking LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
