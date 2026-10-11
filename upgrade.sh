#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# -eq 1 ]] || { echo 'Usage: bash upgrade.sh /path/to/release.zip'; exit 1; }
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo 'Требуется Python 3.11+ на хосте.'; exit 1; }
python3 "$PROJECT_DIR/tools/safe_upgrade.py" "$1" "$PROJECT_DIR"
