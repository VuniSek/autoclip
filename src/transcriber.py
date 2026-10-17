"""Transkripsi dengan faster-whisper, menyimpan timestamp per kata ke JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import TEMP_DIR


class TranscriptionError(RuntimeError):
    pass


def _patch_av_compat() -> str | None:
    """Cocokkan API PyAV dengan faster-whisper.

    faster-whisper memanggil ``av.open(..., metadata_errors="ignore")``, tapi
    PyAV >= 18 menghapus parameter tersebut. Shim ini membuang argumen yang
    tidak dikenali supaya kombinasi versi apa pun tetap jalan.

    ``av.open`` adalah built-in C, jadi ``inspect.signature`` tidak berguna;
    kompatibilitas dideteksi dengan mencoba pemanggilan dan menangkap TypeError.
    Return: deskripsi shim yang terpasang, atau None.
    """
    try:
        import av
    except ImportError:
        return None

    supports_kwarg = True
    try:
        av.open(b"", mode="r", metadata_errors="ignore")
    except TypeError:
        supports_kwarg = False
    except Exception:
        # error lain (mis. file kosong) -> kwarg-nya memang diterima
        pass

    if supports_kwarg:
        return None  # sudah kompatibel, tidak perlu shim

    orig_open = av.open

    def open_compat(file, mode="r", **kwargs):  # noqa: ANN001, ANN202
        kwargs.pop("metadata_errors", None)
        return orig_open(file, mode=mode, **kwargs)

    av.open = open_compat
    return f"shim av.open terpasang (av {getattr(av, '__version__', '?')})"


_AV_SHIM = _patch_av_compat()


def _resolve_device(device: str) -> str:
    """'auto' -> cuda bila tersedia, selain itu cpu."""
    if device and device.lower() != "auto":
        return device.lower()
    try:
        import ctranslate2  # dipaketkan bersama faster-whisper

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _resolve_compute_type(compute_type: str, device: str) -> str:
    """'auto' -> float16 untuk GPU, int8 untuk CPU."""
    if compute_type and compute_type.lower() != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


def transcribe(
    audio_path: Path,
    model_name: str,
    device: str = "auto",
    compute_type: str = "auto",
    language: str = "id",
    model_dir: Path | None = None,
) -> dict[str, Any]:
    """Transkripsikan audio dan kembalikan dict berisi segmen + kata.

    Struktur hasil:
    {
      "language": "id",
      "duration": 123.4,
      "text": "...",
      "segments": [{"start":0.0,"end":2.0,"text":"..."}],
      "words": [{"word":"halo","start":0.0,"end":0.4}]
    }
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "faster-whisper belum terpasang. Jalankan: pip install faster-whisper"
        ) from exc

    device = _resolve_device(device)
    compute_type = _resolve_compute_type(compute_type, device)
    print(f"[transcribe] device={device} compute_type={compute_type} model={model_name}")
    if _AV_SHIM:
        print(f"[transcribe] {_AV_SHIM}")

    model_dir = Path(model_dir) if model_dir else None
    if model_dir:
        model_dir.mkdir(parents=True, exist_ok=True)

    try:
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=str(model_dir) if model_dir else None,
        )
    except Exception as exc:
        raise TranscriptionError(
            f"Gagal memuat model Whisper '{model_name}': {exc}"
        ) from exc

    # Whisper lebih akurat dengan vad_filter; matikan kalau tidak tersedia.
    kwargs: dict[str, Any] = dict(
        language=(language or None),
        word_timestamps=True,
        beam_size=5,
        vad_filter=True,
    )
    if language and language.lower() not in ("auto", ""):
        kwargs["language"] = language

    try:
        segments_iter, info = model.transcribe(str(audio_path), **kwargs)
    except Exception as exc:
        # Sebagian environment/CPU tidak mendukung vad_filter -> coba lagi tanpa vad
        if "vad" in str(exc).lower():
            kwargs.pop("vad_filter", None)
            segments_iter, info = model.transcribe(str(audio_path), **kwargs)
        else:
            raise TranscriptionError(f"Transkripsi gagal: {exc}") from exc

    segments: list[dict] = []
    words: list[dict] = []
    last_end = 0.0

    for seg in segments_iter:  # generator, bisa lambat
        text = (seg.text or "").strip()
        segments.append(
            {
                "start": round(float(seg.start), 3),
                "end": round(float(seg.end), 3),
                "text": text,
            }
        )
        last_end = float(seg.end)
        for w in (seg.words or []):
            wtext = (w.word or "").strip()
            if not wtext:
                continue
            words.append(
                {
                    "word": wtext,
                    "start": round(float(w.start), 3),
                    "end": round(float(w.end), 3),
                    "prob": round(float(getattr(w, "probability", 0.0) or 0.0), 3),
                }
            )

    if not segments:
        raise TranscriptionError(
            "Transkripsi kosong. Periksa: audio sunyi, format rusak, atau bahasa salah."
        )

    result = {
        "language": getattr(info, "language", language) or language,
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
        "duration": round(float(getattr(info, "duration", last_end) or last_end), 3),
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "text": " ".join(s["text"] for s in segments).strip(),
        "segments": segments,
        "words": words,
    }
    return result


def save_transcript(data: dict[str, Any], path: Path | None = None) -> Path:
    """Simpan hasil transkripsi ke temp/transcript.json."""
    path = Path(path or TEMP_DIR / "transcript.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_transcript(path: Path | None = None) -> dict[str, Any]:
    """Muat transkripsi dari disk, dengan validasi ringan."""
    path = Path(path or TEMP_DIR / "transcript.json")
    if not path.exists():
        raise TranscriptionError(f"File transkrip tidak ditemukan: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("segments", "words", "duration"):
        if key not in data:
            raise TranscriptionError(f"Transkrip tidak lengkap, key '{key}' hilang: {path}")
    return data


def transcript_preview(data: dict[str, Any], limit: int = 5) -> str:
    """Potongan teks transkrip untuk ditampilkan di log."""
    segs = data.get("segments", [])
    if not segs:
        return "(kosong)"
    out = []
    for s in segs[:limit]:
        out.append(f"  [{s['start']:7.2f} -> {s['end']:7.2f}] {s['text']}")
    if len(segs) > limit:
        out.append(f"  ... ({len(segs)} segmen total)")
    return "\n".join(out)