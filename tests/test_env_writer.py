"""Uji penulisan `.env` di runner Colab (problem.md P-023).

Tidak ada jaringan/Colab yang dibutuhkan: cukup fungsi `resolve_env()` dengan
argumen tiruan dan folder sementara.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import autoclip_colab as colab  # noqa: E402


def buat_args(**kwargs) -> argparse.Namespace:
    dasar = dict(
        env_file=None,
        model=None,
        api_key="dummy-test-key",
        whisper_model=None,
        face_tracking=False,
        no_face_tracking=False,
        allow_prompt=False,
    )
    dasar.update(kwargs)
    return argparse.Namespace(**dasar)


ENV_AWAL = """OPENROUTER_API_KEY=dummy-test-key
OPENROUTER_MODEL=google/gemma-2.0-flash-exp:free
MAX_SOURCE_HEIGHT=720
DOWNLOAD_PROGRESS_SECONDS=30
YT_COOKIES_FILE=/tmp/cookies.txt
MY_CUSTOM_KEY=jangan-hilang
"""


def main() -> int:
    failures: list[str] = []
    print("=== Uji penulisan .env (P-023) ===\n")

    print("[1] kunci milik pengguna tidak boleh hilang")
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        (project / ".env").write_text(ENV_AWAL, encoding="utf-8")
        path = colab.resolve_env(project, buat_args(), gpu=True)
        teks = path.read_text(encoding="utf-8")
        isi = dict(
            (k.strip(), v.strip())
            for k, _, v in (ln.partition("=") for ln in teks.splitlines() if ln.strip() and not ln.startswith("#"))
        )
        for kunci, diharapkan in (
            ("MAX_SOURCE_HEIGHT", "720"),
            ("DOWNLOAD_PROGRESS_SECONDS", "30"),
            ("YT_COOKIES_FILE", "/tmp/cookies.txt"),
            ("MY_CUSTOM_KEY", "jangan-hilang"),
        ):
            didapat = isi.get(kunci)
            print(f"  {kunci:<26} {didapat!r} (harusnya {diharapkan!r})")
            if didapat != diharapkan:
                failures.append(f"{kunci} berubah/hilang: {didapat!r} != {diharapkan!r}")
        if "MAX_SOURCE_HEIGHT" not in teks:
            failures.append("MAX_SOURCE_HEIGHT tidak tertulis sama sekali")
        # device mengikuti GPU
        if isi.get("WHISPER_DEVICE") != "cuda":
            failures.append(f"device harus cuda saat gpu=True, dapat {isi.get('WHISPER_DEVICE')}")
        if isi.get("WHISPER_COMPUTE_TYPE") != "float16":
            failures.append("compute harus float16 saat gpu=True")

    print("\n[2] semua kunci src/config.py ada di ENV_ORDER")
    from src import config as cfgmod  # noqa: E402

    field_config = {
        "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "OPENROUTER_BASE_URL",
        "WHISPER_MODEL", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE",
        "CLIP_MIN_SECONDS", "CLIP_MAX_SECONDS", "MAX_CLIPS", "LANGUAGE",
        "FACE_TRACKING", "MAX_SOURCE_HEIGHT", "DOWNLOAD_PROGRESS_SECONDS",
        "YT_COOKIES_FILE",
    }
    kurang = sorted(field_config - set(colab.ENV_ORDER))
    print(f"  kunci config={len(field_config)} ENV_ORDER={len(colab.ENV_ORDER)} kurang={kurang}")
    if kurang:
        failures.append(f"kunci tidak ada di ENV_ORDER: {kurang}")

    print("\n[3] GPU tidak dipakai -> device=cpu, compute=int8")
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        (project / ".env").write_text(ENV_AWAL, encoding="utf-8")
        path = colab.resolve_env(project, buat_args(), gpu=False)
        isi = dict(
            (k.strip(), v.strip())
            for k, _, v in (ln.partition("=") for ln in path.read_text(encoding="utf-8").splitlines()
                            if ln.strip() and not ln.startswith("#"))
        )
        print(f"  device={isi.get('WHISPER_DEVICE')} compute={isi.get('WHISPER_COMPUTE_TYPE')}")
        if isi.get("WHISPER_DEVICE") != "cpu":
            failures.append("device harus cpu saat gpu=False")

    print("\n[4] model router gratis diterima")
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        (project / ".env").write_text(ENV_AWAL, encoding="utf-8")
        path = colab.resolve_env(project, buat_args(model="openrouter/free"), gpu=True)
        isi = dict(
            (k.strip(), v.strip())
            for k, _, v in (ln.partition("=") for ln in path.read_text(encoding="utf-8").splitlines()
                            if ln.strip() and not ln.startswith("#"))
        )
        print(f"  model={isi.get('OPENROUTER_MODEL')}")
        if isi.get("OPENROUTER_MODEL") != "openrouter/free":
            failures.append("model router gratis tidak tertulis apa adanya")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan penulisan .env LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())