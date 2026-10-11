#!/usr/bin/env bash
# KiraBot: установка одной командой. Ставит git, curl, Docker + Compose, скачивает бота,
# создаёт .env (спросит только TOKEN и OWNER_ID), поднимает все сервисы и локальный AI.
#
#   git clone https://github.com/Tishir614/Kira-tg-bot-ai.git && cd Kira-tg-bot-ai && bash install.sh
#   или без вопросов:  TOKEN=123:ABC OWNER_ID=12345 bash install.sh
#
# Переменные (необязательно):
#   REPO_URL  — откуда клонировать (по умолчанию GitHub-репозиторий проекта)
#   DIR       — куда ставить, если скрипт запущен не из папки проекта (~/Kira-tg-bot-ai)
#   BRANCH    — ветка (main)
#   KIRA_LOCAL_IMAGE=1 — дополнительно поставить локальный ComfyUI (≈4.3 ГБ, нужен мощный сервер)
# Повторный запуск безопасен: существующий .env НЕ изменяется (используется как есть), данные сохраняются.
set -Eeuo pipefail
umask 077

REPO_URL="${REPO_URL:-https://github.com/Tishir614/Kira-tg-bot-ai.git}"
BRANCH="${BRANCH:-main}"
say()  { printf '\033[0;36m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }
trap 'die "Ошибка на строке $LINENO. Ничего не удалено; после исправления просто запусти install.sh ещё раз."' ERR

[[ "$(uname -s)" == "Linux" ]] || die "Установщик рассчитан на Linux-сервер (Ubuntu/Debian/Fedora/Arch)."
if [[ ${EUID:-$(id -u)} -eq 0 ]]; then SUDO=(); else
  command -v sudo >/dev/null 2>&1 || die "Нужен root или sudo."
  SUDO=(sudo)
fi

# 1. Базовые пакеты (git, curl, python3 нужны для клонирования и слияния .env).
need=()
for tool in git curl python3; do command -v "$tool" >/dev/null 2>&1 || need+=("$tool"); done
if ((${#need[@]})); then
  say "Устанавливаю: ${need[*]}"
  # shellcheck disable=SC1091
  . /etc/os-release 2>/dev/null || true
  case "${ID:-}" in
    ubuntu|debian|linuxmint|pop) "${SUDO[@]}" apt-get update -y && "${SUDO[@]}" apt-get install -y "${need[@]}" ca-certificates ;;
    fedora)                      "${SUDO[@]}" dnf install -y "${need[@]}" ;;
    arch|manjaro|endeavouros)    "${SUDO[@]}" pacman -Sy --needed --noconfirm "${need[@]}" ;;
    *) die "Не знаю, как поставить ${need[*]} в '${ID:-unknown}'. Установи вручную и повтори." ;;
  esac
fi

# 2. Код проекта: текущая папка (если это проект) или клон/обновление в $DIR.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$PWD/x}")" && pwd)"
if [[ -f "$SCRIPT_DIR/setup.sh" && -d "$SCRIPT_DIR/bot" ]]; then
  PROJECT_DIR="$SCRIPT_DIR"
  if [[ -d "$PROJECT_DIR/.git" && -z "$(git -C "$PROJECT_DIR" status --porcelain --untracked-files=no)" ]]; then
    say "Обновляю код (.env и данные не затрагиваются)…"
    git -C "$PROJECT_DIR" pull --ff-only origin "$BRANCH" || warn "Не удалось обновить код — продолжаю с текущей версией."
  fi
else
  PROJECT_DIR="${DIR:-$HOME/Kira-tg-bot-ai}"
  if [[ -d "$PROJECT_DIR/.git" ]]; then
    say "Папка $PROJECT_DIR уже есть — обновляю."
    git -C "$PROJECT_DIR" pull --ff-only origin "$BRANCH" || warn "Не удалось обновить код — продолжаю с текущей версией."
  else
    say "Скачиваю бота в $PROJECT_DIR…"
    git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR" || die "Не удалось клонировать $REPO_URL (приватный репозиторий? нужен токен доступа или deploy key)."
  fi
fi
cd "$PROJECT_DIR"

# 3. Страховка ключей перед любыми изменениями.
if [[ -f .env ]]; then
  cp -p .env ".env.backup-$(date +%Y%m%d-%H%M%S)"
  [[ "$(stat -c %a .env 2>/dev/null || echo 600)" =~ ^[0-7]00$ ]] || warn "У .env открытые права доступа (рекомендуется chmod 600 .env) — я их не меняю."
  ls -1t .env.backup-* 2>/dev/null | tail -n +11 | xargs -r rm -f
  export KIRA_KEEP_ENV=1   # setup.sh использует этот .env как есть: не переписывает и не дополняет
  say "Найден .env — он будет использован как есть, без каких-либо изменений."
fi

# 4. Docker, .env, образы, сервисы, модели — всё делает setup.sh в автоматическом режиме.
export KIRA_AUTO=1
say "Запускаю установку (Docker, сервисы, локальный AI). Это может занять 10–30 минут при первом запуске…"
bash ./setup.sh

say "Готово. Напиши боту в Telegram /помощь, /status и /ai_health."
say "Обновление позже: bash deploy.sh"
