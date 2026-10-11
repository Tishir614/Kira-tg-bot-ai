#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "❌ .env не найден"; exit 1; }
cp .env ".env.backup-1.7.0-$(date +%Y%m%d-%H%M%S)"
echo "🦊 Kira 1.7: сборка без удаления volumes..."
docker compose build kira
echo "🗃️ Миграция БД..."
docker compose run --rm kira uv run --no-dev alembic upgrade head
docker compose up -d
docker compose ps
echo "✅ Проверь: выпить / топ алкоголизм / kira / dnd"
