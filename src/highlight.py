"""Panggil OpenRouter untuk memilih segmen terbaik (highlight) dari transkrip.

Output WAJIB JSON: [{"start": detik, "end": detik, "title": "...", "reason": "..."}]

Model gratis sering rate limit / balas JSON berantakan, jadi:
  - retry dengan exponential backoff,
  - bersihkan pembungkus ```json dan teks sebelum/sesudah JSON,
  - perbaiki koma/quote yang hilang bila memungkinkan,
  - validasi hasil (start<end, durasi dalam batas, tidak melewati durasi video).
"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Any

import requests

DEFAULT_TIMEOUT = 120


class HighlightError(RuntimeError):
    pass


# ---------------------------------------------------------------- prompt

SYSTEM_PROMPT = (
    "Kamu adalah editor video senior yang memilih klip viral untuk media sosial. "
    "Kamu HANYA boleh menjawab dengan JSON valid, tanpa teks tambahan, tanpa markdown, "
    "tanpa penjelasan di luar JSON."
)


def build_user_prompt(
    transcript_text: str,
    duration: float,
    max_clips: int,
    min_seconds: int,
    max_seconds: int,
    language: str,
) -> str:
    lang_note = (
        "Bahasa utama video: Indonesia. Tulis 'title' dalam Bahasa Indonesia."
        if language.lower().startswith("id")
        else f"Bahasa utama video: {language}. Tulis 'title' dalam bahasa yang sama."
    )
    return f"""Berikut transkrip video berdurasi {duration:.1f} detik, beserta penanda waktu
tiap segmen (detik). Setiap baris berformat: [mulai -> selesai] teks.

=== TRANSKRIP ===
{transcript_text}
=== AKHIR TRANSKRIP ===

Tugasmu: pilih paling banyak {max_clips} segmen yang layak dijadikan klip pendek.

Aturan wajib:
1. Durasi tiap segmen antara {min_seconds} dan {max_seconds} detik (selalu bulat, >= {min_seconds}).
2. Segmen harus punya HOOK kuat di 3 detik pertama (pertanyaan, klaim mengejutkan,
   anecdote pribadi, atau undisputed statement).
3. Segmen harus berupa TOPIK UTUH: boleh sedikit tambah konteks sebelum/di akhir agar
   tidak terpotong di tengah kalimat.
4. Jangan pilih segmen yang saling tumpang tindih (overlap).
5. Pilih 'start' dan 'end' dari angka penanda waktu yang ada di transkrip ( snapping
   ke batas segmen terdekat diperbolehkan ).
6. Maksimal {max_clips} segmen. Kalau tidak ada yang memenuhi kriteria, kembalikan [].
7. {lang_note}
8. 'reason' maksimal 15 kata, bahasa Indonesia, menjelaskan kenapa segmen ini viral.

