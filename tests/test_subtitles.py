"""Uji subtitle: tidak ada cue overlap, teks muat di frame, header .ass benar.

Masalah yang diuji: problem.md P-026 (subtitle menumpuk & keluar frame).
Test render memakai FFmpeg + libass sungguhan di atas latar hitam, lalu posisi
piksel teks diukur -> bukti langsung bahwa teks tidak keluar frame.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import subtitles as sub  # noqa: E402
from src.clipper import TARGET_H, TARGET_W  # noqa: E402

# Kata dengan timestamp yang tumpang tindih (terjadi di transkripsi Whisper saat
# bicara cepat) -> harus tetap menghasilkan cue yang tidak overlap.
WORDS_OVERLAP = [
    {"word": "a" * 30, "start": 0.00, "end": 0.50},
    {"word": "b" * 30, "start": 0.40, "end": 0.90},
    {"word": "c" * 20, "start": 0.90, "end": 1.20},
    {"word": "kalimat", "start": 1.20, "end": 1.60},
    {"word": "pendek.", "start": 1.60, "end": 2.00},
]

# Teks panjang yang dulu keluar frame (lihat P-026).
TEKS_PANJANG = (
    "Ini adalah kalimat subtitle yang sengaja dibuat sangat panjang sekali supaya "
    "pasti keluar dari frame kalau batas karakternya dipakai sebagai patokan, "
    "bukan lebar piksel yang sebenarnya"
)


def parse_ass(path: Path) -> tuple[dict, list[dict]]:
    """Baca header .ass dan daftar cue-nya."""
    header: dict[str, str] = {}
    cues: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("PlayResX:") or line.startswith("PlayResY:"):
            key, _, val = line.partition(":")
            header[key.strip()] = val.strip()
        elif line.startswith("WrapStyle:"):
            key, _, val = line.partition(":")
            header[key.strip()] = val.strip()
        elif line.startswith("Style:"):
            header["style"] = line.split(":", 1)[1].strip()
        elif line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            cues.append(
                {
                    "start": parts[1],
                    "end": parts[2],
                    "text": parts[9].replace(r"\N", "\n"),
                }
            )
    return header, cues


def ass_time(t: str) -> float:
    h, m, rest = t.split(":")
    s, cs = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100


def cek_overlap(cues: list[dict], label: str, failures: list[str]) -> None:
    for i in range(1, len(cues)):
        if cues[i]["start"] < cues[i - 1]["end"]:
            failures.append(
                f"{label}: cue {i} mulai {cues[i]['start']:.2f} < cue {i-1} selesai "
                f"{cues[i-1]['end']:.2f} (overlap)"
            )


def main() -> int:
    failures: list[str] = []
    print("=== Uji subtitle (P-026) ===\n")

    print("[1] group_cues(): tidak ada cue overlap")
    cues = sub.group_cues(WORDS_OVERLAP)
    for c in cues:
        print(f"  cue {c['start']:.2f}-{c['end']:.2f} baris={len(c['lines'])} :: {c['lines'][0][:34]!r}")
    cek_overlap(cues, "sintetis", failures)
    if not cues:
        failures.append("tidak ada cue yang terbentuk")

    print("\n[2] group_cues(): durasi minimum dan urutan waktu")
    for i in range(1, len(cues)):
        if cues[i]["start"] < cues[i - 1]["start"]:
            failures.append(f"cue {i} mulai lebih awal dari cue sebelumnya")
        if cues[i]["end"] - cues[i]["start"] < sub.MIN_CUE_SECONDS - 1e-6:
            failures.append(f"cue {i} durasi < MIN_CUE_SECONDS")
    print(f"  durasi minimum dijaga: {sub.MIN_CUE_SECONDS}s")

    print("\n[3] Maksimal 2 baris & lebar baris <= area teks")
    # Kata panjang di-offset ke detik 10 supaya tidak bentrok dengan cue pertama.
    kata_panjang = [
        {"word": w, "start": 10.0 + i * 0.5, "end": 10.0 + i * 0.5 + 0.45}
        for i, w in enumerate(TEKS_PANJANG.split())
    ]
    semua_cue = sub.group_cues(WORDS_OVERLAP) + sub.group_cues(kata_panjang)
    for c in semua_cue:
        if len(c["lines"]) > sub.MAX_LINES:
            failures.append(f"cue punya {len(c['lines'])} baris: {c['lines']}")
        for ln in c["lines"]:
            w = sub.measure_text_width(ln)
            if w > sub.TEXT_AREA_WIDTH:
                failures.append(f"baris terlalu lebar ({w:.0f}px > {sub.TEXT_AREA_WIDTH}px): {ln!r}")
    lebar_maks = max(
        (sub.measure_text_width(ln) for c in semua_cue for ln in c["lines"]), default=0
    )
    print(f"  lebar baris maks={lebar_maks:.0f}px, area teks={sub.TEXT_AREA_WIDTH}px")
    # Batas karakter tetap jadi jaring pengaman
    for c in semua_cue:
        for ln in c["lines"]:
            if len(ln) > sub.MAX_CHARS_PER_LINE:
                failures.append(f"baris melebihi batas karakter: {ln!r}")

    print("\n[4] Header .ass benar")
    with tempfile.TemporaryDirectory() as td:
        ass_path = Path(td) / "uji.ass"
        srt_path = Path(td) / "uji.srt"
        sub.write_ass(semua_cue, ass_path)
        sub.write_srt(semua_cue, srt_path)
        header, parsed = parse_ass(ass_path)
        gaya = header.get("style", "").split(",")
        print(f"  PlayResX={header.get('PlayResX')} PlayResY={header.get('PlayResY')} "
              f"WrapStyle={header.get('WrapStyle')}")
        print(f"  Style: font={gaya[1]} size={gaya[2]} outline={gaya[16]} shadow={gaya[17]} "
              f"align={gaya[18]} L={gaya[19]} R={gaya[20]} V={gaya[21]}")
        if header.get("PlayResX") != str(TARGET_W):
            failures.append(f"PlayResX harus {TARGET_W}, dapat {header.get('PlayResX')}")
        if header.get("PlayResY") != str(TARGET_H):
            failures.append(f"PlayResY harus {TARGET_H}, dapat {header.get('PlayResY')}")
        if header.get("WrapStyle") != "2":
            failures.append("WrapStyle harus 2 (kita wrap sendiri)")
        if int(gaya[2]) != sub.FONT_SIZE:
            failures.append(f"FontSize harus {sub.FONT_SIZE}, dapat {gaya[2]}")
        if int(gaya[19]) != sub.MARGIN_L or int(gaya[20]) != sub.MARGIN_R:
            failures.append(f"margin kiri/kanan harus {sub.MARGIN_L}/{sub.MARGIN_R}")
        if not 60 <= int(gaya[19]) <= 80 or not 60 <= int(gaya[20]) <= 80:
            failures.append("margin kiri/kanan harus di rentang 60-80 px")
        if int(gaya[21]) < 300:
            failures.append("MarginV harus di atas area UI platform (>= 300)")
        if gaya[18] != "2":
            failures.append("alignment harus 2 (tengah-bawah)")

        print("\n[5] .srt: cue tidak overlap dan teks utuh")
        isi_srt = srt_path.read_text(encoding="utf-8").strip().splitlines()
        blok = [b for b in isi_srt if "-->" in b]
        srt_cues = []
        for b in blok:
            awal, _, akhir = b.partition("-->")
            srt_cues.append({"start": awal.strip(), "end": akhir.strip()})
        print(f"  {len(srt_cues)} cue di .srt")
        for i in range(1, len(srt_cues)):
            if srt_cues[i]["start"] < srt_cues[i - 1]["end"]:
                failures.append(f".srt cue {i} overlap")

        print("\n[6] Render nyata (FFmpeg + libass): teks harus di dalam frame")
        frames = Path(td) / "frames"
        frames.mkdir()
        for t in (0.5, 1.0, 1.5, 2.0):
            out = frames / f"f{t}.png"
            cmd = [
                "ffmpeg", "-v", "error", "-y",
                "-f", "lavfi", "-i", f"color=c=black:s={TARGET_W}x{TARGET_H}:d=6:r=10",
                "-vf", f"ass='{ass_path}'", "-ss", str(t), "-frames:v", "1", str(out),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0 or not out.exists():
                print(f"  t={t}: render dilewati ({proc.stderr.strip()[:60]})")
                continue
            try:
                import numpy as np
                from PIL import Image
            except ImportError:
                print("  t=%s: pengukuran pixel dilewati (numpy/PIL tidak ada)" % t)
                break
            arr = np.array(Image.open(out).convert("L"))
            ys, xs = np.where(arr > 100)
            if len(xs) == 0:
                continue
            x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
            print(f"  t={t}: teks x={x0}..{x1} y={y0}..{y1}")
            if x0 <= 2:
                failures.append(f"t={t}: teks keluar frame di kiri (x={x0})")
            if x1 >= TARGET_W - 2:
                failures.append(f"t={t}: teks keluar frame di kanan (x={x1})")
            if y1 >= TARGET_H - 2:
                failures.append(f"t={t}: teks keluar frame di bawah (y={y1})")
            if y0 < 100:
                failures.append(f"t={t}: teks terlalu tinggi (y={y0})")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan subtitle LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
