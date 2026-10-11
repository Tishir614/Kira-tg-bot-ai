#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

[[ -f .env ]] || { echo "[ERROR] .env не найден. Сначала запусти setup.sh." >&2; exit 1; }
command -v docker >/dev/null || { echo "[ERROR] docker не найден." >&2; exit 1; }

dc=(docker compose)
MEM_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
MEM_GB=$(( MEM_KB / 1024 / 1024 ))

# Kira 1.1 adaptive local route. Everyday chat stays on the 2B model; hard
# questions use Qwen3.5 4B when the server has enough headroom. Only one model
# is intentionally kept resident at a time.
FAST="qwen3.5:2b-q4_K_M"
if (( MEM_GB >= 6 )); then
  SMART="qwen3.5:4b"
else
  SMART="$FAST"
fi
FALLBACK="qwen3:1.7b"

echo "Kira AI 1.1 Adaptive Core"
echo "RAM: ~${MEM_GB} GB"
echo "Быстрая модель: ${FAST}"
echo "Умная модель: ${SMART}"
echo "Резервная модель: ${FALLBACK}"
echo "Одновременно модели не держатся в RAM: Kira переключает их по сложности запроса."
echo "Токены/API-ключи выводиться не будут."

if [[ -t 0 ]]; then
  read -r -p "Скачать/обновить эти локальные модели? [Y/n] " ANSWER
  case "${ANSWER:-Y}" in
    n|N|no|NO|нет|Нет) echo "Отменено."; exit 0 ;;
  esac
fi

"${dc[@]}" --profile ollama up -d ollama
"${dc[@]}" --profile ollama exec -T ollama ollama pull "$FAST"
if [[ "$SMART" != "$FAST" ]]; then
  "${dc[@]}" --profile ollama exec -T ollama ollama pull "$SMART"
fi
"${dc[@]}" --profile ollama exec -T ollama ollama pull "$FALLBACK"

python3 - "$FAST" "$SMART" "$FALLBACK" <<'PY'
from pathlib import Path
import re, sys

path = Path('.env')
fast, smart, fallback = sys.argv[1:4]
text = path.read_text(encoding='utf-8')

def get(key: str) -> str:
    m = re.search(rf'(?m)^{re.escape(key)}=(.*)$', text)
    return m.group(1).strip() if m else ''

def set_key(key: str, value: str) -> None:
    global text
    pattern = rf'(?m)^{re.escape(key)}=.*$'
    line = f'{key}={value}'
    if re.search(pattern, text):
        text = re.sub(pattern, line, text)
    else:
        if not text.endswith('\n'):
            text += '\n'
        text += line + '\n'

set_key('OLLAMA_BASE_URL', 'http://ollama:11434')
set_key('OLLAMA_MODEL', fast)
set_key('OLLAMA_FAST_MODEL', fast)
set_key('OLLAMA_SMART_MODEL', smart)
set_key('OLLAMA_MODELS', ','.join(dict.fromkeys((fast, smart, fallback))))
set_key('AI_ADAPTIVE_ROUTING', '1')
set_key('AI_QUALITY_FIRST', '1')
set_key('AI_FAST_MODE', '1')
set_key('OLLAMA_KEEP_ALIVE', '10m')
set_key('OLLAMA_NUM_CTX', '4096')
set_key('AI_TEMPERATURE', '0.32')
set_key('AI_CREATIVE_TEMPERATURE', '0.72')
set_key('AI_RESEARCH_TEMPERATURE', '0.25')
set_key('AI_SMART_DIALOGUE', '1')
set_key('AI_DELIBERATE_MODE', '1')
set_key('AI_REVIEW_PASS', '0')
set_key('AI_HISTORY_MESSAGES', '10')
set_key('AI_HISTORY_MAX_CHARS', '10000')
set_key('AI_MAX_RESPONSE_TOKENS', '950')

set_key('AI_PROVIDER_TIMEOUT_SECONDS', '28')
set_key('AI_PROVIDER_ORDER', 'ollama')
set_key('AI_LOCAL_ONLY', '1')

for key in ('GROQ_API_KEY','GROQ_MODELS','GROQ_TRANSCRIBE_MODEL','HF_TOKEN','HUGGINGFACE_TOKEN','HF_MODELS','HF_VISION_MODEL'):
    text = re.sub(rf'(?m)^{re.escape(key)}=.*\n?', '', text)

path.write_text(text, encoding='utf-8')
PY
chmod 600 .env

"${dc[@]}" --profile ollama up -d --build --force-recreate kira ollama

echo "[OK] AI quality settings применены."
echo "В Telegram: /ai_reset, затем /ai_providers и /ai_health"
