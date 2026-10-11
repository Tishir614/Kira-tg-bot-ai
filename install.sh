#!/usr/bin/env bash
# KiraBot — установка одной командой: ставит всё нужное и скачивает всё, что боту нужно для работы.
#
#   git clone https://github.com/Tishir614/Kira-tg-bot-ai.git && cd Kira-tg-bot-ai && bash install.sh
#   bash install.sh --plan                       — только показать, что будет установлено и скачано
#   TOKEN=123:ABC OWNER_ID=12345 bash install.sh — без вопросов
#
# Что скачивается: Docker + Compose, образы (бот, Redis, Ollama, голос/распознавание), локальные
# модели ИИ (быстрая, умная при RAM ≥ 6 ГБ, 18+ если задана OLLAMA_ADULT_MODEL), голоса Piper,
# модель распознавания речи Whisper и — если хватает диска и памяти — локальный генератор картинок ComfyUI.
#
# Переменные (необязательно): REPO_URL, DIR, BRANCH,
#   KIRA_LOCAL_IMAGE=auto|1|0   (auto: ставить ComfyUI только на мощном сервере; по умолчанию auto)
# Существующий .env используется КАК ЕСТЬ: не переписывается и не дополняется (рядом кладётся копия).
set -Eeuo pipefail
umask 077

REPO_URL="${REPO_URL:-https://github.com/Tishir614/Kira-tg-bot-ai.git}"
BRANCH="${BRANCH:-main}"
PLAN_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --plan) PLAN_ONLY=1 ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'Неизвестный параметр: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

# ---------- оформление ----------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  R=$'\033[1;31m'; G=$'\033[1;32m'; Y=$'\033[1;33m'; C=$'\033[1;36m'; M=$'\033[1;35m'; B=$'\033[1m'; D=$'\033[2m'; N=$'\033[0m'
else
  R=''; G=''; Y=''; C=''; M=''; B=''; D=''; N=''
fi
STEP=0; TOTAL=5
say()  { printf '%s🦊%s %s\n' "$C" "$N" "$*"; }
ok()   { printf '%s✔%s %s\n' "$G" "$N" "$*"; }
warn() { printf '%s⚠%s %s\n' "$Y" "$N" "$*"; }
die()  { printf '%s✖%s %s\n' "$R" "$N" "$*" >&2; exit 1; }
bar()  { # bar <done> <total> : ██████░░░░
  local d=$1 t=$2 w=20 f i out=''; f=$(( d * w / t ))
  for ((i = 0; i < w; i++)); do if ((i < f)); then out+='█'; else out+='░'; fi; done; printf '%s' "$out"
}
step() { STEP=$((STEP + 1)); printf '\n%s━━ [%d/%d] %s%s %s\n' "$M" "$STEP" "$TOTAL" "$(bar "$STEP" "$TOTAL")" "$N" "$*"; }
banner() {
  printf '%s' "$M"
  cat <<'ART'
   ╔═══════════════════════════════════════╗
   ║   /\_/\    K I R A B O T             ║
   ║  ( o.o )   установщик «всё включено» ║
   ║   > ^ <                              ║
   ╚═══════════════════════════════════════╝
ART
  printf '%s' "$N"
}
spin() { # spin "сообщение" команда... : анимация, вывод — в лог, при ошибке показывает хвост
  local msg="$1"; shift
  local log; log="$(mktemp)"
  "$@" >"$log" 2>&1 &
  local pid=$! i=0 frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  if [[ -t 1 ]]; then
    while kill -0 "$pid" 2>/dev/null; do
      printf '\r%s%s%s %s' "$C" "${frames:i++%${#frames}:1}" "$N" "$msg"; sleep 0.1
    done
    printf '\r\033[K'
  fi
  if wait "$pid"; then ok "$msg"; rm -f "$log"; else
    printf '%s✖%s %s — ошибка:\n' "$R" "$N" "$msg" >&2; tail -n 15 "$log" >&2; rm -f "$log"; return 1
  fi
}

