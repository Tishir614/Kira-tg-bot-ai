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
# Существующий .env ищется автоматически (текущая папка, папка запущенной Киры, типичные места, ENV_FILE=…)
# и используется КАК ЕСТЬ: без вопросов, не переписывается и не дополняется (рядом кладётся копия).
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

# ---------- 3. ключи: найти уже существующий .env и использовать его ----------
step "Ключи и настройки"
# Токен Telegram: допускаем пробелы/кавычки вокруг значения. Формат 123456789:AA… проверяем строго.
has_token() { [[ -r "$1" && -f "$1" ]] && grep -Eq "^[[:space:]]*TOKEN[[:space:]]*=[[:space:]]*[\"']?[0-9]{5,}:[A-Za-z0-9_-]{20,}" "$1" 2>/dev/null; }

# Ищет рабочий .env по шагам: от дешёвых мест к глубокому поиску по всему серверу. Файлы только читаются.
find_env_file() {
  local cand c id wd pid
  local -a list=()
  # 1) явный путь, текущая папка, папка запущенного контейнера Киры
  [[ -n "${ENV_FILE:-}" ]] && list+=("$ENV_FILE")
  list+=("$PWD/.env")
  if command -v docker >/dev/null 2>&1; then
    for id in $(docker ps -aq --filter label=com.docker.compose.service=kira 2>/dev/null | head -3); do
      wd="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$id" 2>/dev/null || true)"
      [[ -n "$wd" ]] && list+=("$wd/.env")
    done
  fi
  # 2) папка работающего процесса бота (python -m bot без Docker)
  for pid in $(pgrep -f 'python.*(-m bot|bot/__main__|uv run.*bot)' 2>/dev/null | head -5); do
    [[ -e "/proc/$pid/cwd" ]] && list+=("$(readlink -f "/proc/$pid/cwd" 2>/dev/null)/.env")
  done
  # 3) типичные места прошлых установок
  list+=("$HOME/Kira-tg-bot-ai/.env" "$HOME"/[Kk]ira*/.env "$HOME"/[Kk]ira*/*/.env "$PWD"/../[Kk]ira*/.env
         /opt/[Kk]ira*/.env /srv/[Kk]ira*/.env /root/[Kk]ira*/.env /home/*/[Kk]ira*/.env /home/*/*/[Kk]ira*/.env)
  for cand in "${list[@]}"; do
    for c in $cand; do
      if has_token "$c"; then printf '%s' "$(cd "$(dirname "$c")" && pwd)/$(basename "$c")"; return 0; fi
    done
  done
  # 4) глубокий поиск по серверу: любой .env / *.env / .env.* с токеном; сначала обычные, потом резервные копии, новее — раньше
  say "Ищу .env по всему серверу (до 40 секунд)…" >&2
  local roots="${KIRA_ENV_SEARCH_ROOTS:-}" found="" d
  if [[ -z "$roots" ]]; then
    for d in /root /home /opt /srv /var /usr/local /data /mnt /media /storage /app /www /workspace; do [[ -d "$d" ]] && roots+="$d "; done
  fi
  # shellcheck disable=SC2086
  found="$(timeout 40 find $roots -maxdepth 8 \
      \( -path /proc -o -path /sys -o -path /dev -o -path /usr/lib -o -path /usr/share -o -path /var/lib/docker \
         -o -path '*/node_modules' -o -path '*/.venv' -o -path '*/venv' -o -path '*/site-packages' -o -path '*/.git' \) -prune -o \
      -type f \( -name '.env' -o -name '*.env' -o -name '.env.*' \) -size -64k -printf '%T@ %p\n' 2>/dev/null | sort -rn | cut -d' ' -f2- || true)"
  # Не угадываем вслепую: сервер может хранить .env других ботов. Сначала файлы, похожие на настройки Киры.
  local backups="" kira_like="" others=() n_other=0
  while IFS= read -r c; do
    [[ -n "$c" && "$c" != "$PWD/.env."* && "$c" != *"/example.env" ]] || continue
    has_token "$c" || continue
    if [[ "$(basename "$c")" == .env.backup* || "$(basename "$c")" == *.bak ]]; then backups="${backups:-$c}"; continue; fi
    if grep -Eq '^(OLLAMA_|AI_LOCAL_ONLY|AI_PROVIDER_ORDER|KIRA_|SUPPORT_CHAT_ID|PANEL_TOKEN|FSM_REDIS_URL|WEB_PANEL_)' "$c" 2>/dev/null \
       || [[ -d "$(dirname "$c")/bot/handlers" ]]; then
      kira_like="${kira_like:-$c}"
    else
      others+=("$c"); n_other=$((n_other + 1))
    fi
  done <<< "$found"
  if [[ -n "$kira_like" ]]; then printf '%s' "$kira_like"; return 0; fi
  if (( n_other == 1 )); then
    warn "Нашёл единственный .env с токеном: ${others[0]} — беру его." >&2
    printf '%s' "${others[0]}"; return 0
  elif (( n_other > 1 )); then
    warn "Нашёл несколько .env с токенами и не знаю, какой ваш (Кира или другой бот):" >&2
    printf '   %s\n' "${others[@]}" >&2
    say "Укажи нужный: ENV_FILE=/путь/к/.env bash install.sh" >&2
    return 1
  fi
  if [[ -n "$backups" ]]; then printf '%s' "$backups"; return 0; fi
  # 5) последний шанс: окружение старого контейнера Киры (там лежит TOKEN из его .env)
  if command -v docker >/dev/null 2>&1; then
    id="$(docker ps -aq --filter label=com.docker.compose.service=kira 2>/dev/null | head -1 || true)"
    if [[ -n "$id" ]]; then
      local tmp=".env.from-container"
      docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$id" 2>/dev/null \
        | grep -Ev '^(PATH|HOME|HOSTNAME|LANG|LC_[A-Z]+|PYTHON[A-Z_]*|GPG_KEY|UV_[A-Z_]+|TERM|PWD|SHLVL|_)=' > "$tmp" || true
      if has_token "$tmp"; then printf '%s' "$PWD/$tmp"; return 0; fi
      rm -f "$tmp"
    fi
  fi
  return 1
}

