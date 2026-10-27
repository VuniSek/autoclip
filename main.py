#!/usr/bin/env python3
"""AUTO CLIP - entry point CLI.

Contoh:
    python main.py --input https://www.youtube.com/watch?v=xxxx
    python main.py --input input/vidio-saya.mp4 --max-clips 3
    python main.py --input video.mp4 --face-tracking --keep-temp
"""

from __future__ import annotations

import argparse
import re
import sys
import traceback
from pathlib import Path

from src.config import (
    OUTPUT_DIR,
    TEMP_DIR,
    Config,
    ConfigError,
    load_config,
)
from src import downloader, highlight, merger, transcriber
from src.clipper import ClipError, cut_clip
from src.subtitles import SubtitleError, build_subtitles


def log(msg: str) -> None:
    print(msg, flush=True)


def log_step(n: int, total: int, msg: str) -> None:
    log(f"\n=== [{n}/{total}] {msg} ===")


def slugify(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip()).strip("-").lower()
    if not s:
        s = "klip"
    return s[:max_len].rstrip("-")


def record_problem(title: str, step: str, symptom: str, cause: str) -> Path:
    """Catat masalah ke problem.md (tanpa API key) sesuai aturan AGENTS.md."""
    from datetime import datetime

    path = Path(__file__).resolve().parent / "problem.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# problem.md\n"
    numbers = [int(m) for m in re.findall(r"^## P-(\d{3})", existing, re.MULTILINE)]
    next_id = max(numbers) + 1 if numbers else 1
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## P-{next_id:03d} | {title}\n"
        f"- Waktu: {stamp}\n"
        f"- File/langkah terkait: {step}\n"
        f"- Pesan error / gejala (salin apa adanya, tanpa API key):\n"
        f"  ```\n  {symptom}\n  ```\n"
        f"- Dugaan penyebab: {cause}\n"
        f"- Status: OPEN\n"
    )
    if not existing.endswith("\n"):
        existing += "\n"
    path.write_text(existing + entry, encoding="utf-8")
    print(f"[catatan] masalah dicatat di {path.name} (P-{next_id:03d})")
    return path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="autoclip",
        description="Ubah video panjang menjadi klip pendek vertikal 9:16 bersubtitle.",
    )
    p.add_argument("--input", "-i", required=True, help="URL video atau path file lokal")
    p.add_argument("--max-clips", type=int, default=None, help="Override MAX_CLIPS dari .env")
    p.add_argument("--min-seconds", type=int, default=None, help="Override CLIP_MIN_SECONDS")
    p.add_argument("--max-seconds", type=int, default=None, help="Override CLIP_MAX_SECONDS")
    p.add_argument("--language", default=None, help="Override LANGUAGE dari .env")
    p.add_argument(
        "--face-tracking",
        action="store_true",
        help="Ikuti wajah saat crop (default dari .env FACE_TRACKING)",
    )
    p.add_argument(
        "--no-face-tracking", action="store_true", help="Paksa crop tengah"
    )
    p.add_argument(
        "--face-sample-fps", type=float, default=None,
        help=(
            "Berapa kali deteksi wajah per detik saat face tracking "
            "(default FACE_TRACK_SAMPLE_FPS=10). Makin tinggi makin akurat, "
            "makin lambat."
        ),
    )
    p.add_argument(
        "--face-smooth", type=int, default=None,
        help=(
            "Jendela perataan lintasan wajah (default FACE_TRACK_SMOOTH=5). "
            "1 = mengikuti apa adanya, 9 = sangat halus."
        ),
    )
    p.add_argument(
        "--face-detect-width", type=int, default=None,
        help=(
            "Lebar frame untuk deteksi wajah (default FACE_DETECT_WIDTH=640). "
            "640 = cepat, 1280 = lebih rinci."
        ),
    )
    p.add_argument("--keep-temp", action="store_true", help="Jangan hapus folder temp/")
    p.add_argument(
        "--cookies", default=None,
        help=(
            "Path file cookies.txt untuk yt-dlp, hanya perlu kalau YouTube minta "
            "verifikasi bot ('Sign in to confirm you\'re not a bot')."
        ),
    )
    p.add_argument(
        "--progress-seconds", type=float, default=None,
        help=(
            # argparse mem-format help dengan operator '%', jadi persen biasa harus
            # ditulis '%%' (lihat problem.md P-018).
            "Jarak minimal antar baris progress unduhan (detik, default "
            "DOWNLOAD_PROGRESS_SECONDS=15). 0 = hanya tiap 10%%."
        ),
    )
    p.add_argument(
        "--merge",
        action="store_true",
        help=(
            "Gabungkan semua klip jadi satu video (default dari .env MERGE_CLIPS). "
            "Contoh: --merge"
        ),
    )
    p.add_argument(
        "--no-merge",
        action="store_true",
        help="Paksa tidak menggabungkan klip",
    )
    p.add_argument(
        "--env", default=None,
        help="Path file .env alternatif (default: .env di root proyek)",
    )
    p.add_argument(
        "--reuse-transcript", action="store_true",
        help="Pakai temp/transcript.json yang ada, lewati transkripsi (hemat waktu)",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p.parse_args()


def resolve_face_tracking(args: argparse.Namespace, cfg: Config) -> bool:
    if args.no_face_tracking:
        return False
    if args.face_tracking:
        return True
    return cfg.face_tracking


def resolve_merge(args: argparse.Namespace, cfg: Config) -> bool:
    """True kalau semua klip harus digabung jadi satu video."""
    if args.no_merge:
        return False
    if args.merge:
        return True
    return cfg.merge_clips


def resolve_face_settings(args: argparse.Namespace, cfg: Config) -> dict:
    """Pengaturan face tracking: CLI menang atas nilai di `.env`."""
    return {
        "face_sample_fps": (
            args.face_sample_fps
            if args.face_sample_fps is not None
            else cfg.face_track_sample_fps
        ),
        "face_smooth": (
            args.face_smooth if args.face_smooth is not None else cfg.face_track_smooth
        ),
        "face_detect_width": (
            args.face_detect_width
            if args.face_detect_width is not None
            else cfg.face_detect_width
        ),
    }


def process_one(
    source: str,
    cfg: Config,
    args: argparse.Namespace,
    index: int = 1,
) -> list[Path]:
    """Jalankan alur penuh untuk satu video. Return list file hasil."""
    face_tracking = resolve_face_tracking(args, cfg)
    max_clips = args.max_clips if args.max_clips is not None else cfg.max_clips
    min_sec = args.min_seconds if args.min_seconds is not None else cfg.clip_min_seconds
    max_sec = args.max_seconds if args.max_seconds is not None else cfg.clip_max_seconds
    language = args.language or cfg.language
    face_opts = resolve_face_settings(args, cfg)

    log(f"\n{'#' * 60}")
    log(f"# VIDEO {index}: {source}")
    log(f"#clip: {min_sec}-{max_sec}s | max_clips={max_clips} | face_tracking={face_tracking}")
    if face_tracking:
        log(
            f"#face: sampel={face_opts['face_sample_fps']:g}/detik "
            f"perataan={face_opts['face_smooth']} "
            f"lebar_deteksi={face_opts['face_detect_width']}px"
        )
    log(f"{'#' * 60}")

    # --- 1. Ambil video + ekstrak audio ---
    log_step(1, 5, "Mengambil video & mengekstrak audio")
    if downloader.is_url(source):
        log("  (unduhan dari URL: progress, kecepatan, dan ETA ditampilkan di bawah)")
        log(f"  (batas resolusi sumber: {cfg.max_source_height}p)")
    progress_seconds = (
        args.progress_seconds if args.progress_seconds is not None
        else cfg.download_progress_seconds
    )
    video_path, meta = downloader.download(
        source,
        max_height=cfg.max_source_height,
        progress_seconds=progress_seconds,
        cookies_file=args.cookies or cfg.yt_cookies_file,
    )
    duration = float(meta.get("duration") or 0)
    log(f"  video : {video_path}")
    log(f"  durasi: {duration:.1f}s")
    audio_path = downloader.extract_audio(video_path)
    log(f"  audio : {audio_path}")

    # --- 2. Transkripsi ---
    transcript_path = TEMP_DIR / "transcript.json"
    if args.reuse_transcript and transcript_path.exists():
        log_step(2, 5, "Memakai transkripsi yang sudah ada (--reuse-transcript)")
        transcript = transcriber.load_transcript(transcript_path)
        log(f"  {len(transcript['segments'])} segmen, {len(transcript['words'])} kata")
        log(f"  bahasa: {transcript['language']}")
    else:
        log_step(2, 5, "Transkripsi dengan faster-whisper")
        transcript = transcriber.transcribe(
            audio_path,
            model_name=cfg.whisper_model,
            device=cfg.whisper_device,
            compute_type=cfg.whisper_compute_type,
            language=language,
        )
        transcript_path = transcriber.save_transcript(transcript)
        log(f"  {len(transcript['segments'])} segmen, {len(transcript['words'])} kata")
        log(f"  bahasa terdeteksi: {transcript['language']}")
        log(transcriber.transcript_preview(transcript, limit=6 if args.verbose else 3))
        log(f"  disimpan: {transcript_path}")

    # --- 3. Highlight via OpenRouter ---
    log_step(3, 5, "Memilih segmen terbaik lewat OpenRouter")
    llm_transcript = "\n".join(
        f"[{s['start']:.1f} -> {s['end']:.1f}] {s['text']}" for s in transcript["segments"]
    )
    segments = highlight.select_highlights(
        api_key=cfg.openrouter_api_key,
        base_url=cfg.openrouter_base_url,
        model=cfg.openrouter_model,
        transcript_text=llm_transcript,
        duration=duration,
        max_clips=max_clips,
        min_seconds=min_sec,
        max_seconds=max_sec,
        language=language,
        timeout=cfg.llm_timeout,
    )
    segments = segments[:max_clips]
    log(f"  {len(segments)} segmen dipilih:")
    for i, s in enumerate(segments, 1):
        log(f"   {i}. [{s['start']:.1f} -> {s['end']:.1f}] ({s['end'] - s['start']:.1f}s) "
            f"{s['title']} - {s['reason']}")

    # --- 4 & 5. Potong + subtitle ---
    log_step(4, 5, "Membuat subtitle dan memotong klip 9:16")
    outputs: list[Path] = []
    base_slug = slugify(meta.get("title") or Path(str(video_path)).stem)
    for i, seg in enumerate(segments, 1):
        name = f"{index:02d}_{base_slug}_klip{i}_{slugify(seg['title'], 32)}"
        ass_path, srt_path = build_subtitles(
            transcript, seg["start"], seg["end"], OUTPUT_DIR, name
        )
        out_video = OUTPUT_DIR / f"{name}.mp4"
        log(f"  [{i}/{len(segments)}] {seg['title']} "
            f"({seg['end'] - seg['start']:.1f}s) -> {out_video.name}")
        cut_clip(
            video_path,
            start=seg["start"],
            end=seg["end"],
            out_path=out_video,
            face_tracking=face_tracking,
            burn_subtitle=ass_path,
            **face_opts,
        )
        # salin .srt ke output juga (dari slice yang sama, tanpa subtitle burn)
        log(f"      subtitle: {ass_path.name}, {srt_path.name}")
        outputs.append(out_video)

    log_step(5, 5, "Selesai")
    return outputs


def merged_file_name(clips: list[Path], fallback: str = "video") -> str:
    """Nama file gabungan: `00_<slug-judul>_gabungan.mp4`."""
    slug = fallback
    if clips:
        parts = clips[0].stem.split("_")
        # nama klip: "<index>_<slug-video>_klip<no>_<slug-judul>"
        if len(parts) >= 3 and parts[2].startswith("klip"):
            slug = parts[1]
        else:
            slug = slugify(clips[0].stem)
    return f"00_{slug}_gabungan.mp4"


def main() -> int:
    args = parse_args()

    log("AUTO CLIP - video panjang -> klip vertikal 9:16 bersubtitle")
    try:
        cfg = load_config(args.env)
    except ConfigError as exc:
        log(f"\n[KONFIGURASI BELUM LENGKAP]\n{exc}")
        return 2

    if args.verbose:
        log("\n[Konfigurasi aktif - nilai dari .env, key dimasker]:")
        for k, v in cfg.public_summary().items():
            log(f"  {k} = {v}")

    if not downloader.ffmpeg_available():
        log("[ERROR] ffmpeg/ffprobe tidak ditemukan di PATH. Pasang ffmpeg terlebih dahulu.")
        return 3

    sources = [args.input]

    all_outputs: list[Path] = []
    try:
        for i, src in enumerate(sources, 1):
            all_outputs.extend(process_one(src, cfg, args, index=i))
    except ConfigError as exc:
        log(f"[KONFIGURASI ERROR] {exc}")
        return 2
    except downloader.BotCheckError as exc:
        # Verifikasi bot YouTube: bukan bug kode dan bukan file rusak, jadi pesannya
        # hanya berisi langkah yang bisa dilakukan user (lihat problem.md P-016).
        # Tidak dicatat ulang ke problem.md supaya jurnal tidak penuh dengan
        # pengulangan masalah IP yang sama.
        log(f"[ERROR VERIFIKASI BOT] {exc}")
        return 4
    except (downloader.DownloadError, transcriber.TranscriptionError) as exc:
        log(f"[ERROR UNDUH/TRANSKRIPSI] {exc}")
        return 4
    except highlight.HighlightError as exc:
        endpoint = highlight.endpoint_label(cfg.openrouter_base_url)
        log(f"[ERROR HIGHLIGHT/LLM] {exc}")
        log(f"[CATATAN] Endpoint {endpoint} gagal memilih segmen. "
            "Coba lagi nanti, periksa OPENROUTER_MODEL/OPENROUTER_BASE_URL di .env, "
            "atau perkecil durasi video.")
        # Dicatat ke problem.md dan TIDAK mengganti model secara diam-diam.
        try:
            record_problem(
                title=f"{endpoint} gagal memilih segmen highlight",
                step=f"langkah 3 (highlight), model={cfg.openrouter_model}",
                symptom=str(exc)[:500],
                cause=(
                    "Model/endpoint bisa rate limit, tidak bisa dihubungi, atau membalas "
                    "di luar format JSON setelah semua percobaan ulang habis."
                ),
            )
        except OSError as werr:
            log(f"[peringatan] gagal menulis problem.md: {werr}")
        return 5
    except (ClipError, SubtitleError) as exc:
        log(f"[ERROR CLIP/SUBTITLE] {exc}")
        return 6
    except KeyboardInterrupt:
        log("\n[DIBATIKAN user]")
        return 130
    except Exception as exc:  # noqa: BLE001
        log(f"[ERROR TIDAK TERDUKUR] {exc}")
        traceback.print_exc()
        return 1

    # --- penggabungan semua klip jadi satu video (opsional) ---
    if resolve_merge(args, cfg):
        log("\n=== [+] Menggabungkan semua klip jadi satu video ===")
        try:
            merged = merger.merge_clips(
                all_outputs, OUTPUT_DIR / merged_file_name(all_outputs)
            )
            size_mb = merged.stat().st_size / 1_048_576
            log(f"  gabungan : {merged.name} ({size_mb:.1f} MB)")
            all_outputs.append(merged)
        except merger.MergeError as exc:
            log(f"[PERINGATAN] Penggabungan gagal: {exc}")
            log("  Klip individual TIDAK dihapus dan tetap bisa dipakai di folder output/.")

    # --- ringkasan ---
    log(f"\n{'=' * 60}")
    log(f"SELESAI. {len(all_outputs)} klip di {OUTPUT_DIR}")
    log("=" * 60)
    for p in all_outputs:
        size_mb = p.stat().st_size / 1_048_576
        log(f"  {p.name}  ({size_mb:.1f} MB)")

    if not args.keep_temp:
        for f in TEMP_DIR.glob("*"):
            if f.is_file():
                try:
                    f.unlink()
                except OSError:
                    pass
        log(f"\nFolder temp dibersihkan: {TEMP_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())