banner
trap 'die "Ошибка на строке $LINENO. Ничего не удалено; после исправления просто запусти install.sh ещё раз."' ERR
[[ "$(uname -s)" == "Linux" ]] || die "Установщик рассчитан на Linux-сервер (Ubuntu/Debian/Fedora/Arch)."

# ---------- железо и план ----------
MEM_GB=$(( $(awk '/MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1024 / 1024 ))
CPUS="$(nproc 2>/dev/null || echo 1)"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$PWD/x}")" && pwd)"
DISK_PATH="$SCRIPT_DIR"; [[ -d /var/lib/docker ]] && DISK_PATH=/var/lib/docker
FREE_GB=$(( $(df -Pk "$DISK_PATH" 2>/dev/null | awk 'NR==2 {print $4}' || echo 0) / 1024 / 1024 ))
# shellcheck disable=SC1091
OS_NAME="$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-Linux}" || echo Linux)"

LOCAL_IMAGE="${KIRA_LOCAL_IMAGE:-auto}"
if [[ "$LOCAL_IMAGE" == "auto" ]]; then
  if (( MEM_GB >= 6 && FREE_GB >= 25 )); then LOCAL_IMAGE=1; else LOCAL_IMAGE=0; fi
fi
SMART_MODEL=0; (( MEM_GB >= 6 )) && SMART_MODEL=1
NEED_GB=9; (( SMART_MODEL )) && NEED_GB=$((NEED_GB + 4)); [[ "$LOCAL_IMAGE" == 1 ]] && NEED_GB=$((NEED_GB + 9))

printf '\n%sСервер:%s %s · %d CPU · %d ГБ RAM · свободно %d ГБ\n' "$B" "$N" "$OS_NAME" "$CPUS" "$MEM_GB" "$FREE_GB"
printf '%sПлан установки%s\n' "$B" "$N"
plan_line() { printf '  %s•%s %s %s— %s%s\n' "$C" "$N" "$1" "$D" "$2" "$N"; }
plan_line "Docker + Compose, git, curl"      "если ещё не установлены"
plan_line "Бот, Redis, Ollama (образы)"       "≈ 3 ГБ"
plan_line "ИИ: быстрая модель Qwen3.5 2B"     "≈ 2 ГБ"
if (( SMART_MODEL )); then plan_line "ИИ: умная модель Qwen3.5 4B" "≈ 3.5 ГБ (RAM ≥ 6 ГБ)"; else plan_line "ИИ: умная модель" "пропуск (мало RAM, хватит быстрой)"; fi
plan_line "ИИ: запасная Qwen3 1.7B"           "≈ 1.4 ГБ"
plan_line "ИИ для 18+ (OLLAMA_ADULT_MODEL)"   "если задана в .env"
plan_line "Голоса Piper + Whisper"            "≈ 0.3 ГБ"
if [[ "$LOCAL_IMAGE" == 1 ]]; then plan_line "Генератор картинок ComfyUI" "≈ 8 ГБ (локально)"; else plan_line "Картинки" "онлайн: AI Horde / Perchance (ComfyUI пропущен)"; fi
printf '  %sИтого свободного места нужно ≈ %d ГБ, сейчас %d ГБ%s\n' "$D" "$NEED_GB" "$FREE_GB" "$N"
if [[ -f "$SCRIPT_DIR/.env" ]]; then printf '  %s.env найден — будет использован как есть, без изменений%s\n' "$G" "$N"; fi
(( FREE_GB >= NEED_GB )) || warn "Свободного места меньше рекомендуемого (${FREE_GB} < ${NEED_GB} ГБ): установка может не поместиться."

if (( PLAN_ONLY )); then
  say "Режим --plan: ничего не устанавливалось. Запусти без --plan, чтобы начать."
  exit 0
fi
if (( FREE_GB > 0 && FREE_GB < 6 )); then die "Свободно только ${FREE_GB} ГБ — даже базовая установка не поместится. Освободи место."; fi

if [[ ${EUID:-$(id -u)} -eq 0 ]]; then SUDO=(); else
  command -v sudo >/dev/null 2>&1 || die "Нужен root или sudo."
  SUDO=(sudo)
fi

