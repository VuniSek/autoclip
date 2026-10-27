"""Uji aturan "model harus gratis" (problem.md P-010, P-022, P-030).

Aturan:
- model diterima kalau berakhiran ':free' ATAU termasuk router gratis OpenRouter
  (`openrouter/free`) -> berlaku untuk endpoint OpenRouter resmi;
- endpoint OpenAI-compatible milik pengguna (9router di localhost atau lewat
  ngrok/tunnel) memakai model apa adanya: tidak dipilih otomatis dan tidak
  ditambahi ':free'.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import autoclip_colab as colab  # noqa: E402
from src.config import (  # noqa: E402
    FREE_ROUTER_MODELS,
    ConfigError,
    is_openrouter,
    load_config,
    model_is_free,
)

GRATIS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openrouter/free",
    "OpenRouter/Free",
    "  openrouter/free  ",
    "qwen/qwen3-235b-a22b:free",
]
BERBAYAR = [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.0-flash-exp",
    "deepseek/deepseek-chat",
    "",
]
# Nama model yang lazim dipakai di 9router (bukan OpenRouter): tanpa ':free'.
MODEL_9ROUTER = [
    "combo/free-coding",
    "cc/claude-sonnet-4.5",
    "openai/gpt-5",
    "qwen3-coder",
]
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
CUSTOM_BASES = [
    "http://localhost:20128/v1",
    "http://127.0.0.1:20128/v1",
    "https://contoh-ngrok.ngrok-free.app/v1",
]
BASE_ENV = """OPENROUTER_API_KEY=dummy-test-key
OPENROUTER_MODEL={model}
OPENROUTER_BASE_URL={base_url}
"""


def load_with(model: str, base_url: str = OPENROUTER_BASE):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / ".env"
        path.write_text(
            BASE_ENV.format(model=model, base_url=base_url), encoding="utf-8"
        )
        return load_config(path)


def main() -> int:
    failures: list[str] = []
    print("=== Uji aturan model gratis (P-010/P-022/P-030) ===\n")

    print("[1] is_openrouter()")
    for base_url, expected in [
        (OPENROUTER_BASE, True),
        ("https://openrouter.ai/api/v1/", True),
        ("openrouter.ai/api/v1", True),
        ("http://localhost:20128/v1", False),
        ("https://contoh-ngrok.ngrok-free.app/v1", False),
        ("", False),
    ]:
        got = is_openrouter(base_url)
        ok = got == expected
        print(f"  {'OK ' if ok else 'GAGAL'} {base_url!r} -> {got} (harus {expected})")
        if not ok:
            failures.append(f"is_openrouter({base_url!r}) = {got}, harus {expected}")

    print("\n[2] model_is_free() tanpa base URL (perilaku lama, hanya cek nama)")
    for model in GRATIS:
        ok = model_is_free(model)
        print(f"  {'OK ' if ok else 'GAGAL'} {model!r} -> {ok}")
        if not ok:
            failures.append(f"model gratis ditolak: {model!r}")
    for model in BERBAYAR:
        ok = model_is_free(model)
        print(f"  {'OK ' if not ok else 'GAGAL'} {model!r} -> {ok} (harus False)")
        if ok:
            failures.append(f"model berbayar lolos: {model!r}")

    print("\n[3] load_config() di OpenRouter resmi: gratis diterima, berbayar ditolak")
    for model in GRATIS:
        try:
            cfg = load_with(model, OPENROUTER_BASE)
            print(f"  OK  {model!r} -> {cfg.openrouter_model}")
        except ConfigError as exc:
            failures.append(f"load_config menolak model gratis {model!r}: {exc}")
            print(f"  GAGAL {model!r} -> {exc}")
    for model in BERBAYAR:
        try:
            load_with(model, OPENROUTER_BASE)
            failures.append(f"load_config menerima model berbayar {model!r}")
            print(f"  GAGAL {model!r} -> diterima (seharusnya ditolak)")
        except ConfigError as exc:
            first = str(exc).splitlines()[0]
            print(f"  OK  {model!r} -> ditolak: {first}")
            if ":free" not in str(exc):
                failures.append("pesan penolakan tidak menjelaskan aturan ':free'")

    print("\n[4] load_config() di gateway sendiri (9router/ngrok): model apa adanya")
    for base_url in CUSTOM_BASES:
        for model in MODEL_9ROUTER:
            try:
                cfg = load_with(model, base_url)
            except ConfigError as exc:
                failures.append(
                    f"gateway {base_url} menolak model {model!r}: {exc}"
                )
                print(f"  GAGAL {base_url} {model!r} -> {exc}")
                continue
            same = cfg.openrouter_model == model
            print(f"  OK  {base_url} {model!r} -> dipakai apa adanya: {same}")
            if not same:
                failures.append(f"nama model diubah: {model!r} -> {cfg.openrouter_model!r}")

    print("\n[5] runner Colab konsisten dengan src/config.py")
    print(f"  FREE_ROUTER_MODELS = {sorted(FREE_ROUTER_MODELS)}")
    print(f"  COLAB_FREE_ROUTERS = {sorted(colab.COLAB_FREE_ROUTERS)}")
    if FREE_ROUTER_MODELS != colab.COLAB_FREE_ROUTERS:
        failures.append(
            f"daftar router gratis berbeda: {sorted(FREE_ROUTER_MODELS)} vs "
            f"{sorted(colab.COLAB_FREE_ROUTERS)}"
        )
    for base_url in [OPENROUTER_BASE, *CUSTOM_BASES, None]:
        for model in GRATIS + BERBAYAR + MODEL_9ROUTER:
            a, b = model_is_free(model, base_url), colab.colab_model_is_free(model, base_url)
            if a != b:
                failures.append(
                    f"keputusan berbeda untuk {model!r} @ {base_url!r}: config={a} colab={b}"
                )
    print(f"  {len(GRATIS) + len(BERBAYAR) + len(MODEL_9ROUTER)} model x 5 endpoint dicek")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan model gratis LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
