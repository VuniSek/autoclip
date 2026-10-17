#!/usr/bin/env python3
"""Mock lokal OpenRouter /chat/completions untuk pengujian (tanpa API key).

Server ini hanya untuk tes otomatis: menyimulasikan balasan model gratis yang
"berantakan" supaya retry/backoff/parser/validator bisa diuji.

Cara pakai:
    python tests/mock_openrouter.py --port 8765 --scenario good
    lalu jalankan AUTO CLIP dengan:
        OPENROUTER_BASE_URL=http://127.0.0.1:8765/api/v1
        OPENROUTER_API_KEY=dummy-test-key
        OPENROUTER_MODEL=mock/test-model:free

Skenario:
    good          JSON bersih
    fenced        dibungkus ```json
    trailing      ada kalimat penutup setelah array
    garbage       jawaban bukan JSON sama sekali
    ratelimit     429 pada 2 permintaan pertama, lalu good
    truncated     JSON terpotong (kurang kurung)
    dictwrap      dibungkus {"clips": [...]}
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"count": 0, "scenario": "good", "lock": threading.Lock()}

# Sengaja tidak saling tumpang tindih, supaya AUTO CLIP tidak membuang salah satunya.
SEGMENTS = [
    {
        "start": 0.0,
        "end": 38.0,
        "title": "Kenapa kita susah berhenti scrolling",
        "reason": "Hook pertanyaan relatable di detik pertama, topik utuh.",
    },
    {
        "start": 42.0,
        "end": 72.0,
        "title": "Rebuild dari nol karena menu rusak",
        "reason": "Klaim arsitektur, ada konflik dan pelajaran nyata.",
    },
]


def _build_response(scenario: str, n: int) -> str:
    if scenario == "good":
        return json.dumps(SEGMENTS, ensure_ascii=False)
    if scenario == "fenced":
        return "```json\n" + json.dumps(SEGMENTS, ensure_ascii=False) + "\n```"
    if scenario == "trailing":
        return (
            json.dumps(SEGMENTS, ensure_ascii=False)
            + "\n\nSemoga membantu! Silakan beri rating."
        )
    if scenario == "truncated":
        return json.dumps(SEGMENTS, ensure_ascii=False)[:-12]
    if scenario == "dictwrap":
        return json.dumps({"clips": SEGMENTS}, ensure_ascii=False)
    if scenario == "garbage":
        return (
            "Maaf, saya tidak dapat memenuhi permintaan itu karena saya adalah "
            "asisten yang membantu dan tidak dapat mengubah format jawaban."
        )
    if scenario == "ratelimit":
        if n <= 2:
            return "__RATELIMIT__"
        return json.dumps(SEGMENTS, ensure_ascii=False)
    return json.dumps(SEGMENTS, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: ANN002, ANN003
        print(f"[mock] {fmt % args}", flush=True)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}
        # Jangan pernah log Authorization header.
        auth = self.headers.get("Authorization", "")
        masked = f"{auth[:11]}...len={len(auth)}" if auth else "(tidak ada)"
        print(f"[mock] model={body.get('model')} auth={masked}", flush=True)

        with STATE["lock"]:
            STATE["count"] += 1
            n = STATE["count"]
            scenario = STATE["scenario"]

        content = _build_response(scenario, n)

        if content == "__RATELIMIT__":
            payload = json.dumps(
                {"error": {"code": 429, "message": "Rate limit exceeded"}}
            ).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Retry-After", "2")
            self.end_headers()
            self.wfile.write(payload)
            return

        payload = json.dumps(
            {
                "id": f"mock-{n}",
                "object": "chat.completion",
                "model": body.get("model", "mock"),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--scenario", default="good")
    args = ap.parse_args()
    STATE["scenario"] = args.scenario
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True
    print(f"[mock] berjalan di http://127.0.0.1:{args.port}/api/v1 "
          f"(skenario={args.scenario})", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())