"""Buat file subtitle (.srt dan .ass) dari timestamp per kata, lalu bakar ke video.

Aturan tampilan:
  - maksimal 2 baris per tampilan,
  - teks besar, tebal, di tengah-bawah,
  - pengelompokan kata berdasarkan waktu: potong cue saat kata melewati batas durasi,
  - lebar baris dihitung dalam PIXEL (bukan jumlah karakter) supaya tidak keluar frame,
  - tidak ada dua cue yang aktif bersamaan (lihat problem.md P-026).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .clipper import TARGET_H, TARGET_W

# Durasi maximal satu tampilan (detik) sebelum di-break ke tampilan baru
MAX_CUE_SECONDS = 2.5

# --- Layout (semuanya dalam pixel pada resolusi 1080x1920) ---
FONT_NAME = "DejaVu Sans"
FONT_SIZE = 72          # cukup besar, tapi 2 baris tetap muat di area teks
MARGIN_L = 80           # ruang aman dari tepi kiri/kanan
MARGIN_R = 80
MARGIN_V = 420          # di atas area UI platform (ikon kanan bawah, caption)
OUTLINE = 6
SHADOW = 3
MAX_LINES = 2
MIN_CUE_SECONDS = 0.30  # jangan sampai cue tanpa durasi

# Lebar area teks yang boleh dipakai satu baris (tanpa outline/shadow).
TEXT_AREA_WIDTH = TARGET_W - MARGIN_L - MARGIN_R - 2 * (OUTLINE + SHADOW)

# Batas karakter sebagai jaring pengaman (bukan penentu utama; yang menentukan
# adalah lebar piksel).
MAX_CHARS_PER_LINE = 24
MAX_CHARS_PER_CUE = 48

# Kandidat file font DejaVu Sans Bold untuk pengukuran (harus sama dengan font
# yang dipakai libass supaya hasil pengukuran akurat).
FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/local/share/fonts/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

# Faktor lebar per karakter sebagai cadangan kalau Pillow tidak tersedia.
# Dipakai faktor KONSERVATIF (huruf besar/angka paling lebar di DejaVu Sans).
FALLBACK_CHAR_RATIO = 0.62


class SubtitleError(RuntimeError):
    pass


def _clean_word(raw: str) -> str:
    return re.sub(r"\s+", " ", (raw or "").strip())


@lru_cache(maxsize=8)
def _load_font():
    """Muat font DejaVu Sans Bold untuk pengukuran lebar. None kalau tidak ada."""
    try:
        from PIL import ImageFont
    except ImportError:
        return None
    for path in FONT_PATHS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, FONT_SIZE)
            except Exception:  # noqa: BLE001 - font rusak, coba berikutnya
                continue
    return None


def measure_text_width(text: str, font_size: int = FONT_SIZE) -> float:
    """Lebar teks dalam pixel memakai font yang sama dengan libass.

    Kalau Pillow tidak terpasang, dipakai estimator konservatif (huruf besar/angka),
    sehingga batas yang dihitung tidak pernah lebih longgar dari kenyataan.
    """
    if not text:
        return 0.0
    font = _load_font()
    if font is not None:
        try:
            return float(font.getlength(text))
        except Exception:  # noqa: BLE001
            pass
    return len(text) * font_size * FALLBACK_CHAR_RATIO


def _fit_single_line(text: str) -> bool:
    """True kalau teks muat dalam satu baris (lebar + batas karakter)."""
    return (
        len(text) <= MAX_CHARS_PER_LINE
        and measure_text_width(text) <= TEXT_AREA_WIDTH
    )


def _hard_split_word(word: str, max_width: float) -> list[str]:
    """Potong satu kata yang terlalu lebar jadi beberapa potongan per karakter."""
    bagian: list[str] = []
    sekarang = ""
    for ch in word:
        calon = sekarang + ch
        if sekarang and measure_text_width(calon) > max_width:
            bagian.append(sekarang)
            sekarang = ch
        else:
            sekarang = calon
    if sekarang:
        bagian.append(sekarang)
    return bagian or [word]


def _split_lines(text: str) -> list[str]:
    """Pecah teks jadi maksimal 2 baris yang muat di area teks (lebar piksel).

    Berbeda dari versi lama, batas yang dipakai adalah lebar piksel, bukan jumlah
    karakter, dan hasilnya tidak pernah melewati batas (lihat problem.md P-026).
    """
    words = text.split()
    if not words:
        return []
    if _fit_single_line(text):
        return [text]

    # 1) wrap biasa: isi baris pertama selagi muat, sisanya jadi baris kedua.
    baris1: list[str] = []
    baris2: list[str] = []
    for word in words:
        calon1 = " ".join(baris1 + [word])
        if not baris2 and _fit_single_line(calon1):
            baris1.append(word)
            continue
        baris2.append(word)
    if baris2 and _fit_single_line(" ".join(baris2)):
        return [" ".join(baris1), " ".join(baris2)] if baris1 else [" ".join(baris2)]

    # 2) dua baris seimbang: cari titik potong yang paling imbang.
    best, best_diff = None, None
    for i in range(1, len(words)):
        kiri = " ".join(words[:i])
        kanan = " ".join(words[i:])
        if not _fit_single_line(kiri) or not _fit_single_line(kanan):
            continue
        diff = abs(len(kiri) - len(kanan))
        if best_diff is None or diff < best_diff:
            best, best_diff = (kiri, kanan), diff
    if best:
        return [ln for ln in best if ln]

    # 3) kata tunggal yang terlalu lebar -> potong per karakter.
    potongan: list[str] = []
    for word in words:
        potongan.extend(_hard_split_word(word, TEXT_AREA_WIDTH))
    if not potongan:
        return [text]
    if len(potongan) == 1:
        return [potongan[0]]
    mid = len(potongan) // 2
    baris_atas = " ".join(potongan[:mid])
    baris_bawah = " ".join(potongan[mid:])
    return [ln for ln in (baris_atas, baris_bawah) if ln]


def _text_fits_two_lines(text: str) -> bool:
    """True kalau teks muat maksimal 2 baris pada area teks."""
    baris = _split_lines(text)
    if len(baris) > MAX_LINES:
        return False
    return all(measure_text_width(ln) <= TEXT_AREA_WIDTH for ln in baris)


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


def group_cues(words: list[dict]) -> list[dict]:
    """Kelompokkan kata jadi cue.

    Aturan:
      - satu cue = maksimal 2 baris yang muat di area teks,
      - durasi maksimal `MAX_CUE_SECONDS`,
      - **tidak boleh ada cue yang overlap** (lihat problem.md P-026): cue berikutnya
        selalu mulai pada atau setelah cue sebelumnya selesai.
    """
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
        too_long_text = (
            len(cand_text) > MAX_CHARS_PER_CUE or not _text_fits_two_lines(cand_text)
        )
        too_long_time = span > MAX_CUE_SECONDS
        # avoid one orphan word creating a 1-word cue when we can help it
        if cur_words and (too_long_text or too_long_time):
            flush()
        cur_words.append(w)
        # tutup cue setelah kata yang mengakhiri kalimat
        if re.search(r"[.!?]$", w["word"]):
            flush()
    flush()
    return fix_overlaps(cues)


def fix_overlaps(cues: list[dict]) -> list[dict]:
    """Jamin tidak ada dua cue yang aktif bersamaan.

    Cue diurutkan berdasarkan waktu mulai. Cue berikutnya dipaksa mulai pada waktu
    selesai cue sebelumnya (kalau masih tumpang tindih), cue sebelumnya dipotong
    bila perlu, dan durasi minimum `MIN_CUE_SECONDS` dijaga.
    """
    if not cues:
        return []
    urut = sorted(cues, key=lambda c: (float(c["start"]), float(c["end"])))
    hasil: list[dict] = []
    for cue in urut:
        start = float(cue["start"])
        end = float(cue["end"])
        if hasil:
            sebelumnya = hasil[-1]
            if start < float(sebelumnya["end"]):
                # Cue ini dimulai sebelum cue sebelumnya selesai -> geser ke
                # belakang, dan potong cue sebelumnya bila masih tumpang tindih.
                start = float(sebelumnya["end"])
                if end < start + MIN_CUE_SECONDS:
                    end = start + MIN_CUE_SECONDS
                if float(sebelumnya["end"]) > start:
                    sebelumnya["end"] = start
        if end < start + MIN_CUE_SECONDS:
            end = start + MIN_CUE_SECONDS
        cue = dict(cue)
        cue["start"] = round(start, 3)
        cue["end"] = round(end, 3)
        hasil.append(cue)
    return hasil


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


def write_ass(cues: list[dict], path: Path, font: str = FONT_NAME,
              font_size: int = FONT_SIZE) -> Path:
    """Tulis .ass untuk dibakar ke video (gaya besar, tebal, tengah-bawah)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ASS_HEADER.format(
        w=TARGET_W, h=TARGET_H, font=font, fontsize=font_size,
        outline=OUTLINE, shadow=SHADOW,
        margin_l=MARGIN_L, margin_r=MARGIN_R, margin_v=MARGIN_V,
    )
    lines = [header]
    for c in cues:
        # WAJIB pakai hasil pemecahan baris: header memakai WrapStyle 2 (libass tidak
        # membungkus otomatis, hanya menghormati \N). Kalau teks penuh dikirim sebagai
        # satu baris, teks akan keluar dari frame dan terpotong (lihat problem.md
        # P-008 dan P-026).
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
