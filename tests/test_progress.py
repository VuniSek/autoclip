"""Uji frekuensi baris progress unduhan (problem.md P-014).

Simulasi unduhan file besar (1,3 GB, event tiap 2 detik seperti pada P-013)
lalu hitung berapa baris progress yang keluar. Waktu disimulasikan supaya
tidak perlu menunggu sungguhan.
"""
import contextlib
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import downloader  # noqa: E402
from src.downloader import PROGRESS_INTERVAL, PROGRESS_STEP, make_progress_hook  # noqa: E402

TOTAL = 1_300_000_000
CHUNK = TOTAL // 100  # 1% per event


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def sleep(self, seconds):
        self.t += seconds


def run(every, step, events=100, total=TOTAL, chunk=None, per_event_seconds=2.0):
    """Jalankan hook dengan waktu palsu; kembalikan list baris yang tercetak."""
    clock = FakeClock()
    real_time = downloader.time.monotonic
    real_sleep = downloader.time.sleep
    downloader.time.monotonic = lambda: clock.t
    downloader.time.sleep = clock.sleep
    buf = io.StringIO()
    try:
        hook = make_progress_hook(every=every, step=step)
        with contextlib.redirect_stdout(buf):
            for i in range(events):
                got = min(total, (chunk or total // 100) * (i + 1))
                hook(
                    {
                        "status": "downloading",
                        "downloaded_bytes": got,
                        "total_bytes": total,
                        "speed": 7_000_000,
                        "eta": int((total - got) / 7_000_000),
                    }
                )
                clock.sleep(per_event_seconds)
    finally:
        downloader.time.monotonic = real_time
        downloader.time.sleep = real_sleep
    return [ln for ln in buf.getvalue().splitlines() if ln.strip()]


def main() -> int:
    print(f"default interval={PROGRESS_INTERVAL}s step={PROGRESS_STEP}%\n")
    failures = []

    cases = [(2.0, "lama (P-013)"), (PROGRESS_INTERVAL, "default"), (60.0, "sangat jarang")]
    counts = {}
    for every, label in cases:
        lines = run(every, PROGRESS_STEP)
        counts[every] = len(lines)
        print(f"every={every:>5}s ({label:<13}) -> {len(lines):>3} baris")
        for ln in lines[:6]:
            print("   ", ln)
        print()

    # Default harus jauh lebih jarang dari interval lama, tapi tetap > 1 baris.
    if counts[PROGRESS_INTERVAL] >= counts[2.0]:
        failures.append("default tidak lebih jarang dari interval lama")
    if counts[PROGRESS_INTERVAL] < 3:
        failures.append("default terlalu jarang (kurang dari 3 baris)")

    # Unduhan kecil harus tetap menampilkan baris (jangan sampai diam total):
    # 8 event untuk 8 MB -> 12,5% per event, jadi gate 10% selalu memicu.
    short = run(PROGRESS_INTERVAL, PROGRESS_STEP, events=8, total=8_000_000,
                chunk=8_000_000 // 8)
    print(f"file kecil (8 event, 8 MB) -> {len(short)} baris:")
    for ln in short:
        print("   ", ln)
    if len(short) < 3:
        failures.append("unduhan kecil tidak menampilkan cukup progress")

    # every=0 -> hanya berbasis langkah persentase, tidak bergantung waktu.
    zero = run(0.0, PROGRESS_STEP, events=100)
    print(f"\nevery=0 (hanya tiap 10%) -> {len(zero)} baris")
    if not (5 <= len(zero) <= 12):
        failures.append(f"every=0 harus ~10 baris (tiap 10%), dapat {len(zero)}")

    # Tanpa total_bytes: tidak ada persentase, harus tetap aman (tidak crash).
    clock = FakeClock()
    real_monotonic = downloader.time.monotonic
    downloader.time.monotonic = lambda: clock.t
    buf = io.StringIO()
    try:
        hook = make_progress_hook()
        with contextlib.redirect_stdout(buf):
            for _ in range(3):
                hook({"status": "downloading", "downloaded_bytes": 1_000_000, "speed": 100_000})
                clock.sleep(PROGRESS_INTERVAL + 0.1)
    finally:
        downloader.time.monotonic = real_monotonic
    no_total = buf.getvalue().splitlines()
    print(f"tanpa total_bytes -> {len(no_total)} baris: {no_total[0] if no_total else '(tidak ada)'}")
    if not no_total:
        failures.append("kasus tanpa total_bytes tidak menghasilkan baris")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan progress LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())