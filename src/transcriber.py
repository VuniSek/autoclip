"""Transkripsi dengan faster-whisper, menyimpan timestamp per kata ke JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

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


# Pustaka yang wajib ada supaya ctranslate2/faster-whisper bisa menghitung di GPU.
CUDA_LIBS = ("libcublas.so.12", "libcudnn.so.9")

# Potongan pesan galat yang menandakan GPU tidak bisa dipakai sama sekali.
CUDA_ERROR_MARKERS = (
    "libcublas",
    "libcudnn",
    "cannot be loaded",
    "cuda_error",
    "no kernel image",
    "cuda initialization",
)


def missing_cuda_libs() -> list[str]:
    """Daftar pustaka CUDA yang tidak bisa dimuat loader (lihat problem.md P-015).

    `get_cuda_device_count()` tidak cukup: ia mengembalikan jumlah GPU даже kalau
    cuBLAS belum terpasang, sehingga program memilih cuda lalu crash saat encode.
    """
    import ctypes

    missing: list[str] = []
    for lib in CUDA_LIBS:
        try:
            ctypes.CDLL(lib)
        except OSError:
            missing.append(lib)
    return missing


def _is_cuda_error(exc: BaseException) -> bool:
    msg = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in msg for marker in CUDA_ERROR_MARKERS)


def _resolve_compute_type(compute_type: str, device: str) -> str:
    """'auto' -> float16 untuk GPU, int8 untuk CPU."""
    if compute_type and compute_type.lower() != "auto":
        return compute_type
    return "float16" if device == "cuda" else "int8"


def _collect_segments(segments_iter: Any, device: str) -> tuple[list[dict], list[dict], float]:
    """Kumpulkan segmen + kata dari generator faster-whisper.

    Generator baru berjalan di sini, jadi error apa pun dari ctranslate2 (mis.
    pustaka CUDA tidak termuat) muncul di fungsi ini, bukan di `model.transcribe()`.
    """
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
    return segments, words, last_end


def _transcribe_once(
    audio_path: Path,
    model: Any,
    kwargs: dict[str, Any],
    device: str,
    model_factory: Callable[[str, str], Any],
    device_setting: str,
) -> tuple[list[dict], list[dict], float, Any, str]:
    """Jalankan transkripsi; kalau GPU gagal karena pustaka CUDA, ulangi di CPU.

    Fallback hanya otomatis bila perangkat tidak dipaksa user (WHISPER_DEVICE=auto).
    Kalau user memang meminta cuda, galatnya dibiarkan sebagai `TranscriptionError`
    berisi cara memperbaiki, supaya tidak ada perubahan setting secara diam-diam
    (lihat problem.md P-015).
    """

    def run(current_kwargs: dict[str, Any]) -> tuple[list[dict], list[dict], float, Any, str]:
        segments_iter, info = model.transcribe(str(audio_path), **current_kwargs)
        segments, words, last_end = _collect_segments(segments_iter, device)
        return segments, words, last_end, info, device

    try:
        return run(dict(kwargs))
    except Exception as exc:
        # Sebagian environment/CPU tidak mendukung vad_filter -> coba lagi tanpa vad.
        if "vad" in str(exc).lower() and kwargs.get("vad_filter"):
            print(f"[transcribe] vad_filter tidak bisa dipakai ({exc.__class__.__name__}), ulangi tanpa vad")
            retry_kwargs = dict(kwargs)
            retry_kwargs.pop("vad_filter", None)
            try:
                return run(retry_kwargs)
            except Exception as exc2:
                exc = exc2

        if device != "cuda" or not _is_cuda_error(exc):
            raise TranscriptionError(f"Transkripsi gagal: {exc}") from exc

        if device_setting != "auto":
            missing = ", ".join(missing_cuda_libs()) or "tidak diketahui"
            raise TranscriptionError(
                "GPU diminta (WHISPER_DEVICE=cuda) tapi ctranslate2 tidak bisa memakainya:\n"
                f"  {exc}\n"
                "  Pustaka CUDA yang tidak termuat: " + missing + "\n"
                "  Cara memperbaiki:\n"
                "    1) di Colab, jalankan lewat autoclip_colab.py (pustakanya dipasang otomatis), atau\n"
                "    2) pip install nvidia-cublas-cu12 nvidia-cudnn-cu12==9.* lalu tambahkan\n"
                "       folder 'site-packages/nvidia/*/lib' ke LD_LIBRARY_PATH, atau\n"
                "    3) pakai CPU: ubah WHISPER_DEVICE=cpu dan WHISPER_COMPUTE_TYPE=int8 di .env"
            ) from exc

        print(
            f"[transcribe] GPU gagal dipakai ({type(exc).__name__}: {exc})\n"
            "[transcribe] otomatis mengulang transkripsi di CPU (int8), lebih lambat "
            "tapi hasilnya sama."
        )
        cpu_model = model_factory("cpu", "int8")
        return _transcribe_once(
            audio_path, cpu_model, kwargs, "cpu", model_factory, "cpu"
        )


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

    device_setting = (device or "auto").lower()
    device = _resolve_device(device_setting)
    compute_type = _resolve_compute_type(compute_type, device)

    # GPU terdeteksi tapi pustakanya belum termuat -> jangan crash, langsung CPU.
    # Hanya berlaku untuk 'auto'; kalau user memaksa cuda, galat harus tampil apa adanya.
    if device == "cuda" and device_setting == "auto":
        missing = missing_cuda_libs()
        if missing:
            print(
                f"[transcribe] GPU ada tapi pustaka CUDA tidak bisa dimuat "
                f"({', '.join(missing)}) -> otomatis pakai CPU int8."
            )
            device, compute_type = "cpu", "int8"

    print(f"[transcribe] device={device} compute_type={compute_type} model={model_name}")
    if _AV_SHIM:
        print(f"[transcribe] {_AV_SHIM}")

    model_dir = Path(model_dir) if model_dir else None
    if model_dir:
        model_dir.mkdir(parents=True, exist_ok=True)

    def load_model(dev: str, ctype: str):  # noqa: ANN202
        try:
            return WhisperModel(
                model_name,
                device=dev,
                compute_type=ctype,
                download_root=str(model_dir) if model_dir else None,
            )
        except Exception as exc:
            raise TranscriptionError(
                f"Gagal memuat model Whisper '{model_name}' (device={dev}): {exc}"
            ) from exc

    model = load_model(device, compute_type)
    initial_device = device

    # Whisper lebih akurat dengan vad_filter; matikan kalau tidak tersedia.
    kwargs: dict[str, Any] = dict(
        language=(language or None),
        word_timestamps=True,
        beam_size=5,
        vad_filter=True,
    )
    if language and language.lower() not in ("auto", ""):
        kwargs["language"] = language

    # model.transcribe() hanya mengembalikan generator; galat CUDA baru muncul
    # saat diiterasi, jadi seluruh pemanggilan + iterasi harus di dalam try
    # (lihat problem.md P-015).
    initial_device = device
    segments, words, last_end, info, device = _transcribe_once(
        audio_path, model, kwargs, device, load_model, device_setting
    )
    if device != initial_device:
        print(f"[transcribe] selesai di device={device} compute_type=int8")

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