"""Konfigurasi AUTO CLIP.

Semua nilai dibaca dari file .env (via python-dotenv). Tidak ada nama model
yang di-hardcode di modul ini.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Path root proyek (folder yang memuat .env)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_DIR = PROJECT_ROOT / "input"
TEMP_DIR = PROJECT_ROOT / "temp"
OUTPUT_DIR = PROJECT_ROOT / "output"

for _d in (INPUT_DIR, TEMP_DIR, OUTPUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Nilai placeholder yang menandakan .env belum diisi user.
PLACEHOLDERS = {
    "isi_api_key_di_sini",
    "isi_nama_model_gratis_di_sini",
    "",
    "none",
    "null",
    "changeme",
    "your_api_key_here",
    "your_model_here",
}


class ConfigError(RuntimeError):
    """Konfigurasi .env tidak valid / belum diisi."""


def _mask(value: str) -> str:
    """Tampilkan key dalam bentuk tersamar. JANGAN pernah print key mentah."""
    v = (value or "").strip()
    if not v:
        return "(kosong)"
    if len(v) <= 12:
        return f"{v[:2]}***"
    return f"{v[:6]}...{v[-4:]} (len={len(v)})"


def _parse_bool(raw: str | None, var: str) -> bool:
    if raw is None:
        return False
    val = raw.strip().lower()
    if val in ("1", "true", "yes", "y", "on"):
        return True
    if val in ("0", "false", "no", "n", "off", ""):
        return False
    raise ConfigError(f"{var} harus true/false, dapat '{raw}'")


def _parse_int(raw: str | None, var: str, default: int | None = None) -> int:
    if raw is None or raw.strip() == "":
        if default is None:
            raise ConfigError(f"{var} wajib diisi di .env")
        return default
    try:
        return int(float(raw.strip()))
    except ValueError as exc:
        raise ConfigError(f"{var} harus angka bulat, dapat '{raw}'") from exc


def _parse_float(raw: str | None, var: str, default: float) -> float:
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{var} harus angka, dapat '{raw}'") from exc


@dataclass(frozen=True)
class Config:
    openrouter_api_key: str
    openrouter_model: str
    openrouter_base_url: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    clip_min_seconds: int
    clip_max_seconds: int
    max_clips: int
    language: str
    face_tracking: bool
    max_source_height: int
    download_progress_seconds: float
    yt_cookies_file: str

    @property
    def model_slug(self) -> str:
        """Versi aman dari nama model untuk nama file output."""
        slug = re.sub(r"[^A-Za-z0-9]+", "-", self.openrouter_model).strip("-").lower()
        return slug or "model"

    def public_summary(self) -> dict:
        """Ringkasan config yang AMAN untuk ditampilkan/log."""
        return {
            "OPENROUTER_API_KEY": _mask(self.openrouter_api_key),
            "OPENROUTER_MODEL": self.openrouter_model,
            "OPENROUTER_BASE_URL": self.openrouter_base_url,
            "WHISPER_MODEL": self.whisper_model,
            "WHISPER_DEVICE": self.whisper_device,
            "WHISPER_COMPUTE_TYPE": self.whisper_compute_type,
            "CLIP_MIN_SECONDS": self.clip_min_seconds,
            "CLIP_MAX_SECONDS": self.clip_max_seconds,
            "MAX_CLIPS": self.max_clips,
            "LANGUAGE": self.language,
            "FACE_TRACKING": self.face_tracking,
            "MAX_SOURCE_HEIGHT": self.max_source_height,
            "DOWNLOAD_PROGRESS_SECONDS": self.download_progress_seconds,
            "YT_COOKIES_FILE": self.yt_cookies_file or "(kosong)",
        }


def _validate(cfg: Config) -> Config:
    """Validasi nilai konfigurasi."""
    problems: list[str] = []

    if cfg.openrouter_api_key.strip().lower() in PLACEHOLDERS:
        problems.append(
            "OPENROUTER_API_KEY masih placeholder. "
            "Isi API key OpenRouter kamu di file .env (root proyek)."
        )
    if cfg.openrouter_model.strip().lower() in PLACEHOLDERS:
        problems.append(
            "OPENROUTER_MODEL masih placeholder. "
            "Isi nama model gratis OpenRouter (harus berakhiran :free) di file .env."
        )

    if problems:
        raise ConfigError("Konfigurasi .env belum lengkap:\n  - " + "\n  - ".join(problems))

    # Penegakan model gratis: BLOKIR KERAS. Proyek ini hanya mengizinkan model gratis,
    # jadi model tanpa akhiran ':free' harus menghentikan program, bukan sekadar
    # memberi peringatan (lihat problem.md P-010).
    if ":free" not in cfg.openrouter_model.lower():
        raise ConfigError(
            f"OPENROUTER_MODEL='{cfg.openrouter_model}' tidak berakhiran ':free'.\n"
            "Proyek ini hanya mengizinkan model GRATIS. Ganti nilainya di .env dengan "
            "nama model yang berakhiran ':free' (contoh: 'google/gemini-2.0-flash-exp:free').\n"
            "Daftar model gratis: https://openrouter.ai/models?max_price=0"
        )

    if cfg.clip_min_seconds >= cfg.clip_max_seconds:
        raise ConfigError(
            f"CLIP_MIN_SECONDS ({cfg.clip_min_seconds}) harus lebih kecil dari "
            f"CLIP_MAX_SECONDS ({cfg.clip_max_seconds})."
        )
    if cfg.max_clips < 1:
        raise ConfigError("MAX_CLIPS harus >= 1.")
    if cfg.max_source_height != 0 and cfg.max_source_height < 360:
        raise ConfigError(
            "MAX_SOURCE_HEIGHT harus >= 360 (hasil akhir klip 1080x1920, "
            "jadi 720/1080 sudah cukup), atau 0 untuk tanpa batas."
        )
    if cfg.yt_cookies_file and not Path(cfg.yt_cookies_file).expanduser().is_file():
        raise ConfigError(
            f"YT_COOKIES_FILE menunjuk file yang tidak ada: {cfg.yt_cookies_file}\n"
            "  Kosongkan nilainya kalau tidak memakai cookie."
        )
    if not 0 <= cfg.download_progress_seconds <= 3600:
        raise ConfigError(
            f"DOWNLOAD_PROGRESS_SECONDS ({cfg.download_progress_seconds:g}) harus antara "
            "0 (hanya tampilkan tiap 10%) dan 3600."
        )

    return cfg


def load_config(env_path: str | Path | None = None) -> Config:
    """Baca .env, validasi, dan kembalikan objek Config."""
    path = Path(env_path) if env_path else PROJECT_ROOT / ".env"
    if not path.exists():
        raise ConfigError(
            f"File .env tidak ditemukan di {path}.\n"
            f"Salin .env.example menjadi .env lalu isi nilainya:\n"
            f"  cp .env.example .env"
        )

    load_dotenv(dotenv_path=path, override=True)

    cfg = Config(
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        openrouter_model=os.getenv("OPENROUTER_MODEL", ""),
        openrouter_base_url=os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        ).rstrip("/"),
        whisper_model=os.getenv("WHISPER_MODEL", "small"),
        whisper_device=os.getenv("WHISPER_DEVICE", "auto"),
        whisper_compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "auto"),
        clip_min_seconds=_parse_int(os.getenv("CLIP_MIN_SECONDS"), "CLIP_MIN_SECONDS", 30),
        clip_max_seconds=_parse_int(os.getenv("CLIP_MAX_SECONDS"), "CLIP_MAX_SECONDS", 60),
        max_clips=_parse_int(os.getenv("MAX_CLIPS"), "MAX_CLIPS", 5),
        language=os.getenv("LANGUAGE", "id") or "id",
        face_tracking=_parse_bool(os.getenv("FACE_TRACKING"), "FACE_TRACKING"),
        max_source_height=_parse_int(os.getenv("MAX_SOURCE_HEIGHT"), "MAX_SOURCE_HEIGHT", 1080),
        download_progress_seconds=_parse_float(
            os.getenv("DOWNLOAD_PROGRESS_SECONDS"), "DOWNLOAD_PROGRESS_SECONDS", 15.0
        ),
        yt_cookies_file=(os.getenv("YT_COOKIES_FILE", "") or "").strip(),
    )
    return _validate(cfg)
