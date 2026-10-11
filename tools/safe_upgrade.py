"""Offline release installer. Run only while the bot is stopped."""
from __future__ import annotations
import ast
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile

PROTECTED = {'.env', 'static', '.git', '.venv', 'venv', '__pycache__', '.pytest_cache'}

def install(archive: Path, target: Path) -> Path:
    target = target.resolve()
    # A lock is outside the installation so replacing code cannot remove it.
    import fcntl
    with (target.parent / ('.' + target.name + '.upgrade.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _install(archive.resolve(), target)

def _install(archive: Path, target: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix='kira-stage-', dir=target.parent) as temp:
        stage = Path(temp)
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if len(infos) > 10000 or sum(i.file_size for i in infos) > 500 * 1024**2:
                raise ValueError('Archive exceeds release limits')
            seen = set()
            for info in infos:
                p = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (p.is_absolute() or '..' in p.parts or '\\' in info.filename
                        or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR))):
                    raise ValueError('Unsafe archive entry')
                if p in seen:
                    raise ValueError('Duplicate archive entry')
                seen.add(p)
            z.extractall(stage)
        roots = [p.parent for p in stage.glob('*/pyproject.toml')]
        if (stage / 'pyproject.toml').exists():
            roots.append(stage)
        if len(roots) != 1:
            raise ValueError('Expected exactly one release root')
        source = roots[0]
        for required in ('setup.sh', 'upgrade.sh', 'bot/__init__.py', 'tools/safe_upgrade.py'):
            if not (source / required).is_file():
                raise ValueError('Incomplete release: ' + required)
        with (source / 'pyproject.toml').open('rb') as f:
            tomllib.load(f)['project']['version']
        for p in source.rglob('*.py'):
            ast.parse(p.read_bytes(), filename=str(p))
        for p in source.rglob('*.sh'):
            subprocess.run(['bash', '-n', str(p)], check=True)
        entries = [p for p in source.iterdir() if p.name not in PROTECTED and not p.name.startswith('.env')]
        for p in entries:
            if (target / p.name).is_symlink():
                raise ValueError('Refusing to replace a symlink: ' + p.name)
        backup = Path(tempfile.mkdtemp(prefix=target.name + '-backup-', dir=target.parent))
        os.chmod(backup, 0o700)
        # Copy before any mutation; a backup failure leaves the installation intact.
        for p in target.iterdir():
            if p.name in {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache'}:
                continue
            if p.is_dir() and not p.is_symlink():
                shutil.copytree(p, backup / p.name, symlinks=True)
            else:
                shutil.copy2(p, backup / p.name, follow_symlinks=False)
        changed = []
        try:
            for p in entries:
                dest = target / p.name
                changed.append(p.name)
                remove(dest)
                if p.is_dir():
                    shutil.copytree(p, dest)
                else:
                    shutil.copy2(p, dest)
        except BaseException:
            for name in reversed(changed):
                dest, old = target / name, backup / name
                remove(dest)
                if old.is_dir():
                    shutil.copytree(old, dest, symlinks=True)
                elif old.exists() or old.is_symlink():
                    shutil.copy2(old, dest, follow_symlinks=False)
            raise
        return backup

def remove(path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)

if __name__ == '__main__':
    try:
        result = install(Path(sys.argv[1]), Path(sys.argv[2]))
        print(f'Обновление завершено. .env и static не изменены. Резервная копия: {result}')
        print('Запустите docker compose up -d --build. Повторный setup.sh не требуется.')
    except Exception as exc:
        print(f'Обновление не завершено: {type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
