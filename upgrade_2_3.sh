#!/usr/bin/env bash
set -Eeuo pipefail
TARGET="kira-persistent-data"
BACKUP_DIR="${KIRA_BACKUP_DIR:-/root/kira-backups}"
mkdir -p "$BACKUP_DIR"
command -v docker >/dev/null || { echo 'Docker not found'; exit 1; }
docker volume inspect "$TARGET" >/dev/null 2>&1 || docker volume create "$TARGET" >/dev/null
has_db() { docker run --rm -v "$1:/data:ro" alpine sh -c 'test -s /data/database.db' >/dev/null 2>&1; }
if has_db "$TARGET"; then
  stamp=$(date +%Y%m%d-%H%M%S)
  docker run --rm -v "$TARGET:/data:ro" -v "$BACKUP_DIR:/backup" alpine sh -c "cp /data/database.db /backup/database-$stamp.db"
  echo "Persistent DB already present; backup created: $BACKUP_DIR/database-$stamp.db"
else
  best=""; best_size=0
  while read -r v; do
    [ "$v" = "$TARGET" ] && continue
    case "$v" in *kira-data*) ;; *) continue ;; esac
    size=$(docker run --rm -v "$v:/data:ro" alpine sh -c 'test -s /data/database.db && stat -c %s /data/database.db || echo 0' 2>/dev/null || echo 0)
    case "$size" in ''|*[!0-9]*) size=0;; esac
    if [ "$size" -gt "$best_size" ]; then best="$v"; best_size="$size"; fi
  done < <(docker volume ls -q)
  if [ -n "$best" ]; then
    echo "Migrating persistent data from $best ($best_size bytes DB) -> $TARGET"
    docker run --rm -v "$best:/from:ro" -v "$TARGET:/to" alpine sh -c 'cp -a /from/. /to/'
  else
    echo 'No previous Kira database found; starting with a fresh persistent volume.'
  fi
fi
# Offline SQLite integrity check without mutating user data.
docker run --rm -v "$TARGET:/data" python:3.12-alpine python - <<'PY'
import sqlite3, pathlib, sys
p=pathlib.Path('/data/database.db')
if not p.exists():
    print('DB: fresh install'); raise SystemExit(0)
con=sqlite3.connect(p)
result=con.execute('PRAGMA integrity_check').fetchone()[0]
con.close()
print('DB integrity:', result)
if result != 'ok': raise SystemExit(2)
PY
echo 'Kira 2.3 persistent-data migration: OK'
