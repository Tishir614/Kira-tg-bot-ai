#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && cp .env ".env.backup-1.4.0-$(date +%Y%m%d-%H%M%S)"
grep -q '^SKETCHFORGE_PUBLIC_URL=' .env 2>/dev/null || echo 'SKETCHFORGE_PUBLIC_URL=' >> .env
grep -q '^OMNIGET_TELEGRAM_MAX_MB=' .env 2>/dev/null || echo 'OMNIGET_TELEGRAM_MAX_MB=49' >> .env
docker compose --profile voice --profile image --profile 3d up -d --build
printf '\nKira 1.4.0 запущена. Проверка:\n'
docker compose --profile 3d ps
printf '\nКоманды в Telegram: /инфо URL, /скачать URL, /аудио URL, /3d\n'
