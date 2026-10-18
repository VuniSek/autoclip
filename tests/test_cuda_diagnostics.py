"""Uji diagnostik CUDA di Colab runner (problem.md P-019).

Tidak butuh GPU: `cuda_diagnostics()`/`cuda_ready()`/`explain_cuda_failure()`
dipanggil dengan dict hasil probe yang disimulasikan.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import autoclip_colab as colab  # noqa: E402

SEHAT = {
    "python": "/usr/bin/python3",
    "ld_path": "/content/autoclip/site-packages/nvidia/cublas/lib",
    "device_count": 1,
    "ctranslate2": "4.8.3",
    "nvidia_dir": "/content/autoclip/site-packages/nvidia",
    "libs": {
        "libcublas.so.12": "ok",
        "libcudnn.so.9": "ok",
        "libcudart.so.12": "ok",
        "libcublasLt.so.12": "ok",
    },
    "errors": {},
}


def clone(diag: dict, **changes) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in diag.items()}
    out.update(changes)
    return out


def main() -> int:
    failures: list[str] = []
    print("=== Uji diagnostik CUDA (P-019) ===\n")

    # 1. Kondisi sehat: GPU + semua pustaka termuat -> siap dipakai.
    print("[1] kondisi sehat")
    print(f"  cuda_ready={colab.cuda_ready(SEHAT)} device_count={SEHAT['device_count']}")
    if not colab.cuda_ready(SEHAT):
        failures.append("kondisi sehat harus dianggap siap")

    # 2. Pustaka belum termuat (kejadian di P-016/P-019) -> belum siap.
    print("\n[2] pustaka CUDA belum termuat")
    no_libs = clone(
        SEHAT,
        libs={
            "libcublas.so.12": "cannot open shared object file: No such file or directory",
            "libcudnn.so.9": "cannot open shared object file: No such file or directory",
            "libcudart.so.12": "ok",
            "libcublasLt.so.12": "ok",
        },
    )
    print(f"  cuda_ready={colab.cuda_ready(no_libs)}")
    text = colab.explain_cuda_failure(no_libs, "Tesla T4, 15360 MiB")
    print("  penjelasan:")
    for line in text.splitlines():
        print("   ", line)
    if colab.cuda_ready(no_libs):
        failures.append("pustaka hilang harus dianggap belum siap")
    if "libcublas.so.12: cannot open shared object file" not in text:
        failures.append("penjelasan tidak menyebut pustaka yang gagal + alasannya")
    if "Tesla T4" not in text:
        failures.append("penjelasan tidak menyebut GPU yang terdeteksi")

    # 3. Pustaka ada tapi ctranslate2 melihat 0 GPU -> sebab driver/runtime.
    print("\n[3] ctranslate2 melihat 0 GPU")
    nolap = clone(SEHAT, device_count=0)
    text3 = colab.explain_cuda_failure(nolap, "Tesla T4, 15360 MiB")
    print("  penjelasan:")
    for line in text3.splitlines():
        print("   ", line)
    if colab.cuda_ready(nolap):
        failures.append("device_count=0 harus dianggap belum siap")
    if "0 GPU" not in text3 or "nvidia-smi" not in text3:
        failures.append("penjelasan device_count=0 tidak kontraskan dengan nvidia-smi")
    if "nvidia-cuda-runtime-cu12" not in text3:
        failures.append("penjelasan device_count=0 tidak memberi perintah perbaikan")

    # 4. Probe gagal total -> tetap harus memberi pesan, bukan crash.
    print("\n[4] probe gagal total")
    rusak = {
        "python": "/usr/bin/python3",
        "ld_path": "",
        "libs": {},
        "errors": {"probe": "ModuleNotFoundError: No module named 'ctranslate2'"},
    }
    text4 = colab.explain_cuda_failure(rusak, "tidak ada")
    print(f"  cuda_ready={colab.cuda_ready(rusak)}")
    print("  penjelasan:", text4.splitlines()[-1])
    if colab.cuda_ready(rusak):
        failures.append("probe rusak harus dianggap belum siap")
    if "ctranslate2" not in text4:
        failures.append("penjelasan probe rusak tidak menyebut ctranslate2")

    # 5. Paket nvidia tidak terlihat -> curigai pip vs interpreter beda.
    print("\n[5] paket pip nvidia tidak terlihat")
    tanpa_nvidia = clone(SEHAT, device_count=0)
    tanpa_nvidia.pop("nvidia_dir", None)
    text5 = colab.explain_cuda_failure(tanpa_nvidia, "Tesla T4")
    print("  penjelasan:", text5.splitlines()[-2])
    if "tidak terlihat di interpreter" not in text5:
        failures.append("paket nvidia yang hilang tidak dilaporkan")

    # 6. Probe nyata di mesin ini tidak boleh membuat program jatuh.
    print("\n[6] cuda_diagnostics() nyata di mesin lokal")
    diag = colab.cuda_diagnostics()
    print(f"  python={diag.get('python')} device_count={diag.get('device_count')} "
          f"siap={colab.cuda_ready(diag)}")
    if "libs" not in diag or "python" not in diag:
        failures.append("hasil probe nyata tidak lengkap")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan diagnostik CUDA LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())