"""Buat file subtitle (.srt dan .ass) dari timestamp per kata, lalu bakar ke video.

Aturan tampilan:
  - maksimal 2 baris per tampilan,
  - teks besar, tebal, di tengah-bawah,
  - pengelompokan kata berdasarkan waktu: potong cue saat kata melewati batas durasi.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .clipper import TARGET_H, TARGET_W

# Durasi maximal satu tampilan (detik) sebelum di-break ke tampilan baru
MAX_CUE_SECONDS = 2.5
MAX_CHARS_PER_LINE = 22
MAX_CHARS_PER_CUE = 46


class SubtitleError(RuntimeError):
    pass


def _clean_word(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


def slice_words(words: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    """Ambil kata yang berada di dalam [clip_start, clip_end], geser ke waktu lokal."""
    out: list[dict] = []
    for w in words:
        ws, we = float(w["start"]), float(w["end"])
        if we <= clip_start or ws >= clip_end:
            continue
        local_s = max(0.0, ws - clip_start)
        local_e = min(clip_end - clip_start, we - clip_start)
        if local_e <= local_s:
            continue
        text = _clean_word(w["word"])
        if not text:
            continue
        out.append({"word": text, "start": local_s, "end": local_e})
    out.sort(key=lambda d: d["start"])
    return out


def _split_lines(text: str) -> list[str]:
    """Pecah teks jadi maksimal 2 baris dengan lebar seimbang."""
    words = text.split()
    if not words:
        return []
    if len(text) <= MAX_CHARS_PER_LINE:
        return [text]
    # Cari titik potong yang paling seimbang
    best, best_diff = None, None
    for i in range(1, len(words)):
        left = " ".join(words[:i])
        right = " ".join(words[i:])
        if len(left) > MAX_CHARS_PER_LINE or len(right) > MAX_CHARS_PER_LINE:
            break
        diff = abs(len(left) - len(right))
        if best_diff is None or diff < best_diff:
            best, best_diff = (left, right), diff
    if best is None:
        # Fallback: potong memutar
        mid = len(words) // 2 or 1
        best = (" ".join(words[:mid]), " ".join(words[mid:]))
    return [ln for ln in best if ln]


def group_cues(words: list[dict]) -> list[dict]:
    """Kelompokkan kata jadi cue: <= MAX_CARS_PER_CUE chars dan <= MAX_CUE_SECONDS."""
    cues: list[dict] = []
    cur_words: list[dict] = []

    def flush():
        nonlocal cur_words
        if not cur_words:
            return
        text = " ".join(w["word"] for w in cur_words)
        cues.append(
            {
                "start": cur_words[0]["start"],
                "end": cur_words[-1]["end"],
                "text": text,
                "lines": _split_lines(text) or [text],
            }
        )
        cur_words = []

    for w in words:
        cand = cur_words + [w]
        cand_text = " ".join(x["word"] for x in cand)
        span = w["end"] - (cur_words[0]["start"] if cur_words else w["start"])
        too_long_text = len(cand_text) > MAX_CHARS_PER_CUE
        too_long_time = span > MAX_CUE_SECONDS
        # avoid one orphan word creating a 1-word cue when we can help it
        if cur_words and (too_long_text or too_long_time):
            flush()
        cur_words.append(w)
        # tutup cue setelah kata yang mengakhiri kalimat
        if re.search(r"[.!?]$", w["word"]):
            flush()
    flush()
    return cues


def _fmt_srt_time(t: float) -> str:
    if t < 0:
        t = 0.0
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def write_srt(cues: list[dict], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, c in enumerate(cues, 1):
        blocks.append(
            f"{i}\n{_fmt_srt_time(c['start'])} --> {_fmt_srt_time(c['end'])}\n{c['text']}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{fontsize},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(cues: list[dict], path: Path, font: str = "DejaVu Sans",
              font_size: int = 88) -> Path:
    """Tulis .ass untuk dibakar ke video (gaya besar, tebal, tengah-bawah)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ASS_HEADER.format(
        w=TARGET_W, h=TARGET_H, font=font, fontsize=font_size,
        outline=6, shadow=3, margin_l=90, margin_r=90, margin_v=420,
    )
    lines = [header]
    for c in cues:
        # WAJIB pakai hasil pemecahan baris: header memakai WrapStyle 2 (libass tidak
        # membungkus otomatis, hanya menghormati \N). Kalau teks penuh dikirim sebagai
        # satu baris, teks akan keluar dari frame dan terpotong (lihat problem.md P-008).
        parts = c.get("lines") or [c["text"]]
        text = r"\N".join(parts)
        # libass escape
        text = text.replace("\\N", "\x00")  # lindungi placeholder \N
        text = text.replace("{", "\\{").replace("}", "\\}")
        text = text.replace("\x00", r"\N")
        lines.append(
            "Dialogue: 0,{s},{e},Default,,0,0,0,,{t}\n".format(
                s=_fmt_ass_time(c["start"]),
                e=_fmt_ass_time(c["end"]),
                t=text,
            )
        )
    path.write_text("".join(lines), encoding="utf-8")
    return path


def build_subtitles(
    transcript: dict[str, Any],
    clip_start: float,
    clip_end: float,
    out_dir: Path,
    basename: str,
    ass_name: str | None = None,
    srt_name: str | None = None,
) -> tuple[Path, Path]:
    """Buat .ass + .srt untuk satu segmen clip. Return (path_ass, path_srt)."""
    words = slice_words(transcript.get("words", []), clip_start, clip_end)
    if not words:
        raise SubtitleError(
            f"Tidak ada kata di rentang {clip_start:.1f}-{clip_end:.1f}; subtitle kosong."
        )
    cues = group_cues(words)
    if not cues:
        raise SubtitleError("Tidak ada cue yang bisa dibuat dari timestamp kata.")

    out_dir = Path(out_dir)
    ass_path = Path(ass_name or (out_dir / f"{basename}.ass"))
    srt_path = Path(srt_name or (out_dir / f"{basename}.srt"))
    write_ass(cues, ass_path)
    write_srt(cues, srt_path)
    return ass_path, srt_path