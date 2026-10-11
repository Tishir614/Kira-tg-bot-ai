#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  RED=$'\033[1;31m'; GREEN=$'\033[1;32m'; YELLOW=$'\033[1;33m'; CYAN=$'\033[1;36m'; MAGENTA=$'\033[1;35m'; DIM=$'\033[2m'; NC=$'\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; CYAN=''; MAGENTA=''; DIM=''; NC=''
fi
log()  { printf "%s🦊 %s%s\n" "$CYAN" "$NC" "$*"; }
ok()   { printf "%s✔ %s%s\n" "$GREEN" "$NC" "$*"; }
warn() { printf "%s⚠ %s%s\n" "$YELLOW" "$NC" "$*"; }
die()  { printf "%s✖ %s%s\n" "$RED" "$NC" "$*" >&2; exit 1; }
step() { printf "\n%s━━ %s ━━%s\n" "$MAGENTA" "$*" "$NC"; }
ENV_TMP=""
cleanup() {
  if [[ -n "${ENV_TMP:-}" && -f "$ENV_TMP" ]]; then
    rm -f "$ENV_TMP"
  fi
}
trap cleanup EXIT
trap 'die "Ошибка на строке $LINENO. Посмотри вывод выше."' ERR

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  SUDO=()
else
  command -v sudo >/dev/null 2>&1 || die "Нужен sudo (или запусти скрипт от root)."
  SUDO=(sudo)
fi

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    return 0
  fi

  warn "Docker не найден. Устанавливаю его из репозитория системы."
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
  else
    die "Не удалось определить Linux-дистрибутив. Установи Docker вручную и снова запусти bash setup.sh"
  fi

  case "${ID:-}" in
    arch|manjaro|endeavouros)
      "${SUDO[@]}" pacman -Syu --needed --noconfirm docker docker-compose
      ;;
    ubuntu|debian|linuxmint|pop)
      "${SUDO[@]}" apt-get update
      "${SUDO[@]}" apt-get install -y docker.io ca-certificates curl
      if ! "${SUDO[@]}" apt-get install -y docker-compose-plugin; then
        "${SUDO[@]}" apt-get install -y docker-compose
      fi
      ;;
    fedora)
      "${SUDO[@]}" dnf install -y docker docker-compose
      ;;
    *)
      die "Автоустановка Docker пока не настроена для '${ID:-unknown}'. Установи Docker + Compose и повтори bash setup.sh"
      ;;
  esac
}

install_docker

if command -v systemctl >/dev/null 2>&1; then
  "${SUDO[@]}" systemctl enable --now docker || warn "Не смог включить docker.service через systemd."
fi

# Pick docker compose implementation and whether sudo is required.
DOCKER=()
if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif "${SUDO[@]}" docker info >/dev/null 2>&1; then
  DOCKER=("${SUDO[@]}" docker)
else
  die "Docker установлен, но daemon недоступен. Проверь: sudo systemctl status docker"
fi

if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  DC=("${DOCKER[@]}" compose)
elif command -v docker-compose >/dev/null 2>&1; then
  if docker-compose version >/dev/null 2>&1; then
    DC=(docker-compose)
  else
    DC=("${SUDO[@]}" docker-compose)
  fi
else
  die "Docker Compose не найден."
fi

ask_required() {
  local prompt="$1" var="$2" secret="${3:-0}" value=""
  while [[ -z "$value" ]]; do
    if [[ "$secret" == "1" ]]; then
      read -r -s -p "$prompt: " value < /dev/tty; printf '\n' > /dev/tty
    else
      read -r -p "$prompt: " value < /dev/tty
    fi
  done
  printf -v "$var" '%s' "$value"
}

ask_optional() {
  local prompt="$1" var="$2" secret="${3:-0}" value=""
  if [[ "$secret" == "1" ]]; then
    read -r -s -p "$prompt (Enter = пропустить): " value < /dev/tty; printf '\n' > /dev/tty
  else
    read -r -p "$prompt (Enter = пропустить): " value < /dev/tty
  fi
  printf -v "$var" '%s' "$value"
}

