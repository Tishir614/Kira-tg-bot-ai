#!/usr/bin/env bash
# Безопасный деплой KiraBot на сервер, где уже лежат .env с ключами и данные бота.
#   bash deploy.sh            — обновить из GitHub (ветка main) и перезапустить
#   BRANCH=dev bash deploy.sh — другая ветка
#
# Что гарантируется:
#   * .env (токены/ключи) НИКОГДА не перезаписывается: git его не трогает (он в .gitignore),
#     перед деплоем делается копия .env.backup-*, новые настройки только ДОПИСЫВАЮТСЯ в конец.
#   * База, сессии и память бота лежат в docker-томе kira-persistent-data; скрипт не делает
#     `down -v` и не удаляет тома. Перед обновлением снимается архив тома в ./backups/.
set -Eeuo pipefail
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
BRANCH="${BRANCH:-main}"
STAMP="$(date +%Y%m%d-%H%M%S)"

say()  { printf '\033[0;36m[deploy]\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; exit 1; }
trap 'die "Ошибка на строке $LINENO. .env и данные не затронуты; откат: git reset --hard ${PREV_COMMIT:-HEAD} && docker compose up -d --build"' ERR

command -v git >/dev/null    || die "Нужен git."
command -v docker >/dev/null || die "Нужен docker."
docker compose version >/dev/null 2>&1 || die "Нужен docker compose v2."
[[ -f .env ]] || die ".env не найден. Для первой установки запусти: bash setup.sh"
grep -qE '^TOKEN=.{20,}' .env || die "В .env нет TOKEN. Деплой остановлен, чтобы не запустить бота без ключа."
[[ -d .git ]] || die "Это не git-репозиторий. Клонируй: git clone <repo> и перенеси .env, либо используй bash upgrade.sh release.zip"

# 1. Резервные копии ключей и данных.
cp -p .env ".env.backup-$STAMP"
chmod 600 ".env" ".env.backup-$STAMP"
ls -1t .env.backup-* 2>/dev/null | tail -n +11 | xargs -r rm -f   # хранить 10 последних
say "Копия ключей: .env.backup-$STAMP"

mkdir -p backups
if docker volume inspect kira-persistent-data >/dev/null 2>&1; then
  docker run --rm -v kira-persistent-data:/data:ro -v "$PROJECT_DIR/backups:/out" alpine \
    tar czf "/out/kira-data-$STAMP.tgz" -C /data . && say "Копия данных: backups/kira-data-$STAMP.tgz"
  ls -1t backups/kira-data-*.tgz 2>/dev/null | tail -n +6 | xargs -r rm -f   # хранить 5 последних
else
  say "Том kira-persistent-data ещё не создан — копировать нечего."
fi

# 2. Обновление кода. Игнорируемые файлы (.env, *.db, static/) git не трогает.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  die "В репозитории есть локальные правки отслеживаемых файлов. Сохрани их (git stash) и запусти снова."
fi
PREV_COMMIT="$(git rev-parse HEAD)"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git merge --ff-only "origin/$BRANCH"
say "Код обновлён: ${PREV_COMMIT:0:8} -> $(git rev-parse --short HEAD)"

# 3. Только допись новых настроек в .env (существующие строки не меняются ни на байт).
if command -v python3 >/dev/null && [[ -f example.env ]]; then
  TMP_ENV=".env.merge.$$"
  cp example.env "$TMP_ENV"
  # merge_env.py читает старый .env и переписывает ВТОРОЙ файл: старые строки + недостающие ключи.
  python3 tools/merge_env.py .env "$TMP_ENV"
  if ! cmp -s .env "$TMP_ENV"; then
    # Страховка: в новом файле должны остаться все старые байты .env как префикс.
    python3 - "$TMP_ENV" <<'PY'
import sys
old = open('.env', 'rb').read()
new = open(sys.argv[1], 'rb').read()
sys.exit(0 if new.startswith(old.rstrip(b'\n')) else 1)
PY
    chmod 600 "$TMP_ENV"
    mv -f "$TMP_ENV" .env
  else
    rm -f "$TMP_ENV"
  fi
fi
cmp -s .env ".env.backup-$STAMP" || say "В .env дописаны новые параметры по умолчанию (старые значения сохранены)."

# 4. Проверка конфигурации и запуск (тома не удаляются).
docker compose config -q
docker compose up -d --build
say "Жду запуска…"
sleep 15
docker compose ps
docker compose logs --tail=40 kira || true
say "Готово. Если что-то пошло не так: git reset --hard ${PREV_COMMIT:0:8} && docker compose up -d --build"
say "Ключи: .env.backup-$STAMP · данные: backups/"
