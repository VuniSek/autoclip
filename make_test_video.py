#!/usr/bin/env python3
"""Buat video uji 1-3 menit: suara Indonesia (edge-tts) + video visual pola.

Dipakai hanya untuk pengujian, bukan bagian dari alur AUTO CLIP.
"""
import asyncio
import subprocess
import sys
from pathlib import Path

import edge_tts

OUT_DIR = Path(__file__).resolve().parent / "input"
OUT_DIR.mkdir(exist_ok=True)

# Teks Indonesia pendek dengan hook kuat di beberapa titik (duram ±100 detik)
SECTIONS = [
    (
        "hook.mp3",
        "Pernah nggak kamu mikir, kenapa kita susah banget berhenti scrolling di media sosial?",
    ),
    (
        "s1.mp3",
        "Nova and I made a complete scratch rebuild from zero, because all we did before was patch the old system. "
        "The main problem was that every time we changed one menu, three other menus broke. "
        "That is not a bug, that is an architecture problem. "
        "So we decided to throw everything away and start from a blank page. "
        "It took us four months, and honestly the first two months felt like pure waste.",
    ),
    (
        "s2.mp3",
        "You know what nobody tells you about learning to code? "
        "The tutorials are the easy part. The hard part is staring at your own code that you wrote eight hours ago, "
        "and having absolutely no idea what it does. "
        "That moment, where you feel completely stupid, is actually the moment you are learning the fastest. "
        "Every senior developer I know has that moment, every single week.",
    ),
    (
        "s3.mp3",
        "This is the thing I wish someone told me at the start. "
        "Do not learn five languages at once. Learn one, get comfortable, then move. "
        "I wasted two years jumping between Python, JavaScript, and Rust because I thought I was being efficient. "
        "I was not. I was just afraid of being bad at one thing for longer than a month.",
    ),
]


async def synth(filename: str, text: str, voice: str) -> Path:
    path = OUT_DIR / filename
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(path))
    return path


async def main() -> int:
    voice = sys.argv[1] if len(sys.argv) > 1 else "id-ID-ArdiNeural"
    print(f"Suara: {voice}")
    parts = []
    for fn, text in SECTIONS:
        p = await synth(fn, text, voice)
        print(f"  {p.name}: {p.stat().st_size/1024:.0f} KB, {len(text)} char")
        parts.append(p)

    concat_list = OUT_DIR / "parts.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8"
    )
    audio = OUT_DIR / "voice_id.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c", "copy", str(audio)],
        check=True,
    )
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(audio)],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"audio gabungan: {dur} detik")

    # Video 1280x720 dengan pola bergerak + teks waktu agar crop terlihat jelas
    out = OUT_DIR / "testvideo_id.mp4"
    vf = (
        "testsrc2=size=1280x720:rate=25:duration="
        f"{float(dur) + 1:.2f}"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", vf,
         "-i", str(audio),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-shortest", str(out)],
        check=True,
    )
    vdur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"VIDEO UJI: {out} ({vdur} detik, {out.stat().st_size/1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))