"""Save source code for rollback without credentials, uploads or databases."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import zipfile
import argparse

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"node_modules", ".venv", ".git", "__pycache__", ".pytest_cache", "dist", "storage", "certs"}
PARTS = ["backend/app", "backend/alembic", "backend/tests", "frontend/src", "frontend/public", "tools", "docs", ".github", "deploy"]
ROOT_FILES = ["README.md", "LICENSE", ".gitignore", "compose.yaml", "backend/docker-compose.yml", "backend/Dockerfile",
              "backend/requirements.txt", "backend/alembic.ini", "frontend/package.json", "frontend/package-lock.json",
              "frontend/vite.config.ts", "frontend/index.html", "frontend/tsconfig.json", "frontend/tsconfig.node.json"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='conversation-2026-10-25-before-fixes')
    name = parser.parse_args().name
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in name):
        raise SystemExit('Use a simple checkpoint name')
    target = ROOT / 'artifacts/checkpoints' / (name + '.zip')
    if target.exists():
        raise SystemExit("Checkpoint already exists; refusing to overwrite it")
    files = set()
    for part in PARTS:
        directory = ROOT / part
        if directory.is_dir():
            for file in directory.rglob("*"):
                relative = file.relative_to(ROOT)
                if (file.is_file() and not any(p in EXCLUDED for p in relative.parts)
                        and not file.name.startswith('.env')
                        and (file.suffix not in {'.pyc', '.log', '.docx', '.pdf', '.png'}
                             or str(relative).replace('\\', '/').startswith(('backend/app/templates/form_sources/', 'backend/app/templates/assets/')))
                        and not (part == 'backend/tests' and file.suffix != '.py')):
                    files.add(file)
    files.update(ROOT / file for file in ROOT_FILES if (ROOT / file).is_file())
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = {str(file.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(file.read_bytes()).hexdigest()
                for file in sorted(files)}
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files):
            archive.write(file, file.relative_to(ROOT))
        archive.writestr('CHECKPOINT_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.sha256').write_text(digest + '  ' + target.name + '\n', encoding='utf-8')
    print(f"Checkpoint saved: {target}; files={len(files)}; sha256={digest}")


if __name__ == '__main__':
    main()