yesno() {
  local prompt="$1" default="${2:-N}" ans=""
  # KIRA_AUTO=1 (set by install.sh): never ask, take the default answer.
  if [[ "${KIRA_AUTO:-0}" == "1" ]]; then
    [[ "$default" =~ ^[Yy]$ ]]
    return
  fi
  local suffix="[y/N]"
  [[ "$default" =~ ^[Yy]$ ]] && suffix="[Y/n]"
  read -r -p "$prompt $suffix: " ans < /dev/tty
  [[ -z "$ans" ]] && ans="$default"
  [[ "$ans" =~ ^[YyДд]$ ]]
}

log "Мастер настройки KiraBot 0.8.0"
printf '\n'

# Reuse existing values safely when setup is re-run. Never `source` .env because it is data, not shell code.
env_get() {
  local key="$1" file="${2:-.env}" line=""
  [[ -f "$file" ]] || return 0
  line="$(grep -m1 -E "^${key}=" "$file" 2>/dev/null || true)"
  if [[ -n "$line" ]]; then
    printf '%s' "${line#*=}"
  fi
  return 0
}

# KIRA_KEEP_ENV=1 (set by install.sh when .env already exists): the file is used EXACTLY as it is.
# Nothing is asked, rewritten, merged or appended; services are chosen by reading the existing values.
if [[ "${KIRA_KEEP_ENV:-0}" == "1" && -f .env ]]; then
  [[ -n "$(env_get TOKEN)" ]] || die "В существующем .env нет TOKEN. Добавь TOKEN=... или запусти bash setup.sh для мастера."
  log "Использую существующий .env без изменений."
  OLLAMA_BASE_URL="$(env_get OLLAMA_BASE_URL)"
  OLLAMA_MODELS="$(env_get OLLAMA_MODELS)"
  [[ -n "$OLLAMA_MODELS" ]] || OLLAMA_MODELS="$(env_get OLLAMA_MODEL)"
  # Download every model the .env refers to (default chain, fast, smart), once each.
  _models=""
  for _m in ${OLLAMA_MODELS//,/ } "$(env_get OLLAMA_MODEL)" "$(env_get OLLAMA_FAST_MODEL)" "$(env_get OLLAMA_SMART_MODEL)"; do
    [[ -n "$_m" && ",$_models," != *",$_m,"* ]] && _models="${_models:+$_models,}$_m"
  done
  OLLAMA_MODELS="$_models"
  USE_OLLAMA=0
  if [[ "$OLLAMA_BASE_URL" == *"ollama:11434"* ]]; then USE_OLLAMA=1; fi   # Ollama внутри compose
  USE_LOCAL_IMAGE=0
  if [[ "$(env_get LOCAL_IMAGE_BASE_URL)" == *"comfyui"* ]]; then USE_LOCAL_IMAGE=1; fi
  ENABLE_PANEL=0
  [[ "$(env_get WEB_PANEL_ENABLED)" == "1" ]] && ENABLE_PANEL=1
else
EXISTING_ENV=0
if [[ -f .env ]]; then
  EXISTING_ENV=1
  BACKUP_NAME=".env.backup-$(date +%Y%m%d-%H%M%S)"
  warn ".env уже существует. Делаю резервную копию $BACKUP_NAME"
  cp .env "$BACKUP_NAME"

  # Upgrade only untouched historical AI defaults. Custom user values are never overwritten.
  sed -i \
    -e 's/^OLLAMA_MODEL=qwen3:1.7b$/OLLAMA_MODEL=qwen3.5:2b-q4_K_M/' \
    -e 's/^OLLAMA_MODELS=qwen3:1.7b,llama3.2:3b$/OLLAMA_MODELS=qwen3.5:2b-q4_K_M,qwen3:1.7b/' \
    -e 's/^OLLAMA_MODEL=qwen2.5:3b$/OLLAMA_MODEL=qwen3.5:2b-q4_K_M/' \
    -e 's/^OLLAMA_MODELS=qwen2.5:3b,qwen3:1.7b$/OLLAMA_MODELS=qwen3.5:2b-q4_K_M,qwen3:1.7b/' \
    -e 's/^AI_HISTORY_MESSAGES=5$/AI_HISTORY_MESSAGES=10/' \
    -e 's/^AI_HISTORY_MAX_CHARS=6000$/AI_HISTORY_MAX_CHARS=10000/' \
    -e 's/^AI_TEMPERATURE=0.45$/AI_TEMPERATURE=0.32/' \
    -e 's/^AI_MAX_RESPONSE_TOKENS=700$/AI_MAX_RESPONSE_TOKENS=950/' \
    .env
fi

TOKEN="${TOKEN:-$(env_get TOKEN)}"
OWNER_ID="${OWNER_ID:-$(env_get OWNER_ID)}"
AUDD_API_TOKEN="${AUDD_API_TOKEN:-$(env_get AUDD_API_TOKEN)}"
API_ID="${API_ID:-$(env_get API_ID)}"
API_HASH="${API_HASH:-$(env_get API_HASH)}"
BOT_TIMEZONE="${BOT_TIMEZONE:-$(env_get BOT_TIMEZONE)}"
BOT_TIMEZONE="${BOT_TIMEZONE:-Europe/Vilnius}"

printf '
%bШаг 1/4 — Telegram%b
' "$CYAN" "$NC"
log "Нужен токен бота от @BotFather. Вставь его в следующем поле и нажми Enter."
log "Ввод скрыт: токен не будет показан на экране."

if [[ -n "$TOKEN" && "$EXISTING_ENV" -eq 1 ]]; then
  if yesno "В .env уже есть TOKEN. Оставить сохранённый токен?" Y; then
    ok "Использую сохранённый TOKEN."
  else
    TOKEN=""
  fi
fi

while [[ -z "$TOKEN" ]]; do
  ask_required "Вставь Telegram BOT TOKEN" TOKEN 1
  if [[ ! "$TOKEN" =~ ^[0-9]{5,}:[A-Za-z0-9_-]{20,}$ ]]; then
    warn "Токен выглядит необычно. Обычно он похож на 123456789:AA..."
    if ! yesno "Всё равно сохранить этот токен?" N; then
      TOKEN=""
    fi
  fi
done

if [[ -n "$OWNER_ID" && "$EXISTING_ENV" -eq 1 ]]; then
  if yesno "Оставить сохранённый OWNER_ID=$OWNER_ID?" Y; then
    :
  else
    OWNER_ID=""
  fi
fi
[[ -n "$OWNER_ID" ]] || ask_required "Твой Telegram user ID (OWNER_ID)" OWNER_ID 0
[[ "$OWNER_ID" =~ ^[0-9]+$ ]] || die "OWNER_ID должен быть числом."
ok "Telegram-настройки приняты. TOKEN будет сохранён в защищённый .env."

printf '
%bШаг 2/4 — локальный AI%b: без Groq/Hugging Face/Gemini и без API-ключей.
' "$CYAN" "$NC"
USE_OLLAMA=1
ok "AI будет работать только локально через Ollama."
log "Цепочка: qwen3.5:2b-q4_K_M → qwen3:1.7b. Вторая модель запускается только если первая не справилась."

USE_LOCAL_IMAGE=0
# In auto mode the free online generators (AI Horde/Perchance) are used; the 4.3 GB local
# ComfyUI model is installed only on request: KIRA_LOCAL_IMAGE=1.
if { [[ "${KIRA_AUTO:-0}" == "1" ]] && [[ "${KIRA_LOCAL_IMAGE:-0}" == "1" ]]; } || \
   { [[ "${KIRA_AUTO:-0}" != "1" ]] && yesno "Включить локальную генерацию изображений? Без API-ключей, модель ~4.3 ГБ; на CPU генерация может занять минуты" Y; }; then
  FREE_KB="$(df -Pk . 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)"
  FREE_GB=$(( FREE_KB / 1024 / 1024 ))
  if (( FREE_GB < 8 )); then
    warn "Свободно около ${FREE_GB} ГБ. Для модели и сборки нужно желательно 8+ ГБ. Локальные картинки пока отключаю."
  else
    MEM_KB_IMAGE="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
    MEM_GB_IMAGE=$(( MEM_KB_IMAGE / 1024 / 1024 ))
    if (( MEM_GB_IMAGE < 6 )); then
      warn "RAM около ${MEM_GB_IMAGE} ГБ: SD 1.5 на CPU может работать очень медленно или упасть по памяти."
    fi
    USE_LOCAL_IMAGE=1
    ok "Локальная генерация включена. Модель скачается один раз и останется в Docker volume."
  fi
fi
log "Озвучка теперь всегда локальная: Piper TTS, API-ключ не нужен."

printf '\n%bШаг 3/4 — дополнительные интеграции%b\n' "$CYAN" "$NC"
if yesno "Настроить дополнительные интеграции (AudD/Pyrogram)?" N; then
  ask_optional "AUDD_API_TOKEN для распознавания музыки" AUDD_API_TOKEN 1
  ask_optional "Telegram API_ID для Pyrogram" API_ID 0
  ask_optional "Telegram API_HASH для Pyrogram" API_HASH 1
fi

printf '\n%bШаг 4/4 — запуск%b\n' "$CYAN" "$NC"
ENABLE_PANEL=0
PANEL_TOKEN=""
if yesno "Включить локальную web-панель администратора?" N; then
  ENABLE_PANEL=1
  if command -v openssl >/dev/null 2>&1; then
    PANEL_TOKEN="$(openssl rand -hex 32)"
  else
    PANEL_TOKEN="$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)"
  fi
fi

OLLAMA_BASE_URL=""
OLLAMA_MODEL="qwen3.5:2b-q4_K_M"
OLLAMA_FAST_MODEL="qwen3.5:2b-q4_K_M"
OLLAMA_SMART_MODEL=""
OLLAMA_MODELS="qwen3.5:2b-q4_K_M,qwen3:1.7b"
AI_PROVIDER_ORDER="ollama"
if [[ "$USE_OLLAMA" -eq 1 ]]; then
  MEM_KB="$(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  MEM_GB=$(( MEM_KB / 1024 / 1024 ))
  OLLAMA_BASE_URL="http://ollama:11434"
  if (( MEM_GB >= 6 )); then
    OLLAMA_SMART_MODEL="qwen3.5:4b"
    OLLAMA_MODELS="qwen3.5:2b-q4_K_M,qwen3.5:4b,qwen3:1.7b"
    ok "Adaptive AI: 2B для быстрых вопросов, 4B для сложных. В RAM держится только одна модель."
  else
    OLLAMA_SMART_MODEL="$OLLAMA_FAST_MODEL"
    warn "RAM около ${MEM_GB} ГБ: оба маршрута используют Qwen3.5 2B, чтобы VPS не ушёл в swap."
  fi
fi

LOCAL_IMAGE_BASE_URL=""
if [[ "$USE_LOCAL_IMAGE" -eq 1 ]]; then
  LOCAL_IMAGE_BASE_URL="http://comfyui:8188"
fi

umask 077
ENV_TMP=".env.tmp.$$"
cat > "$ENV_TMP" <<EOF_ENV
# Generated by KiraBot setup.sh
TOKEN=$TOKEN
OWNER_ID=$OWNER_ID
SUPPORT_CHAT_ID=@kira26481
API_ID=$API_ID
API_HASH=$API_HASH
BOT_TIMEZONE=$BOT_TIMEZONE
DATA_DIR=static

LOG_LEVEL=INFO
LOG_TO_FILE=1
LOG_RETENTION_DAYS=14
REQUEST_LIMIT=30
REQUEST_WINDOW_SECONDS=10
MAX_CONCURRENT_AI=4
MAX_CONCURRENT_DOWNLOADS=3
FILE_ANALYSIS_MAX_MB=20
FSM_REDIS_URL=redis://redis:6379/0
BACKUP_INTERVAL_HOURS=24
BACKUP_KEEP=7

AI_LOCAL_ONLY=1
OLLAMA_BASE_URL=$OLLAMA_BASE_URL
OLLAMA_MODEL=$OLLAMA_MODEL
OLLAMA_FAST_MODEL=$OLLAMA_FAST_MODEL
OLLAMA_SMART_MODEL=$OLLAMA_SMART_MODEL
OLLAMA_MODELS=$OLLAMA_MODELS
OLLAMA_KEEP_ALIVE=10m
OLLAMA_NUM_CTX=4096
AI_ADAPTIVE_ROUTING=1
AI_PROVIDER_COOLDOWN_SECONDS=60
AI_PROVIDER_TIMEOUT_SECONDS=28
AI_PROVIDER_ORDER=$AI_PROVIDER_ORDER
AI_QUALITY_FIRST=1
AI_FAST_MODE=1
AI_SMART_DIALOGUE=1
AI_DELIBERATE_MODE=1
AI_REVIEW_PASS=0
AI_HISTORY_MESSAGES=10
AI_HISTORY_MAX_CHARS=10000
AI_TEMPERATURE=0.32
AI_CREATIVE_TEMPERATURE=0.72
AI_RESEARCH_TEMPERATURE=0.25
AI_MAX_RESPONSE_TOKENS=1100

TTS_VOICE_RU=ru_RU-irina-medium
TTS_VOICE_EN=en_US-lessac-medium
PIPER_DATA_DIR=/app/static/piper

LOCAL_STT_BASE_URL=http://local-stt:8080
LOCAL_STT_MODEL_FILE=ggml-base.bin
LOCAL_STT_MODEL_URL=https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin?download=true
LOCAL_STT_THREADS=4
LOCAL_STT_LANGUAGE=auto

LOCAL_IMAGE_BASE_URL=$LOCAL_IMAGE_BASE_URL
COMFYUI_CHECKPOINT=DreamShaper_8_pruned.safetensors
COMFYUI_MODEL_URL=https://huggingface.co/Lykon/DreamShaper/resolve/main/DreamShaper_8_pruned.safetensors?download=true
LOCAL_IMAGE_WIDTH=512
LOCAL_IMAGE_HEIGHT=512
LOCAL_IMAGE_STEPS=20
LOCAL_IMAGE_CFG_SCALE=7.0
LOCAL_IMAGE_CONCURRENCY=1
LOCAL_IMAGE_THREADS=4
LOCAL_IMAGE_TIMEOUT=900

AUDD_API_TOKEN=$AUDD_API_TOKEN

INTERNET_MAX_DOWNLOAD_MB=49
MEDIA_MAX_DOWNLOAD_MB=49
BOT_API_BASE_URL=

WEB_PANEL_ENABLED=$ENABLE_PANEL
WEB_PANEL_HOST=0.0.0.0
WEB_PANEL_PORT=8080
PANEL_TOKEN=$PANEL_TOKEN
KIRA_WEBAPP_URL=
EOF_ENV
python3 tools/merge_env.py .env "$ENV_TMP"
chmod 600 "$ENV_TMP"
mv -f "$ENV_TMP" .env
ENV_TMP=""
chmod 600 .env
# Add newer defaults (image providers, AI Horde, anti-hang limits...) without touching existing lines.
if [[ -f example.env ]]; then
  ENV_TMP=".env.tmp.$$"
  cp example.env "$ENV_TMP"
  python3 tools/merge_env.py .env "$ENV_TMP"
  chmod 600 "$ENV_TMP"
  mv -f "$ENV_TMP" .env
  ENV_TMP=""
fi
ok ".env создан и TOKEN сохранён. Права файла: 600 (только владелец)."

fi

step "Скачиваю образы Docker"
log "Проверяю Docker-образы..."
# Use supported generic Redis 8 Alpine tag. redis:8.1-alpine no longer exists.
"${DOCKER[@]}" pull redis:8-alpine

if [[ "$USE_OLLAMA" -eq 1 ]]; then
  if ! "${DOCKER[@]}" pull ollama/ollama:0.34.1; then
    warn "Ollama image не скачался. Не останавливаю установку: запускаю Kira без локального AI."
    USE_OLLAMA=0
    OLLAMA_BASE_URL=""
    warn "Локальный AI останется недоступен, пока Ollama не будет установлен и запущен."
  fi
fi

step "Собираю и запускаю сервисы"
log "Собираю и запускаю сервисы..."
PROFILE_ARGS=(--profile voice)
if [[ "$USE_OLLAMA" -eq 1 ]]; then
  PROFILE_ARGS+=(--profile ollama)
fi
if [[ "$USE_LOCAL_IMAGE" -eq 1 ]]; then
  PROFILE_ARGS+=(--profile image)
fi

"${DC[@]}" "${PROFILE_ARGS[@]}" up -d --build

if [[ "$USE_OLLAMA" -eq 1 ]]; then
  step "Скачиваю модели ИИ"
  log "Скачиваю локальные модели на диск: $OLLAMA_MODELS (в RAM они будут запускаться строго по очереди)"
  ADULT_MODEL="$(env_get OLLAMA_ADULT_MODEL)"   # отдельная модель для 18+/RP, если задана в .env
  if [[ -n "$ADULT_MODEL" ]]; then OLLAMA_MODELS="$OLLAMA_MODELS,$ADULT_MODEL"; fi
  IFS=',' read -r -a OLLAMA_MODEL_LIST <<< "$OLLAMA_MODELS"
  PULLED_ANY=0
  for MODEL in "${OLLAMA_MODEL_LIST[@]}"; do
    MODEL="${MODEL// /}"
    [[ -n "$MODEL" ]] || continue
    if "${DC[@]}" --profile ollama exec -T ollama ollama pull "$MODEL"; then
      PULLED_ANY=1
      ok "Ollama модель готова: $MODEL"
    else
      warn "Не удалось скачать $MODEL. Попробую остальные fallback-модели."
    fi
  done
  if [[ "$PULLED_ANY" -eq 0 ]]; then
    warn "Ни одна Ollama-модель не скачалась. AI_LOCAL_ONLY=1 не позволит незаметно уйти в облачный API; повтори ai_quality.sh после проверки сети/Ollama."
  fi
fi

step "Голос и распознавание речи"
log "Готовлю локальные голоса Piper (~120 МБ суммарно, скачиваются один раз)..."
if "${DC[@]}" exec -T kira uv run --no-dev python -m piper.download_voices \
    --data-dir /app/static/piper ru_RU-irina-medium en_US-lessac-medium >/dev/null 2>&1 \
  && "${DC[@]}" exec -T kira uv run --no-dev python -m piper \
    -m ru_RU-irina-medium \
    --data-dir /app/static/piper \
    -f /tmp/kira-piper-check.wav -- 'Привет, это Кира.' >/dev/null 2>&1; then
  ok "Piper TTS готов и работает полностью локально."
else
  warn "Piper не удалось прогреть сейчас. Бот продолжит работу; первая команда /tts попробует скачать голос снова."
fi

if [[ "$USE_LOCAL_IMAGE" -eq 1 ]]; then
  log "Проверяю локальный генератор изображений..."
  if "${DC[@]}" --profile image ps comfyui 2>/dev/null | grep -Eq 'Up|running|healthy'; then
    ok "ComfyUI запущен. Первый рендер на CPU может быть медленным."
  else
    warn "ComfyUI ещё запускается или модель продолжает загружаться. Смотри: docker compose --profile image logs -f comfyui-model comfyui"
  fi
fi

printf '\n'
"${DC[@]}" ps
printf '\n'
# Give the bot a moment to authenticate, then catch the most common bad-token failure.
sleep 3
STARTUP_LOGS="$("${DC[@]}" logs --no-color --tail 80 kira 2>/dev/null || true)"
if grep -Eqi 'Unauthorized|Token is invalid|TelegramUnauthorizedError|invalid token|bot token' <<<"$STARTUP_LOGS"; then
  warn "Telegram отклонил TOKEN. Исправить просто: снова запусти bash setup.sh и вставь новый токен."
  "${DC[@]}" ps
  exit 2
fi

ok "KiraBot запущен. Telegram TOKEN сохранён в .env и используется контейнером."
log "Логи: ${DC[*]} logs -f kira"
log "Остановка: ${DC[*]} down"
log "После запуска отправь боту: /doctor full"
if [[ "$ENABLE_PANEL" -eq 1 ]]; then
  warn "Web-панель включена только внутри контейнера/локальной сети Docker. PANEL_TOKEN сохранён в .env и намеренно не выводится."
fi
