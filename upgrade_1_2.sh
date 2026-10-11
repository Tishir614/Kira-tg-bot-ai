#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

[[ -f .env ]] || { echo '[ERROR] .env не найден. Сначала перенеси старый .env в папку Kira.' >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo '[ERROR] Docker не найден.' >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo '[ERROR] Docker Compose v2 не найден.' >&2; exit 1; }

BACKUP=".env.backup-1.2.0-$(date +%Y%m%d-%H%M%S)"
cp .env "$BACKUP"
chmod 600 "$BACKUP" .env

echo "[Kira 1.2] Резервная копия настроек: $BACKUP"

# Migrate only Kira's old stock image defaults. Custom user models are never overwritten.
python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit

path = Path('.env')
text = path.read_text('utf-8')
old_file = 'LOCAL_IMAGE_MODEL_FILE=v1-5-pruned-emaonly.safetensors'
old_url = 'LOCAL_IMAGE_MODEL_URL=https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.safetensors?download=true'
if old_file in text:
    text = text.replace(old_file, 'LOCAL_IMAGE_MODEL_FILE=v1-5-pruned_Q4_0.gguf')
if old_url in text:
    text = text.replace(old_url, 'LOCAL_IMAGE_MODEL_URL=https://huggingface.co/kostakoff/stable-diffusion-v1-5-GGUF/resolve/main/v1-5-pruned_Q4_0.gguf?download=true')

def has_key(key: str) -> bool:
    return any(line.split('=', 1)[0].strip() == key for line in text.splitlines() if '=' in line and not line.lstrip().startswith('#'))

additions = []
if not has_key('LOCAL_IMAGE_TIMEOUT'):
    additions.append('LOCAL_IMAGE_TIMEOUT=900')
if not has_key('LOCAL_IMAGE_THREADS'):
    additions.append('LOCAL_IMAGE_THREADS=4')

# Preserve old public /dnd URLs but derive the new all-in-one /kira URL when possible.
if not has_key('KIRA_WEBAPP_URL'):
    values = {}
    for line in text.splitlines():
        if '=' not in line or line.lstrip().startswith('#'):
            continue
        k, v = line.split('=', 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    source = values.get('DND_WEBAPP_URL', '') or values.get('HELP_URL', '')
    kira_url = ''
    if source.startswith('https://'):
        parts = urlsplit(source)
        kira_url = f'{parts.scheme}://{parts.netloc}/kira'
    additions.append('KIRA_WEBAPP_URL=' + kira_url)

if additions:
    text += ('' if text.endswith('\n') else '\n') + '\n# KiraBot 1.2 defaults\n' + '\n'.join(additions) + '\n'
path.write_text(text, 'utf-8')
PY
chmod 600 .env

echo '[Kira 1.2] Пересобираю Kira, локальный голос и генератор изображений…'
PROFILE_ARGS=(--profile voice --profile image)
if grep -Eq '^OLLAMA_BASE_URL=https?://ollama:' .env; then
  PROFILE_ARGS+=(--profile ollama)
fi

docker compose "${PROFILE_ARGS[@]}" up -d --build

echo '[Kira 1.2] Подготавливаю голоса Piper (best effort)…'
RU_VOICE="$(grep -E '^TTS_VOICE_RU=' .env | tail -1 | cut -d= -f2- || true)"
EN_VOICE="$(grep -E '^TTS_VOICE_EN=' .env | tail -1 | cut -d= -f2- || true)"
RU_VOICE="${RU_VOICE:-ru_RU-irina-medium}"
EN_VOICE="${EN_VOICE:-en_US-lessac-medium}"
docker compose exec -T kira uv run --no-dev python -m piper.download_voices \
  --data-dir /app/static/piper "$RU_VOICE" "$EN_VOICE" >/dev/null 2>&1 \
  || echo '[WARN] Голоса Piper не скачались заранее. Kira повторит загрузку при первой /озвучить.'

echo
echo '[Kira 1.2] Статус:'
docker compose ps

echo
echo '[OK] KiraBot 1.2.0 обновлён. Volumes, база, память и .env сохранены.'
echo '[TEST] Telegram: /картинка лиса ночью | /озвучить Привет | /днд | /косметика | /пол женский'
echo '[TEST] В группе: «Кира, кто дурак?»'
