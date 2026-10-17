#!/usr/bin/env python3
"""Uji modul highlight terhadap mock OpenRouter: retry, backoff, parser, validator.

Jalankan: venv/bin/python tests/test_highlight.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import highlight  # noqa: E402

PORT = 8791
BASE = f"http://127.0.0.1:{PORT}/api/v1"
MODEL = "mock/test-model:free"
TRANSCRIPT = """[0.0 -> 3.9] Halo dunia
[27.5 -> 38.0] Contoh segmen
[60.0 -> 90.0] Segmen lain"""

results: list[tuple[str, bool, str]] = []


def start_mock(scenario: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "tests" / "mock_openrouter.py"),
         "--port", str(PORT), "--scenario", scenario],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)
    return proc


def run(scenario: str, expect_ok: bool, max_retries: int = 3) -> None:
    proc = start_mock(scenario)
    t0 = time.time()
    try:
        segs = highlight.select_highlights(
            api_key="dummy-test-key",
            base_url=BASE,
            model=MODEL,
            transcript_text=TRANSCRIPT,
            duration=120.0,
            max_clips=5,
            min_seconds=30,
            max_seconds=60,
            max_retries=max_retries,
            timeout=10,
        )
        elapsed = time.time() - t0
        if expect_ok:
            detail = (f"{len(segs)} segmen: "
                      + " | ".join(f"{s['start']}-{s['end']}s '{s['title']}'" for s in segs)
                      + f" | {elapsed:.1f}s")
            results.append((scenario, len(segs) == 2, detail))
        else:
            results.append((scenario, False, f"harusnya GAGAL tapi dapat {len(segs)} segmen"))
    except highlight.HighlightError as exc:
        elapsed = time.time() - t0
        if expect_ok:
            results.append((scenario, False, f"harusnya BERHASIL tapi: {exc}"))
        else:
            results.append((scenario, True, f"gagal seperti yang diharapkan ({elapsed:.1f}s)"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def main() -> int:
    print("=== uji highlight vs mock OpenRouter ===")
    run("good", True)
    run("fenced", True)
    run("trailing", True)
    run("truncated", True)
    run("dictwrap", True)
    run("garbage", False, max_retries=2)
    run("ratelimit", True, max_retries=3)  # 2x 429 lalu success

    print()
    failed = 0
    for name, ok, detail in results:
        print(f"[{'OK  ' if ok else 'GAGAL'}] {name:12} {detail}")
        if not ok:
            failed += 1
    print(f"\n{len(results) - failed}/{len(results)} skenario lulus")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())