use_found_env() {
  cp -p .env ".env.backup-$(date +%Y%m%d-%H%M%S)"
  [[ "$(stat -c %a .env 2>/dev/null || echo 600)" =~ ^[0-7]00$ ]] || warn "У .env открытые права доступа (рекомендуется chmod 600 .env) — я их не меняю."
  ls -1t .env.backup-* 2>/dev/null | tail -n +11 | xargs -r rm -f
  # Если Кира раньше работала в Docker из другой папки — продолжаем тот же compose-проект (те же тома и данные).
  if command -v docker >/dev/null 2>&1 && [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
    local old_id old_wd old_proj
    old_id="$(docker ps -aq --filter label=com.docker.compose.service=kira 2>/dev/null | head -1 || true)"
    if [[ -n "$old_id" ]]; then
      old_wd="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$old_id" 2>/dev/null || true)"
      old_proj="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$old_id" 2>/dev/null || true)"
      if [[ -n "$old_proj" && "$old_wd" != "$PWD" ]]; then
        export COMPOSE_PROJECT_NAME="$old_proj"
        say "Продолжаю прежний проект Docker: $old_proj (данные сохранятся)"
      fi
    fi
  fi
  export KIRA_KEEP_ENV=1
  ok "Использую существующий .env без вопросов и без изменений"
}

FOUND_ENV=""
if has_token .env; then
  use_found_env
elif [[ -f .env ]]; then
  die ".env есть, но в нём нет TOKEN=… Добавь токен вручную (TOKEN=123456:ABC…) и запусти установщик снова."
elif FOUND_ENV="$(find_env_file)"; then
  say "Нашёл готовый .env: $FOUND_ENV"
  cp -p "$FOUND_ENV" .env                     # оригинал остаётся на месте, не изменяется
  [[ "$(basename "$FOUND_ENV")" == ".env.from-container" ]] && rm -f "$FOUND_ENV"
  use_found_env
elif [[ -n "${TOKEN:-}" && -n "${OWNER_ID:-}" ]]; then
  ok "Токен и ID владельца переданы переменными окружения"
else
  warn ".env с токеном нигде не найден (искал в папке проекта, у запущенной Киры, по процессам, в типичных местах и по всему серверу)."
  say "Подсказка: sudo find / -name '.env' -type f 2>/dev/null | xargs -r grep -l '^TOKEN='"
  if [[ -t 0 && -r /dev/tty ]]; then
    read -r -p "Путь к вашему .env (Enter — ввести токен вручную): " USER_ENV_PATH < /dev/tty || true
    if [[ -n "${USER_ENV_PATH:-}" ]] && has_token "$USER_ENV_PATH"; then
      cp -p "$USER_ENV_PATH" .env
      ok "Беру $USER_ENV_PATH"
      use_found_env
    elif [[ -n "${USER_ENV_PATH:-}" ]]; then
      warn "В этом файле нет TOKEN=… — перехожу к ручному вводу."
    fi
  fi
  [[ "${KIRA_KEEP_ENV:-0}" == "1" ]] || say "Тогда понадобятся только токен бота (@BotFather) и ваш Telegram ID."
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
