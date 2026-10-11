#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

[[ -f .env ]] || { echo '[ERROR] .env не найден.' >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo '[ERROR] Docker не найден.' >&2; exit 1; }

BACKUP=".env.backup-1.1.0-$(date +%Y%m%d-%H%M%S)"
cp .env "$BACKUP"
chmod 600 "$BACKUP" .env

echo "[Kira 1.1] Резервная копия настроек: $BACKUP"
echo '[Kira 1.1] Настраиваю адаптивное локальное AI-ядро…'
# ai_quality.sh is non-interactive when invoked from this script and automatically
# chooses whether the stronger 4B route fits the server RAM.
bash ./ai_quality.sh </dev/null

echo '[Kira 1.1] Запускаю остальные сервисы без удаления volumes…'
docker compose up -d --build kira redis

echo
 docker compose ps
 echo
 echo '[OK] KiraBot 1.1.0 обновлён. База/память/volumes не удалялись.'
 echo '[INFO] Проверь в Telegram: /скорость_ии, /мат, /найти_видео, /ютуб, /тикток, /твич'
