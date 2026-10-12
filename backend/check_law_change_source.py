"""Validate an operator-reviewed JSON feed offline; no DB, GigaChat or notifications."""
import argparse
from pathlib import Path

from app.services.curated_law_changes import load_curated_changes, CuratedSourceError


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка JSON-источника изменений без импорта и рассылки")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    try:
        changes = load_curated_changes(args.file, catalog_root=args.catalog)
    except CuratedSourceError as exc:
        print(f"Источник отклонён: {exc}")
        return 1
    print(f"Источник проверен: {len(changes)} изменений. Импорт и рассылка не выполнялись.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
