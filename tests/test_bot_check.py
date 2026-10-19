"""Uji penanganan verifikasi bot YouTube (problem.md P-016).

yt-dlp dipalsukan supaya tidak ada request ke internet. Skenario:
  1. Deteksi penanda pesan bot check.
  2. Bot check -> percobaan ulang dengan player client tanpa login -> berhasil.
  3. Bot check terus -> BotCheckError dengan petunjuk yang bisa dilakukan.
  4. Cookie sudah dikirim -> tidak ada percobaan ulang yang sia-sia.
  5. Galat biasa (video privat) -> DownloadError, bukan BotCheckError.
  6. Validasi file cookies + opsi extractor_args.
"""
from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import downloader  # noqa: E402
from src.downloader import BotCheckError, DownloadError  # noqa: E402

BOT_MSG = (
    "ERROR: [youtube] wDKyVtbdEsc: Sign in to confirm you're not a bot. "
    "Use --cookies-from-browser or --cookies for the authentication."
)
PRIVATE_MSG = "ERROR: [youtube] abc123: Private video. Sign in if you've been granted access"


def install_fake_yt_dlp(script: list) -> list[dict]:
    """Pasang modul yt_dlp palsu. `script` = perilaku tiap percobaan.

    Entri skrip: Exception (dilempar) atau dict info sukses.
    """
    calls: list[dict] = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts
            calls.append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def extract_info(self, url, download=True):
            step = len(calls) - 1
            if step >= len(script):
                raise RuntimeError("fake yt-dlp dipanggil lebih dari skrip yang disediakan")
            behaviour = script[step]
            if isinstance(behaviour, BaseException):
                raise behaviour
            return behaviour

        def prepare_filename(self, info):
            return info["_filename"]

    module = types.ModuleType("yt_dlp")
    module.YoutubeDL = FakeYDL  # type: ignore[attr-defined]
    sys.modules["yt_dlp"] = module
    return calls


def ok_info(workdir: Path, title: str = "Video Uji", duration: float = 125.0) -> dict:
    return {
        "title": title,
        "duration": duration,
        "uploader": "Uji",
        "_filename": str(workdir / "source.mp4"),
    }


def make_video(workdir: Path) -> None:
    (workdir / "source.mp4").write_bytes(b"\x00" * 2048)


def run_download(workdir: Path, script: list, **kwargs) -> tuple[Path | None, dict | None, list[dict], str]:
    calls = install_fake_yt_dlp(script)
    make_video(workdir)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            path, meta = downloader.download(
                "https://www.youtube.com/watch?v=wDKyVtbdEsc", workdir=workdir, **kwargs
            )
        return path, meta, calls, buf.getvalue()
    finally:
        sys.modules.pop("yt_dlp", None)


def case_markers() -> list[str]:
    failures = []
    positives = [
        BOT_MSG,
        "ERROR: [youtube] xyz: Sign in to confirm you’re not a bot",
        "Failed to extract any player response",
    ]
    negatives = [
        "ERROR: [youtube] abc: Private video",
        "HTTP Error 429: Too Many Requests",
        "",
    ]
    for msg in positives:
        if not downloader.looks_like_bot_check(msg):
            failures.append(f"tidak terdeteksi sebagai bot check: {msg[:60]}")
    for msg in negatives:
        if downloader.looks_like_bot_check(msg):
            failures.append(f"terdeteksi bot check padahal bukan: {msg[:60]}")
    print(f"  penanda pesan: {len(positives)} positif / {len(negatives)} negatif -> "
          f"{'lulus' if not failures else 'GAGAL'}")
    return failures


