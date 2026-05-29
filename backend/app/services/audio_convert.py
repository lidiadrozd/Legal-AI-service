"""
Конвертация загруженного аудио (webm, ogg, mp3, wav) в PCM S16LE mono для SaluteSpeech.
Требует ffmpeg в PATH (в Docker ставится в Dockerfile).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_SUFFIX_BY_CONTENT_TYPE: dict[str, str] = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
}


def _suffix_for_upload(content_type: str | None, filename: str | None) -> str:
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base in _SUFFIX_BY_CONTENT_TYPE:
            return _SUFFIX_BY_CONTENT_TYPE[base]
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in {".webm", ".ogg", ".mp3", ".wav", ".m4a", ".opus"}:
            return ext
    return ".webm"


def transcode_to_pcm16(
    audio_bytes: bytes,
    *,
    sample_rate: int = 16000,
    content_type: str | None = None,
    filename: str | None = None,
) -> bytes:
    if not audio_bytes:
        raise ValueError("Пустой аудиофайл")

    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg не найден на сервере. Установите ffmpeg для голосового ввода (в Docker: apt install ffmpeg)."
        )

    suffix = _suffix_for_upload(content_type, filename)

    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / f"input{suffix}"
        out = Path(tmp) / "output.pcm"
        inp.write_bytes(audio_bytes)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(inp),
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            str(out),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, check=False)
        except OSError as exc:
            raise RuntimeError(f"Не удалось запустить ffmpeg: {exc}") from exc

        if proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", errors="replace")[-500:]
            logger.error("ffmpeg failed: %s", err)
            raise ValueError("Не удалось обработать аудио. Запишите короче или в другом браузере.")

        pcm = out.read_bytes()
        if not pcm:
            raise ValueError("После конвертации аудио пустое")
        return pcm
