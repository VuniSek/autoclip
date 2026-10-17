#!/usr/bin/env python3
"""Uji fallback CPU untuk galat pustaka CUDA (problem.md P-015).

Tidak butuh GPU: perangkat `cuda` disimulasikan dengan model palsu yang melempar
RuntimeError `libcublas.so.12 is not found`, persis seperti faster-whisper di Colab
ketika cuBLAS tidak termuat. Galat itu muncul saat generator diiterasi, bukan saat
`model.transcribe()` dipanggil.

Jalankan: venv/bin/python tests/test_transcribe_cuda_fallback.py
"""
from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import transcriber  # noqa: E402

CUDA_ERR = "Library libcublas.so.12 is not found or cannot be loaded"
AUDIO = Path("audio.wav")


class FakeWord:
    def __init__(self, word, start, end):
        self.word, self.start, self.end, self.probability = word, start, end, 0.9


class FakeSeg:
    def __init__(self, start, end, text, words):
        self.start, self.end, self.text, self.words = start, end, text, words


class Info:
    language = "id"
    language_probability = 0.9
    duration = 3.0


def gpu_segments():
    yield FakeSeg(0.0, 1.5, "halo dunia", [FakeWord("halo", 0.0, 0.5)])
    yield FakeSeg(1.5, 3.0, "ini uji", [FakeWord("ini", 1.5, 1.8)])


class FakeModel:
    """Meledak hanya di device cuda, dan hanya saat generator diiterasi."""

    def __init__(self, device, compute_type, model_name="small"):
        self.device, self.compute_type, self.model_name = device, compute_type, model_name

    def transcribe(self, path, **kwargs):  # noqa: ARG002
        def generator():
            if self.device == "cuda":
                raise RuntimeError(CUDA_ERR)
            yield from gpu_segments()

        return generator(), Info()


class BrokenModel(FakeModel):
    """Model yang gagal dengan galat biasa (bukan masalah CUDA)."""

    def transcribe(self, path, **kwargs):  # noqa: ARG002
        def generator():
            raise ValueError("audio rusak tidak didukung")
            yield  # pragma: no cover

        return generator(), Info()


class FakeModule:
    def __init__(self, factory):
        self.WhisperModel = factory


def run(device_setting, *, libs_present: bool, model_cls=FakeModel):
    """Jalankan transcribe() dengan ctranslate2 & pustaka CUDA disimulasikan."""
    calls: list[tuple[str, str]] = []

    def factory(model_name, device, compute_type, download_root=None):  # noqa: ARG001
        calls.append((device, compute_type))
        return model_cls(device, compute_type, model_name)

    def fake_resolve_device(device):  # noqa: ARG001
        # Selalu ada GPU di mesin uji ini.
        return "cuda" if device == "auto" else device.lower()

    saved_modules = {k: v for k, v in sys.modules.items() if k.startswith("faster_whisper")}
    orig_resolve = transcriber._resolve_device
    orig_missing = transcriber.missing_cuda_libs
    for k in saved_modules:
        del sys.modules[k]
    sys.modules["faster_whisper"] = FakeModule(factory)
    transcriber._resolve_device = fake_resolve_device
    transcriber.missing_cuda_libs = lambda: [] if libs_present else ["libcublas.so.12"]

    buf = io.StringIO()
    result = error = None
    try:
        with contextlib.redirect_stdout(buf):
            result = transcriber.transcribe(
                AUDIO, model_name="small", device=device_setting,
                compute_type="auto", language="id",
            )
    except transcriber.TranscriptionError as exc:
        error = exc
    finally:
        transcriber._resolve_device = orig_resolve
        transcriber.missing_cuda_libs = orig_missing
        for k in list(sys.modules):
            if k.startswith("faster_whisper"):
                del sys.modules[k]
        sys.modules.update(saved_modules)
    return calls, result, error, buf.getvalue()


def main() -> int:
    failures: list[str] = []

    # 1. auto + pustaka CUDA tidak termuat -> langsung CPU, tidak perlu coba GPU.
    calls, result, error, log = run("auto", libs_present=False)
    print("KASUS 1: device=auto, pustaka CUDA tidak termuat")
    for ln in log.strip().splitlines():
        print("   ", ln)
    print("    model dimuat:", calls)
    if error is not None:
        failures.append(f"kasus 1 gagal: {error}")
    else:
        if calls != [("cpu", "int8")]:
            failures.append(f"kasus 1: model harus cpu/int8, dapat {calls}")
        if result["device"] != "cpu" or len(result["segments"]) != 2:
            failures.append("kasus 1: hasil transkripsi salah")
        print(f"    device di transcript.json: {result['device']}, "
              f"{len(result['segments'])} segmen")

    # 2. auto + pustaka ada tapi meledak saat iterasi -> fallback ke CPU saat itu juga.
    calls, result, error, log = run("auto", libs_present=True)
    print("\nKASUS 2: device=auto, GPU meledak saat iterasi (cuBLAS hilang setelah model dimuat)")
    for ln in log.strip().splitlines():
        print("   ", ln)
    print("    model dimuat:", calls)
    if error is not None:
        failures.append(f"kasus 2 gagal: {error}")
    else:
        if calls != [("cuda", "float16"), ("cpu", "int8")]:
            failures.append(f"kasus 2: harus cuda lalu cpu, dapat {calls}")
        if result["device"] != "cpu":
            failures.append("kasus 2: device hasil harus cpu")

    # 3. cuda dipaksa user -> TIDAK boleh fallback diam-diam, pesan harus jelas.
    calls, result, error, log = run("cuda", libs_present=True)
    print("\nKASUS 3: WHISPER_DEVICE=cuda dipaksa, GPU tidak bisa dipakai")
    print("    model dimuat:", calls)
    if error is None:
        failures.append("kasus 3: seharusnya error, bukan fallback diam-diam")
    elif calls != [("cuda", "float16")]:
        failures.append(f"kasus 3: tidak boleh memuat model cpu, dapat {calls}")
    else:
        for ln in str(error).splitlines()[:3]:
            print("   ", ln)
        for needle in ("WHISPER_DEVICE=cpu", "autoclip_colab.py", "libcublas.so.12"):
            if needle not in str(error):
                failures.append(f"kasus 3: pesan tidak menyebut '{needle}'")

    # 4. CPU biasa -> jalur normal tidak berubah.
    calls, result, error, log = run("cpu", libs_present=True)
    print("\nKASUS 4: device=cpu (jalur normal)")
    if error is not None:
        failures.append(f"kasus 4 gagal: {error}")
    if calls != [("cpu", "int8")]:
        failures.append(f"kasus 4: compute type harus int8 di CPU, dapat {calls}")
    else:
        print("    model dimuat:", calls)

    # 5. Galat non-CUDA harus tetap jadi TranscriptionError biasa.
    _, _, error, _ = run("cpu", libs_present=True, model_cls=BrokenModel)
    print("\nKASUS 5: galat non-CUDA ->", str(error)[:70] if error else "(tidak ada error!)")
    if error is None:
        failures.append("kasus 5: galat non-CUDA seharusnya jadi TranscriptionError")

    print()
    if failures:
        for f in failures:
            print("  GAGAL:", f)
        return 1
    print("Semua pemeriksaan fallback CUDA LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())