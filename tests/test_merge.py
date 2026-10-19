"""Uji penggabungan klip (--merge / MERGE_CLIPS).

Clip uji dibuat sungguhan dengan FFmpeg (1080x1920 + audio), lalu digabung dan
diperiksa dengan ffprobe: harus ada stream video DAN audio, resolusinya tetap
1080x1920, dan durasinya mendekati jumlah durasi klip.

Klip asli tidak boleh hilang apa pun kalau penggabungan gagal.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import merger  # noqa: E402
from src.merger import MergeError  # noqa: E402

W, H = 1080, 1920


def buat_klip(path: Path, durasi: int, warna: str, freq: int) -> None:
    """Buat klip uji 9:16 dengan gambar + nada audio."""
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c={warna}:s={W}x{H}:d={durasi}:r=30",
        "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={durasi}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(f"gagal membuat klip uji: {proc.stderr[-300:]}")


def main() -> int:
    failures: list[str] = []
    print("=== Uji penggabungan klip (--merge) ===\n")

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        clips = [
            work / "01_tesvideo_klip1_satu.mp4",
            work / "01_tesvideo_klip2_dua.mp4",
            work / "01_tesvideo_klip3_tiga.mp4",
        ]
        for i, c in enumerate(clips):
            buat_klip(c, 2, ["red", "green", "blue"][i], 440 + i * 110)
        durasi_klip = [merger.probe_streams(c)["duration"] for c in clips]
        print(f"[1] {len(clips)} klip uji dibuat (total {sum(durasi_klip):.1f}s)")

        print("\n[2] Gabung 3 klip -> 1 file")
        out = work / "00_tesvideo_gabungan.mp4"
        hasil = merger.merge_clips(clips, out)
        info = merger.probe_streams(hasil)
        print(f"  file   : {hasil.name} ({hasil.stat().st_size / 1_048_576:.1f} MB)")
        print(f"  stream : video={info['has_video']} audio={info['has_audio']} "
              f"resolusi={info['width']}x{info['height']} durasi={info['duration']:.1f}s")
        if not info["has_video"]:
            failures.append("file gabungan tidak punya stream video")
        if not info["has_audio"]:
            failures.append("file gabungan tidak punya stream audio")
        if (info["width"], info["height"]) != (W, H):
            failures.append(f"resolusi gabungan harus {W}x{H}, dapat {info['width']}x{info['height']}")
        if abs(info["duration"] - sum(durasi_klip)) > 1.5:
            failures.append(
                f"durasi gabungan {info['duration']:.1f}s jauh dari total "
                f"{sum(durasi_klip):.1f}s"
            )
        for c in clips:
            if not c.exists():
                failures.append(f"klip individual hilang: {c.name}")

        print("\n[3] Hanya satu klip -> pesan jelas, klip tetap ada")
        try:
            merger.merge_clips([clips[0]], work / "00_satu_gabungan.mp4")
            failures.append("harus gagal kalau hanya ada satu klip")
        except MergeError as exc:
            print("  pesan:", str(exc).splitlines()[0])
            if "minimal 2 klip" not in str(exc):
                failures.append("pesan kurang jelas (minimal 2 klip)")
            if not clips[0].exists():
                failures.append("klip individual terhapus saat gagal gabung")

        print("\n[4] File klip yang tidak ada -> pesan jelas, klip lain tetap ada")
        try:
            merger.merge_clips([clips[0], work / "hilang.mp4"], work / "00_hilang_gabungan.mp4")
            failures.append("harus gagal kalau ada klip yang tidak ada")
        except MergeError as exc:
            print("  pesan:", str(exc).splitlines()[0])
            if "tidak ditemukan" not in str(exc):
                failures.append("pesan kurang jelas (file tidak ditemukan)")
            for c in clips:
                if not c.exists():
                    failures.append(f"klip individual terhapus: {c.name}")

        print("\n[5] Urutan klip dijaga (klip terakhir jadi bagian akhir)")
        # dua klip berbeda warna: gabung dua kali dengan urutan dibalik, bandingkan
        # frame terakhir -> harus berbeda (bukti urutan benar, bukan acak)
        a = work / "urut1.mp4"
        b = work / "urut2.mp4"
        merger.merge_clips([clips[0], clips[1]], a)
        merger.merge_clips([clips[1], clips[0]], b)
        warna: dict = {}
        for nama, f in (("urut1", a), ("urut2", b)):
            png = work / f"{nama}.png"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", str(f),
                 "-frames:v", "1", str(png)],
                capture_output=True,
            )
            if png.exists():
                try:
                    from PIL import Image
                    im = Image.open(png).convert("RGB")
                    px = im.getpixel((im.width // 2, im.height // 2))
                    warna[nama] = px
                except Exception:  # noqa: BLE001
                    pass
        print(f"  warna frame terakhir: {warna}")
        if len(warna) == 2 and warna["urut1"] == warna["urut2"]:
            failures.append("urutan klip tidak berpengaruh pada hasil (kemungkinan acak)")

        print("\n[6] Nama file gabungan (main.py)")
        import main as autoclip_main

        nama = autoclip_main.merged_file_name(clips)
        print(f"  merged_file_name -> {nama}")
        if not nama.startswith("00_") or not nama.endswith("_gabungan.mp4"):
            failures.append(f"nama gabungan tidak sesuai pola: {nama}")
        if "tesvideo" not in nama:
            failures.append(f"nama gabungan tidak memuat slug video: {nama}")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan penggabungan LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
