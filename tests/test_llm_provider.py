#!/usr/bin/env python3
"""Uji provider OpenAI-compatible (9router/ngrok) tanpa jaringan.

Jalankan: venv/bin/python tests/test_llm_provider.py

Yang diuji (problem.md P-030):
- base URL dipakai apa adanya: `{base_url}/chat/completions`;
- nama model TIDAK diubah (tidak ditambah ':free', tidak dipilih otomatis);
- header atribusi OpenRouter tidak dikirim ke gateway sendiri;
- timeout diambil dari OPENROUTER_TIMEOUT;
- respons gateway yang membalas HTTP 200 + `{"error": ...}` ditangani jelas;
- content kosong / choices hilang -> HighlightError, bukan KeyError.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import highlight  # noqa: E402
from src.config import load_config  # noqa: E402

TRANSCRIPT = """[0.0 -> 10.0] pembuka
[10.0 -> 40.0] isi topik
[40.0 -> 70.0] penutup"""
CLIPS_JSON = json.dumps(
    [{"start": 10.0, "end": 40.0, "title": "Topik", "reason": "hook kuat"}]
)

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'OK ' if cond else 'GAGAL'} {name}" + (f" -> {detail}" if detail else ""))
    if not cond:
        failures.append(name if not detail else f"{name}: {detail}")


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, text: str | None = None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        if self._payload is None:
            raise ValueError("No JSON object could be decoded")
        return self._payload


class FakeRequests:
    """Pengganti modul requests: mencatat permintaan, membalas sesuai daftar."""

    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None):  # noqa: A002
        self.calls.append(
            {"url": url, "json": json, "headers": headers or {}, "timeout": timeout}
        )
        if not self.responses:
            raise AssertionError("FakeRequests: tidak ada respons tersisa")
        return self.responses.pop(0)


def with_fake_requests(responses: list[FakeResponse], fn):
    """Jalankan fn dengan highlight.requests diganti FakeRequests."""
    fake = FakeRequests(responses)
    original = highlight.requests
    highlight.requests = fake
    try:
        return fn(fake)
    finally:
        highlight.requests = original


def call_custom(fake, *, model="combo/free-coding", timeout=99, max_retries=1):
    return highlight.select_highlights(
        api_key="key-9router-rahasia",
        base_url="http://localhost:20128/v1",
        model=model,
        transcript_text=TRANSCRIPT,
        duration=70.0,
        max_clips=1,
        min_seconds=10,
        max_seconds=60,
        language="id",
        max_retries=max_retries,
        timeout=timeout,
    )


def main() -> int:
    print("=== Uji provider OpenAI-compatible / 9router (P-030) ===\n")

    print("[1] endpoint_label()")
    for base_url, expected in [
        ("https://openrouter.ai/api/v1", "OpenRouter"),
        ("http://localhost:20128/v1", "localhost"),
        ("https://contoh.ngrok-free.app/v1", "contoh.ngrok-free.app"),
        ("", "endpoint LLM"),
    ]:
        got = highlight.endpoint_label(base_url)
        check(f"{base_url!r}", got == expected, f"{got!r} (harus {expected!r})")

    print("\n[2] permintaan ke 9router: URL, model apa adanya, header, timeout")
    clips, calls = with_fake_requests(
        [FakeResponse(200, {"choices": [{"message": {"content": CLIPS_JSON}}]})],
        lambda fake: (call_custom(fake), fake.calls)[0:2],
    )
    call = calls[0]
    check("URL = base_url + /chat/completions",
          call["url"] == "http://localhost:20128/v1/chat/completions", call["url"])
    check("model tidak diubah", call["json"]["model"] == "combo/free-coding",
          call["json"]["model"])
    check("timeout dari parameter", call["timeout"] == 99, str(call["timeout"]))
    check("Authorization bearer", call["headers"].get("Authorization")
          == "Bearer key-9router-rahasia")
    check("tanpa header OpenRouter", "HTTP-Referer" not in call["headers"]
          and "X-Title" not in call["headers"])
    check("segmen tervalidasi", len(clips) == 1 and clips[0]["start"] == 10.0,
          str(clips))
    body = json.dumps(call["json"])
    check("API key tidak masuk body", "key-9router-rahasia" not in body)

    print("\n[3] OpenRouter resmi tetap memakai header atribusi")
    _, or_calls = with_fake_requests(
        [FakeResponse(200, {"choices": [{"message": {"content": CLIPS_JSON}}]})],
        lambda fake: (
            highlight.select_highlights(
                api_key="sk-or-dummy",
                base_url="https://openrouter.ai/api/v1",
                model="google/gemini-2.0-flash-exp:free",
                transcript_text=TRANSCRIPT,
                duration=70.0,
                max_clips=1,
                min_seconds=10,
                max_seconds=60,
                max_retries=1,
            ),
            fake.calls,
        )[0:2],
    )
    check("HTTP-Referer dikirim", "HTTP-Referer" in or_calls[0]["headers"])
    check("X-Title dikirim", "X-Title" in or_calls[0]["headers"])

    print("\n[4] HTTP 200 + {\"error\": ...} dari gateway")
    def make_error():
        try:
            highlight._call_once(
                "key-9router-rahasia", "http://localhost:20128/v1", "combo/x",
                "prompt", 30,
            )
            return None
        except highlight.HighlightError as exc:
            return str(exc)

    msg = with_fake_requests(
        [FakeResponse(200, {"error": {"message": "No credentials for provider"}})],
        lambda fake: make_error(),
    )
    check("HighlightError, bukan KeyError", msg is not None)
    check("menyebut host endpoint", bool(msg) and "localhost" in msg, msg or "")
    check("menyebut pesan gateway", bool(msg) and "No credentials" in msg, msg or "")
    check("API key disensor", bool(msg) and "key-9router-rahasia" not in msg, msg or "")

    print("\n[5] respons aneh: content kosong / choices hilang / bukan JSON")
    empty = with_fake_requests(
        [FakeResponse(200, {"choices": [{"message": {"content": "   "}}]})],
        lambda fake: make_error(),
    )
    check("content kosong -> pesan jelas", bool(empty) and "kosong" in empty, empty or "")
    missing = with_fake_requests(
        [FakeResponse(200, {"choices": []})], lambda fake: make_error()
    )
    check("choices kosong -> pesan jelas", bool(missing) and "choices" in missing,
          missing or "")
    notjson = with_fake_requests(
        [FakeResponse(200, None, text="<html>ngrok warning</html>")],
        lambda fake: make_error(),
    )
    check("bukan JSON -> pesan jelas", bool(notjson) and "bukan JSON" in notjson,
          notjson or "")

    print("\n[6] HTTP error gateway menyebut host, tanpa membocorkan key")
    try:
        with_fake_requests(
            [FakeResponse(401, {"error": "unauthorized"},
                          text='{"error":"unauthorized"}')],
            lambda fake: highlight._call_once(
                "key-9router-rahasia", "http://localhost:20128/v1", "combo/x",
                "prompt", 30,
            ),
        )
        check("HTTP 401 -> HighlightError", False, "tidak melempar error")
    except highlight.HighlightError as exc:
        text = str(exc)
        check("HTTP 401 -> HighlightError", True)
        check("menyebut host", "localhost" in text, text)
        check("API key tidak bocor", "key-9router-rahasia" not in text, text)

    print("\n[7] config: OPENROUTER_TIMEOUT + base URL 9router diterima")
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / ".env"
        path.write_text(
            "OPENROUTER_API_KEY=key-9router-rahasia\n"
            "OPENROUTER_MODEL=combo/free-coding\n"
            "OPENROUTER_BASE_URL=http://localhost:20128/v1\n"
            "OPENROUTER_TIMEOUT=300\n",
            encoding="utf-8",
        )
        cfg = load_config(path)
    check("base URL disimpan", cfg.openrouter_base_url == "http://localhost:20128/v1",
          cfg.openrouter_base_url)
    check("model tidak diubah", cfg.openrouter_model == "combo/free-coding",
          cfg.openrouter_model)
    check("timeout dibaca", cfg.llm_timeout == 300, str(cfg.llm_timeout))

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan provider LLM LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
