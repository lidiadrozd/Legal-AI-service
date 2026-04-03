"""
Встроенные шаблоны: файлы из каталога backend/builtin_templates (или BUILTIN_TEMPLATES_PATH).

Идентификатор в API и в чате: builtin:<имя_файла>, например builtin:pretenziya.docx
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings

BUILTIN_PREFIX = "builtin:"

_ALLOWED_SUFFIX = {".docx", ".pdf", ".txt"}

# Служебные файлы в каталоге не показываем модели как шаблоны
_SKIP_NAMES_LOWER = {"readme.txt", "readme"}


def _backend_root() -> Path:
    """Каталог backend/ (родитель пакета app)."""
    return Path(__file__).resolve().parent.parent.parent


def builtin_templates_dir() -> Path:
    raw = (settings.BUILTIN_TEMPLATES_PATH or "").strip()
    if raw:
        p = Path(raw)
        return p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()
    return (_backend_root() / "builtin_templates").resolve()


def list_builtin_templates() -> list[tuple[str, str]]:
    """Список (id, отображаемое имя файла)."""
    root = builtin_templates_dir()
    if not root.is_dir():
        return []
    out: list[tuple[str, str]] = []
    for f in sorted(root.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        if f.suffix.lower() not in _ALLOWED_SUFFIX:
            continue
        if f.name.lower() in _SKIP_NAMES_LOWER:
            continue
        out.append((f"{BUILTIN_PREFIX}{f.name}", f.name))
    return out


def resolve_builtin_template_path(template_id: str) -> tuple[str | None, str | None]:
    """
    Для template_id вида builtin:filename.docx возвращает (абсолютный путь, имя файла).
    """
    if not template_id.startswith(BUILTIN_PREFIX):
        return None, None
    name = template_id[len(BUILTIN_PREFIX) :].strip()
    if not name or name in (".", ".."):
        return None, None
    if any(sep in name for sep in ("/", "\\")):
        return None, None
    path = (builtin_templates_dir() / name).resolve()
    try:
        path.relative_to(builtin_templates_dir())
    except ValueError:
        return None, None
    if not path.is_file():
        return None, None
    return str(path), name
