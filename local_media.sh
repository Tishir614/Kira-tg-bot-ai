#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

[[ -f .env ]] || { echo '[ERROR] .env не найден. Сначала запусти bash setup.sh'; exit 1; }
command -v docker >/dev/null 2>&1 || { echo '[ERROR] Docker не найден.'; exit 1; }

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
else
  echo '[ERROR] Docker daemon недоступен.' >&2
  exit 1
fi

if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  DC=("${DOCKER[@]}" compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo '[ERROR] Docker Compose не найден.' >&2
  exit 1
fi

set_env() {
  local key="$1" value="$2"
  python3 - "$key" "$value" <<'PY'
from pathlib import Path
import re, sys
p=Path('.env')
key, value=sys.argv[1:3]
text=p.read_text(encoding='utf-8')
line=f'{key}={value}'
pat=re.compile(rf'^{re.escape(key)}=.*$', re.M)
if pat.search(text):
    text=pat.sub(line, text, count=1)
else:
    text += ('' if text.endswith('\n') else '\n') + line + '\n'
p.write_text(text, encoding='utf-8')
PY
}

FREE_KB="$(df -Pk . | awk 'NR==2 {print $4}')"
FREE_GB=$(( FREE_KB / 1024 / 1024 ))
if (( FREE_GB < 8 )); then
  echo "[ERROR] Свободно около ${FREE_GB} ГБ. Для локальной модели изображений нужно желательно 8+ ГБ." >&2
  exit 1
fi

cp .env ".env.backup-local-media-$(date +%Y%m%d-%H%M%S)"
chmod 600 .env

set_env TTS_VOICE_RU ru_RU-irina-medium
set_env TTS_VOICE_EN en_US-lessac-medium
set_env PIPER_DATA_DIR /app/static/piper
set_env LOCAL_STT_BASE_URL http://local-stt:8080
set_env LOCAL_STT_MODEL_FILE ggml-base.bin
set_env LOCAL_STT_MODEL_URL https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin?download=true
set_env LOCAL_STT_THREADS 4
set_env LOCAL_STT_LANGUAGE auto
set_env LOCAL_IMAGE_BASE_URL http://comfyui:8188
set_env COMFYUI_CHECKPOINT DreamShaper_8_pruned.safetensors
set_env COMFYUI_MODEL_URL 'https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors?download=true'
set_env LOCAL_IMAGE_WIDTH 512
set_env LOCAL_IMAGE_HEIGHT 512
set_env LOCAL_IMAGE_STEPS 20
set_env LOCAL_IMAGE_CFG_SCALE 7.0
set_env LOCAL_IMAGE_CONCURRENCY 1
set_env LOCAL_IMAGE_THREADS 4
chmod 600 .env

echo '[Kira] Собираю Kira + локальный ComfyUI...'
"${DC[@]}" --profile image --profile voice up -d --build

echo '[Kira] Скачиваю локальные голоса Piper (один раз, без API-ключей)...'
"${DC[@]}" exec -T kira uv run --no-dev python -m piper.download_voices \
  --data-dir /app/static/piper ru_RU-irina-medium en_US-lessac-medium

printf 'Привет, это Кира. Локальная озвучка работает.\n' | "${DC[@]}" exec -T kira uv run --no-dev piper \
  --model ru_RU-irina-medium \
  --data-dir /app/static/piper \
  --output_file /tmp/kira-piper-check.wav >/dev/null

echo
"${DC[@]}" ps
echo
echo '[OK] Локальные TTS, STT и генерация изображений настроены.'
echo '[INFO] Модель изображений ~4.3 ГБ. Если она ещё качается:'
echo 'docker compose --profile image logs -f comfyui-model comfyui'
echo '[INFO] В Telegram проверь: /tts Привет, /summary_voice и /image фурри лиса ночью'