# ---------- 1. пакеты ----------
step "Базовые пакеты"
need=()
for tool in git curl python3; do command -v "$tool" >/dev/null 2>&1 || need+=("$tool"); done
if ((${#need[@]})); then
  # shellcheck disable=SC1091
  . /etc/os-release 2>/dev/null || true
  case "${ID:-}" in
    ubuntu|debian|linuxmint|pop) spin "Устанавливаю ${need[*]}" bash -c "${SUDO[*]:-} apt-get update -y && ${SUDO[*]:-} apt-get install -y ${need[*]} ca-certificates" ;;
    fedora)                      spin "Устанавливаю ${need[*]}" "${SUDO[@]}" dnf install -y "${need[@]}" ;;
    arch|manjaro|endeavouros)    spin "Устанавливаю ${need[*]}" "${SUDO[@]}" pacman -Sy --needed --noconfirm "${need[@]}" ;;
    *) die "Не знаю, как поставить ${need[*]} в '${ID:-unknown}'. Установи вручную и повтори." ;;
  esac
else
  ok "git, curl и python3 уже установлены"
fi

# ---------- 2. код ----------
step "Код проекта"
if [[ -f "$SCRIPT_DIR/setup.sh" && -d "$SCRIPT_DIR/bot" ]]; then
  PROJECT_DIR="$SCRIPT_DIR"
  if [[ -d "$PROJECT_DIR/.git" && -z "$(git -C "$PROJECT_DIR" status --porcelain --untracked-files=no)" ]]; then
    spin "Обновляю код (.env и данные не затрагиваются)" git -C "$PROJECT_DIR" pull --ff-only origin "$BRANCH" \
      || warn "Не удалось обновить код — продолжаю с текущей версией."
  else
    ok "Использую код из текущей папки"
  fi
else
  PROJECT_DIR="${DIR:-$HOME/Kira-tg-bot-ai}"
  if [[ -d "$PROJECT_DIR/.git" ]]; then
    spin "Обновляю $PROJECT_DIR" git -C "$PROJECT_DIR" pull --ff-only origin "$BRANCH" \
      || warn "Не удалось обновить код — продолжаю с текущей версией."
  else
    spin "Скачиваю бота в $PROJECT_DIR" git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR" \
      || die "Не удалось клонировать $REPO_URL (приватный репозиторий? нужен токен доступа или deploy key)."
  fi
fi
cd "$PROJECT_DIR"

# ---------- 3. ключи ----------
step "Ключи и настройки"
if [[ -f .env ]]; then
  cp -p .env ".env.backup-$(date +%Y%m%d-%H%M%S)"
  [[ "$(stat -c %a .env 2>/dev/null || echo 600)" =~ ^[0-7]00$ ]] || warn "У .env открытые права доступа (рекомендуется chmod 600 .env) — я их не меняю."
  ls -1t .env.backup-* 2>/dev/null | tail -n +11 | xargs -r rm -f
  export KIRA_KEEP_ENV=1
  ok "Найден .env — используется как есть (копия сохранена рядом)"
else
  say "Файла .env ещё нет: понадобятся только токен бота (@BotFather) и ваш Telegram ID."
fi

# ---------- 4. Docker, образы, модели ----------
step "Docker, образы и модели (самый долгий шаг)"
export KIRA_AUTO=1 KIRA_LOCAL_IMAGE="$LOCAL_IMAGE"
say "Первый запуск обычно занимает 10–30 минут: скачиваются образы и модели ИИ."
bash ./setup.sh

# ---------- 5. итог ----------
step "Готово"
printf '%s' "$G"
cat <<'DONE'
   ╔═══════════════════════════════════════╗
   ║   🦊  Кира установлена и запущена!    ║
   ╚═══════════════════════════════════════╝
DONE
printf '%s' "$N"
printf '  %sСтатус:%s      docker compose ps\n' "$B" "$N"
printf '  %sЛоги:%s        docker compose logs -f kira\n' "$B" "$N"
printf '  %sВ Telegram:%s  /помощь · /status · /ai_health\n' "$B" "$N"
printf '  %sОбновление:%s  bash deploy.sh        %sHTTPS:%s bash https.sh домен почта\n' "$B" "$N" "$B" "$N"
