#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "KiraBot 1.9.0: validating and rebuilding..."
python3 -m compileall -q bot
python3 - <<'PY'
import ast
from pathlib import Path
for path in Path('bot').rglob('*.py'):
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print('Python AST: OK')
PY
docker compose config >/dev/null
docker compose up -d --build --force-recreate kira
echo "KiraBot 1.9.0 started. Check: docker compose logs --tail=100 kira"
