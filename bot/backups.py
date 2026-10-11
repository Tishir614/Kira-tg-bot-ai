from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from bot.config import settings
from bot.sql import DATABASE_PATH


async def create_database_backup() -> Path:
    """Create a consistent temporary SQLite snapshot using sqlite3 backup API."""
    return await asyncio.to_thread(_create_backup_sync, None)


async def create_persistent_database_backup() -> Path:
    """Create a consistent snapshot in DATA_DIR/backups and prune old copies."""
    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"kira-{stamp}.sqlite3"
    path = await asyncio.to_thread(_create_backup_sync, target)
    await asyncio.to_thread(_prune_backups, backup_dir, settings.backup_keep)
    return path


def _create_backup_sync(target: Path | None) -> Path:
    if target is None:
        fd, name = tempfile.mkstemp(prefix="kira-db-", suffix=".sqlite3")
        os.close(fd)
        target = Path(name)
        target.unlink(missing_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.unlink(missing_ok=True)
        target = tmp

    src = sqlite3.connect(str(DATABASE_PATH), timeout=10)
    dst = sqlite3.connect(str(target), timeout=10)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    # Persistent backups are first written atomically through .tmp.
    if target.suffix == ".tmp":
        final = target.with_suffix("")
        os.replace(target, final)
        return final
    return target


def _prune_backups(backup_dir: Path, keep: int) -> None:
    backups = sorted(
        backup_dir.glob("kira-*.sqlite3"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old in backups[max(1, keep):]:
        old.unlink(missing_ok=True)
