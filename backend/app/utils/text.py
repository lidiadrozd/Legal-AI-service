"""Форматирование пользовательских подписей (названия чатов, файлов и т.д.)."""
from __future__ import annotations

from pathlib import Path


def capitalize_first_letter(text: str | None) -> str:
    """Первая буква в строке (по unicode isalpha) — заглавная, остальное без изменений."""
    if text is None:
        return ""
    s = str(text).strip()
    if not s:
        return ""
    chars = list(s)
    for i, ch in enumerate(chars):
        if ch.isalpha():
            chars[i] = ch.upper()
            break
    return "".join(chars)


def capitalize_filename(filename: str | None) -> str:
    """Имя файла: заглавная первая буква основы (stem), расширение не трогаем."""
    if filename is None:
        return ""
    name = str(filename).strip()
    if not name:
        return ""
    p = Path(name)
    stem, suffix = p.stem, p.suffix
    if not stem and suffix:
        return capitalize_first_letter(name) or name
    cap = capitalize_first_letter(stem) or stem
    return f"{cap}{suffix}" if suffix else (cap or name)