Balas HANYA dengan array JSON valid dengan format persis:
[{{"start": 12.5, "end": 58.0, "title": "Judul pendek", "reason": "Alasan singkat"}}]
Jangan tambahkan markdown, kode fence, atau komentar apa pun."""


# ---------------------------------------------------------------- json cleaning

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def strip_code_fences(text: str) -> str:
    """Hapus pembungkus ```json ... ```."""
    if not text:
        return ""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _balance(text: str) -> str:
    """Buat kurung kurawal/kurung siku seimbang agar json.loads tidak gagal."""
    stack: list[str] = []
    in_str = False
    esc = False
    pairs = {"{": "}", "[": "]"}
    closers = {"}": "{", "]": "["}
    for ch in text:
        if esc:
            esc = False
            continue
        if ch == "\\":
            if in_str:
                esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif ch in closers:
            if stack and stack[-1] == ch:
                stack.pop()
            else:
                stack.pop() if stack else None
    if in_str:
        text += '"'
    return text + "".join(reversed(stack))


def _scan_array_span(text: str, start: int) -> int | None:
    """Dari indeks '[' di `start`, cari indeks ']' penutup yang sesuai.

    Mengabaikan kurung di dalam string dan escaped quote.
    Return indeksExclusive dari ']', atau None kalau tidak ketemu.
    """
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            if in_str:
                esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def _extract_array(text: str) -> list | None:
    """Ambil array JSON pertama yang valid dari teks (abaikan teks sebelum/sesudah).

    Menangani:
      - pembungkus ```json ... ```
      - kalimat pembuka/penutup dari model
      - array terpotong (kurang kurung siku -> dilengkapi)
    """
    text = strip_code_fences(text)
    for start_idx, ch in enumerate(text):
        if ch != "[":
            continue
        span_end = _scan_array_span(text, start_idx)
        candidates: list[str] = []
        if span_end is not None:
            candidates.append(text[start_idx:span_end])  # array tertutup rapi
        candidates.append(text[start_idx:])  # mungkin ada sisa di belakang
        candidates.append(_balance(text[start_idx:]))  # perbaiki kurung kurang
        for attempt in candidates:
            try:
                data = json.loads(attempt)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue
    return None


# ---------------------------------------------------------------- validation

def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r"-?\d+(?:[.,]\d+)?", value.replace(" ", ""))
        if m:
            return float(m.group(0).replace(",", "."))
    return None


def validate_segments(
    raw: Any,
    duration: float,
    min_seconds: int,
    max_seconds: int,
) -> list[dict]:
    """Normalisasi + validasi output LLM. Buang yang tidak valid."""
    if raw is None:
        raise HighlightError("Output LLM tidak bisa diparse sebagai JSON array.")
    if isinstance(raw, dict):
        # beberapa model membungkus: {"clips": [...]} atau {"segments": [...]}
        for key in ("clips", "segments", "results", "highlights", "data"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
        else:
            raw = [raw]
    if not isinstance(raw, list):
        raise HighlightError(f"Output LLM harus array, dapat {type(raw).__name__}")

    cleaned: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start = _coerce_float(item.get("start"))
        end = _coerce_float(item.get("end"))
        if start is None or end is None:
            continue
        start = max(0.0, start)
        end = min(duration, end)  # jangan melewati durasi video
        if end <= start:
            continue

        seg_len = end - start
        # toleransi: durasi di luar batas dipotong ke batas terdekat
        if seg_len < min_seconds:
            end = min(duration, start + min_seconds)
        elif seg_len > max_seconds:
            end = min(duration, start + max_seconds)
        if end <= start or (end - start) < min_seconds * 0.9:
            continue
        end = min(duration, end)
        if end - start > max_seconds:
            continue

        title = str(item.get("title") or "Klip").strip()[:120] or "Klip"
        reason = str(item.get("reason") or "").strip()[:200]
        cleaned.append(
            {
                "start": round(start, 2),
                "end": round(end, 2),
                "title": title,
                "reason": reason,
            }
        )

    cleaned.sort(key=lambda d: d["start"])

    # buang overlap
    result: list[dict] = []
    for seg in cleaned:
        if result and seg["start"] < result[-1]["end"]:
            continue
        result.append(seg)
    return result


# ---------------------------------------------------------------- API call

def _call_once(
    api_key: str,
    base_url: str,
    model: str,
    user_prompt: str,
    timeout: int,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/autoclip",
        "X-Title": "AUTO CLIP",
    }
    resp = requests.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    if resp.status_code != 200:
        # Jangan dump body penuh karena bisa memuat info sensitif; ambil ringkas.
        snippet = resp.text[:400].replace(api_key, "***")
        raise HighlightError(f"HTTP {resp.status_code} dari OpenRouter: {snippet}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise HighlightError(f"Respons OpenRouter tidak punya choices: {str(data)[:300]}") from exc


def select_highlights(
    api_key: str,
    base_url: str,
    model: str,
    transcript_text: str,
    duration: float,
    max_clips: int,
    min_seconds: int,
    max_seconds: int,
    language: str = "id",
    max_retries: int = 3,
    timeout: int = DEFAULT_TIMEOUT,
    on_retry=None,
) -> list[dict]:
    """Panggil LLM dengan retry/backoff, Return list segmen tervalidasi."""
    user_prompt = build_user_prompt(
        transcript_text, duration, max_clips, min_seconds, max_seconds, language
    )
    last_err: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            content = _call_once(api_key, base_url, model, user_prompt, timeout)
            raw = _extract_array(content)
            if raw is None:
                raise HighlightError(
                    "Tidak menemukan array JSON di balasan model "
                    f"(awal: {strip_code_fences(content)[:200]!r})"
                )
            segments = validate_segments(raw, duration, min_seconds, max_seconds)
            if not segments:
                raise HighlightError("Semua segmen dari LLM tidak lolos validasi (hasil kosong).")
            return segments
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt >= max_retries:
                break
            # backoff eksponensial + jitter
            delay = min(60.0, (2**attempt)) + random.uniform(0, 3)
            msg = (
                f"[highlight] percobaan {attempt}/{max_retries} gagal: {exc}. "
                f"Retry dalam {delay:.1f}s..."
            )
            print(msg)
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(delay)

    raise HighlightError(
        f"Gagal mendapatkan segmen highlight setelah {max_retries} percobaan "
        f"pada model '{model}'. Error terakhir: {last_err}"
    )