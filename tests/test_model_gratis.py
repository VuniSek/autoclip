"""Uji aturan "model harus gratis" (problem.md P-010 dan P-022).

Aturan: model diterima kalau berakhiran ':free' ATAU termasuk router gratis
OpenRouter (`openrouter/free`) yang hanya meneruskan ke model gratis.
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

BASE_ENV = """OPENROUTER_API_KEY=dummy-test-key
OPENROUTER_MODEL={model}
OPENROUTER_BASE_URL=http://127.0.0.1:9/api/v1
"""


def load_with(model: str):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / ".env"
        path.write_text(BASE_ENV.format(model=model), encoding="utf-8")
        return load_config(path)


def main() -> int:
    failures: list[str] = []
    print("=== Uji aturan model gratis (P-010/P-022) ===\n")

    print("[1] model_is_free()")
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

    print("\n[2] load_config() menerima gratis, menolak berbayar")
    for model in GRATIS:
        try:
            cfg = load_with(model)
            print(f"  OK  {model!r} -> {cfg.openrouter_model}")
        except ConfigError as exc:
            failures.append(f"load_config menolak model gratis {model!r}: {exc}")
            print(f"  GAGAL {model!r} -> {exc}")
    for model in BERBAYAR:
        try:
            load_with(model)
            failures.append(f"load_config menerima model berbayar {model!r}")
            print(f"  GAGAL {model!r} -> diterima (seharusnya ditolak)")
        except ConfigError as exc:
            first = str(exc).splitlines()[0]
            print(f"  OK  {model!r} -> ditolak: {first}")
            if ":free" not in str(exc):
                failures.append("pesan penolakan tidak menjelaskan aturan ':free'")

    print("\n[3] runner Colab konsisten dengan src/config.py")
    print(f"  FREE_ROUTER_MODELS = {sorted(FREE_ROUTER_MODELS)}")
    print(f"  COLAB_FREE_ROUTERS = {sorted(colab.COLAB_FREE_ROUTERS)}")
    if FREE_ROUTER_MODELS != colab.COLAB_FREE_ROUTERS:
        failures.append(
            f"daftar router gratis berbeda: {sorted(FREE_ROUTER_MODELS)} vs "
            f"{sorted(colab.COLAB_FREE_ROUTERS)}"
        )
    for model in GRATIS + BERBAYAR:
        a, b = model_is_free(model), colab.colab_model_is_free(model)
        if a != b:
            failures.append(f"keputusan berbeda untuk {model!r}: config={a} colab={b}")
    print(f"  {len(GRATIS) + len(BERBAYAR)} model dicek, keputusan sama")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan model gratis LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())