def main() -> int:
    failures: list[str] = []
    print("=== Uji penanganan verifikasi bot YouTube (P-016) ===\n")

    print("[1] Deteksi penanda pesan")
    failures += case_markers()

    print("\n[2] Bot check -> retry per player client -> berhasil")
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        script = [RuntimeError(BOT_MSG), ok_info(workdir, title="Big Buck Bunny")]
        path, meta, calls, out = run_download(workdir, script)
        print(f"  percobaan={len(calls)} opts[1]={calls[1].get('extractor_args')}")
        print(f"  judul={meta['title'] if meta else None} file={Path(path).name if path else None}")
        print("  log retry:", [ln for ln in out.splitlines() if "player client" in ln][:2])
        if len(calls) != 2:
            failures.append(f"harus 2 percobaan (default + 1 client), dapat {len(calls)}")
        # Tiap client dicoba SATU-SATU (bukan tv,ios digabung) - P-024
        if calls[1].get("extractor_args") != {"youtube": {"player_client": ["player_client=tv"]}}:
            failures.append(f"extractor_args retry salah: {calls[1].get('extractor_args')}")
        if not meta or meta["title"] != "Big Buck Bunny":
            failures.append("unduhan sukses tidak mengembalikan metadata judul")

    print("\n[3] Bot check terus-menerus -> BotCheckError + petunjuk")
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        # 1 percobaan default + 1 untuk tiap client fallback
        n_client = len(downloader.fallback_clients())
        script = [RuntimeError(BOT_MSG) for _ in range(n_client + 1)]
        try:
            run_download(workdir, script)
            failures.append("harusnya melempar BotCheckError")
        except BotCheckError as exc:
            text = str(exc)
            print("  pesan:", text.splitlines()[0])
            for line in text.splitlines()[1:4]:
                print("   ", line)
            for wajib in ("cookie", "file lokal", "reputasi IP"):
                if wajib.lower() not in text.lower():
                    failures.append(f"pesan tidak menyebut '{wajib}'")
            if "Sign in to confirm" not in text:
                failures.append("pesan tidak menyertakan galat asli YouTube")
            for client in downloader.fallback_clients():
                if client not in text:
                    failures.append(f"pesan tidak menyebut client yang dicoba: {client}")
            if "yt-dlp --extractor-args" not in text:
                failures.append("pesan tidak memberi perintah manual siap tempel")

    print("\n[4] Cookie sudah dikirim -> tidak ada retry sia-sia")
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        cookie_file = workdir / "cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        script = [RuntimeError(BOT_MSG)]
        calls = install_fake_yt_dlp(script)
        make_video(workdir)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                downloader.download(
                    "https://www.youtube.com/watch?v=wDKyVtbdEsc",
                    workdir=workdir,
                    cookies_file=str(cookie_file),
                )
            failures.append("harusnya melempar BotCheckError")
        except BotCheckError as exc:
            print(f"  percobaan={len(calls)} cookiefile={calls[0].get('cookiefile')}")
            print("  pesan:", str(exc).splitlines()[1].strip())
            if len(calls) != 1:
                failures.append(f"tidak boleh retry tanpa tambahan apa pun, percobaan={len(calls)}")
            if calls[0].get("cookiefile") != str(cookie_file.resolve()):
                failures.append(f"cookiefile tidak diteruskan: {calls[0].get('cookiefile')}")
        finally:
            sys.modules.pop("yt_dlp", None)

    print("\n[5] Galat biasa (video privat) -> DownloadError biasa")
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        calls = install_fake_yt_dlp([RuntimeError(PRIVATE_MSG)])
        make_video(workdir)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                downloader.download(
                    "https://www.youtube.com/watch?v=abc123", workdir=workdir
                )
            failures.append("harusnya melempar DownloadError")
        except BotCheckError as exc:
            failures.append(f"galat biasa salah dikira bot check: {exc}")
        except DownloadError as exc:
            print(f"  percobaan={len(calls)} pesan={str(exc).splitlines()[0][:70]}")
            if len(calls) != 1:
                failures.append("galat biasa tidak boleh memicu retry")

    print("\n[6] Validasi cookie + extractor_args")
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        # daftar player client bisa diatur lewat env (P-024)
        import os

        asli = os.environ.get("YT_PLAYER_CLIENTS")
        try:
            os.environ["YT_PLAYER_CLIENTS"] = "tv,ios,web_safari,mweb"
            clients = downloader.fallback_clients()
            print(f"  YT_PLAYER_CLIENTS -> {clients}")
            if clients != ["tv", "ios", "web_safari", "mweb"]:
                failures.append(f"env YT_PLAYER_CLIENTS tidak dipakai: {clients}")
        finally:
            if asli is None:
                os.environ.pop("YT_PLAYER_CLIENTS", None)
            else:
                os.environ["YT_PLAYER_CLIENTS"] = asli
        if downloader.fallback_clients() != list(downloader.BOT_CHECK_FALLBACK_CLIENTS):
            failures.append("default fallback_clients() harus sesuai BOT_CHECK_FALLBACK_CLIENTS")
        print(f"  default -> {downloader.fallback_clients()}")
        try:
            downloader.resolve_cookies(workdir / "hilang.txt")
            failures.append("file cookies yang tidak ada harus ditolak")
        except DownloadError as exc:
            print("  cookies hilang ->", str(exc).splitlines()[0])
        good = workdir / "cookies.txt"
        good.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        resolved = downloader.resolve_cookies(good)
        if resolved != good.resolve():
            failures.append(f"resolve_cookies salah: {resolved}")
        if downloader.resolve_cookies("") is not None or downloader.resolve_cookies(None) is not None:
            failures.append("cookie kosong harus menghasilkan None")
        print(f"  cookies.txt -> {resolved}")

    if downloader.build_extractor_args(None) != {}:
        failures.append("player_client None harus menghasilkan opts kosong")
    if downloader.build_extractor_args("tv") != {
        "extractor_args": {"youtube": {"player_client": ["player_client=tv"]}}
    }:
        failures.append(f"player_client tunggal salah: {downloader.build_extractor_args('tv')}")
    gabungan = ",".join(downloader.BOT_CHECK_FALLBACK_CLIENTS)
    if downloader.build_extractor_args(downloader.BOT_CHECK_FALLBACK_CLIENTS) != {
        "extractor_args": {"youtube": {"player_client": ["player_client=" + gabungan]}}
    }:
        failures.append("gabungan player client salah")
    # Key top-level "youtube" diabaikan yt-dlp -> harus berada di extractor_args
    if "youtube" in downloader.build_extractor_args("tv"):
        failures.append("player client harus di dalam extractor_args, bukan key top-level")
    # player_skip=webpage justru memicu bot check (P-025) -> jangan dipakai di retry
    if downloader.build_extractor_args("tv", skip_webpage=True) != {
        "extractor_args": {
            "youtube": {"player_client": ["player_client=tv"], "player_skip": ["webpage"]}
        }
    }:
        failures.append("skip_webpage tidak producing opts yang benar")

    print("\n[8] runtime JS untuk yt-dlp (P-025)")
    import os

    asli_js = os.environ.get("YT_JS_RUNTIMES")
    try:
        os.environ["YT_JS_RUNTIMES"] = "none"
        if downloader.detect_js_runtimes() != {}:
            failures.append("YT_JS_RUNTIMES=none harus mematikan runtime JS")
        os.environ["YT_JS_RUNTIMES"] = "auto"
        runtimes = downloader.detect_js_runtimes()
        print(f"  auto -> {sorted(runtimes)}")
        for nama in runtimes:
            if nama not in ("deno", "node", "bun"):
                failures.append(f"runtime JS tak dikenal: {nama}")
        os.environ["YT_JS_RUNTIMES"] = "deno"
        hanya_deno = downloader.detect_js_runtimes()
        print(f"  paksa deno -> {sorted(hanya_deno)}")
        if any(k != "deno" for k in hanya_deno):
            failures.append(f"YT_JS_RUNTIMES=deno harus hanya deno: {sorted(hanya_deno)}")
    finally:
        if asli_js is None:
            os.environ.pop("YT_JS_RUNTIMES", None)
        else:
            os.environ["YT_JS_RUNTIMES"] = asli_js
    print("  extractor_args: None/tv/tuple -> kosong, tv, tv,ios")

    print("\n[7] File lokal tidak terpengaruh")
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        video = workdir / "lokal.mp4"
        # Video sungguhan (bukan file kosong) karena downloader memvalidasi durasi
        # lewat ffprobe. Urutan opsi FFmpeg: input dulu, baru output (pelajaran P-005).
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not video.exists():
            print(f"  dilewati: FFmpeg tidak bisa membuat video uji ({proc.stderr.strip()[:80]})")
        else:
            path, meta = downloader.download(str(video), workdir=workdir)
            print(f"  file lokal -> {path.name} durasi={meta['duration']:.1f}s")
            if meta["is_url"]:
                failures.append("file lokal harus ditandai is_url=False")

    print()
    if failures:
        for f in failures:
            print(f"  GAGAL: {f}")
        return 1
    print("Semua pemeriksaan bot check LULUS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())