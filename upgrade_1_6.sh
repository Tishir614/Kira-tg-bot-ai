#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "❌ .env не найден"; exit 1; }
cp .env ".env.backup-1.6.0-$(date +%Y%m%d-%H%M%S)"
echo "🦊 Kira 1.6: сборка без удаления volumes..."
docker compose build kira
docker compose up -d
docker compose ps
echo "✅ Проверь /kira и /dnd"
