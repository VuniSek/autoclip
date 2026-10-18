"""Uji diagnostik CUDA di Colab runner (problem.md P-019).

Tidak butuh GPU: `cuda_diagnostics()`/`cuda_ready()`/`explain_cuda_failure()`
dipanggil dengan dict hasil probe yang disimulasikan.
"""
from __future__ import annotations

import os
import sys
import tempfile
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
    if "libcublas.so.12" not in text or "cannot open shared object file" not in text:
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

    # 7. `setup_cuda_libs(install=...)` (problem.md P-020): GPU tetap diperiksa
    #    walau --skip-install, tapi pip tidak boleh jalan kalau install=False.
    print("\n[7] setup_cuda_libs: GPU dicek walau --skip-install")
    asli = {
        "gpu_name": colab.gpu_name,
        "cuda_diagnostics": colab.cuda_diagnostics,
        "install_cuda_libs": colab.install_cuda_libs,
        "have": colab.have,
        "ld_path": os.environ.get("LD_LIBRARY_PATH", ""),
    }

    def bersihkan() -> None:
        os.environ["LD_LIBRARY_PATH"] = asli["ld_path"]
        for nama, fun in (
            ("gpu_name", asli["gpu_name"]),
            ("cuda_diagnostics", asli["cuda_diagnostics"]),
            ("install_cuda_libs", asli["install_cuda_libs"]),
            ("have", asli["have"]),
        ):
            setattr(colab, nama, fun)

    dipanggil: list[bool] = []

    def install_palsu() -> bool:
        dipanggil.append(True)
        return True

    try:
        colab.gpu_name = lambda: "Tesla T4, 15360 MiB (palsu)"
        colab.have = lambda cmd: False  # jangan ldconfig di mesin uji

        # a) pustaka sudah siap -> GPU dipakai tanpa memanggil pip sama sekali.
        colab.cuda_diagnostics = lambda: clone(SEHAT)
        dipanggil.clear()
        siap = colab.setup_cuda_libs(install=False)
        print(f"  pustaka siap, install=False -> gpu={siap} pip={len(dipanggil)} kali")
        if not siap:
            failures.append("pustaka siap + install=False harus tetap memakai GPU")
        if dipanggil:
            failures.append("pip tidak boleh jalan saat install=False")

        # b) pustaka belum siap + install=False -> CPU, tanpa pip, dengan alasan.
        colab.cuda_diagnostics = lambda: clone(SEHAT, device_count=0)
        dipanggil.clear()
        siap = colab.setup_cuda_libs(install=False)
        print(f"  pustaka belum siap, install=False -> gpu={siap} pip={len(dipanggil)} kali")
        if siap:
            failures.append("tanpa pustaka CUDA tidak boleh diklaim GPU siap")
        if dipanggil:
            failures.append("pip tidak boleh jalan saat install=False")

        # c) install=True tetap memasang paket seperti sebelumnya.
        colab.cuda_diagnostics = lambda: clone(SEHAT, device_count=0)
        colab.install_cuda_libs = install_palsu
        dipanggil.clear()
        colab.setup_cuda_libs(install=True)
        print(f"  pustaka belum siap, install=True -> pip={len(dipanggil)} kali")
        if not dipanggil:
            failures.append("install=True harus memasang paket CUDA")
    finally:
        bersihkan()

    # 8. Nilai status baru dari probe (P-021): file ditemukan -> dimuat paksa; file
 #    tidak ada -> dilaporkan sebagai TIDAK ADA + versi lain yang terpasang.
    print("\n[8] status 'loaded:' / 'gagal:' / TIDAK ADA")
    ketemu = clone(
        SEHAT,
        libs={
            "libcublas.so.12": "loaded:/usr/lib/python3/nvidia/cublas/lib/libcublas.so.12",
            "libcudnn.so.9": "ok",
            "libcudart.so.12": "loaded:/usr/lib/python3/nvidia/cuda_runtime/lib/libcudart.so.12",
            "libcublasLt.so.12": "loaded:/usr/lib/python3/nvidia/cublas/lib/libcublasLt.so.12",
        },
        found={
            "libcublas.so.12": "/usr/lib/python3/nvidia/cublas/lib/libcublas.so.12",
            "libcudart.so.12": "/usr/lib/python3/nvidia/cuda_runtime/lib/libcudart.so.12",
            "libcublasLt.so.12": "/usr/lib/python3/nvidia/cublas/lib/libcublasLt.so.12",
        },
    )
    print(f"  semua termuat -> cuda_ready={colab.cuda_ready(ketemu)} "
          f"missing={colab.missing_sonames(ketemu)}")
    if not colab.cuda_ready(ketemu):
        failures.append("status 'loaded:<path>' harus dihitung termuat")
    if colab.missing_sonames(ketemu):
        failures.append("semua pustaka ada -> tidak boleh ada yang 'hilang'")
    ada_di_path = clone(
        ketemu,
        libs=dict(ketemu["libs"], **{"libcudnn.so.9": "gagal:/x/libcudnn.so.9 -> error"}),
    )
    teks_ok = colab.explain_cuda_failure(ada_di_path, "T4")
    if "gagal:" not in teks_ok or "/x/libcudnn.so.9" not in teks_ok:
        failures.append("status 'gagal:<path> -> err' harus ditampilkan lengkap")
    if "dimuat lewat path absolut" not in colab.explain_cuda_failure(
        clone(ada_di_path, libs=dict(ketemu["libs"])), "T4"
    ):
        failures.append("daftar pustaka yang dimuat lewat path absolut tidak ditampilkan")

    tidak_ada = clone(
        SEHAT,
        libs={lib: f"{lib}: cannot open shared object file: No such file or directory"
              for lib in colab.CUDA_LIBS + colab.CUDA_OPTIONAL_LIBS},
        found={},
        missing={"libcublas.so.12": ["libcublas.so.13", "libcublas.so.13.0.87"]},
        ld_path="/a:/b",
    )
    teks = colab.explain_cuda_failure(tidak_ada, "Tesla T4, 15360 MiB")
    print("  penjelasan (baris(libcublas):")
    for line in [ln for ln in teks.splitlines() if "libcublas" in ln or "perbaiki" in ln][:4]:
        print("   ", line)
    if not colab.lib_loaded("ok") or not colab.lib_loaded("loaded:/x"):
        failures.append("lib_loaded harus menerima 'ok' dan 'loaded:'")
    if colab.lib_loaded("gagal:/x -> err") or colab.lib_loaded(""):
        failures.append("lib_loaded harus menolak 'gagal:' dan string kosong")
    if colab.missing_sonames(tidak_ada) != list(colab.CUDA_LIBS):
        failures.append(f"missing_sonames salah: {colab.missing_sonames(tidak_ada)}")
    if "libcublas.so.13" not in teks:
        failures.append("penjelasan tidak menyebut versi lain yang terpasang (CUDA 13)")
    if "--force-reinstall" not in teks:
        failures.append("penjelasan tidak memberi perintah --force-reinstall")

    # 9. nvidia_lib_dirs() memindai SELURUH sys.path, bukan hanya nvidia.__file__.
    print("\n[9] nvidia_lib_dirs() memindai semua sys.path")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "nvidia" / "cublas" / "lib").mkdir(parents=True)
        (root / "nvidia" / "cu12").mkdir(parents=True)
        asli_path = sys.path[:]
        asli_ld = os.environ.get("LD_LIBRARY_PATH", "")
        try:
            sys.path.insert(0, str(root))
            dirs = [str(d) for d in colab.nvidia_lib_dirs()]
            print(f"  folder terdeteksi: {len(dirs)}")
            if str(root / "nvidia" / "cublas" / "lib") not in dirs:
                failures.append("folder nvidia/cublas/lib dari sys.path tidak terpindai")
            if str(root / "nvidia" / "cu12") not in dirs:
                failures.append("folder nvidia/cu12 dari sys.path tidak terpindai")
        finally:
            sys.path[:] = asli_path
            os.environ["LD_LIBRARY_PATH"] = asli_ld
    if colab.cuda_ready(SEHAT) is not True:
        failures.append("regresi: kondisi sehat harus tetap siap")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan diagnostik CUDA LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())