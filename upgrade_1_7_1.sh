#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "KiraBot 1.7.1: rebuilding bot with social side effects..."
docker compose config >/dev/null
docker compose up -d --build --force-recreate kira
echo "KiraBot 1.7.1 started. Check: docker compose logs --tail=80 kira"
