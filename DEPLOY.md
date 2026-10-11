# Деплой KiraBot на сервер (ключи и данные сохраняются)

Ключи лежат в `.env` (он в `.gitignore`, git его не трогает), а база, сессии и память — в docker-томе
`kira-persistent-data`. `deploy.sh` ничего из этого не перезаписывает и не удаляет.

## Обновление уже работающего бота (рекомендуется)
```bash
cd /путь/к/Kira-tg-bot-ai          # папка, где лежит .env
git remote -v                      # origin должен вести на github.com/Tishir614/Kira-tg-bot-ai
bash deploy.sh                     # обновит из ветки main и перезапустит
```
Что делает скрипт:
1. Проверяет, что `.env` существует и в нём есть `TOKEN`; иначе останавливается, ничего не меняя.
2. Копирует `.env` в `.env.backup-<дата>` (права 600, хранится 10 последних).
3. Архивирует том данных в `backups/kira-data-<дата>.tgz` (хранится 5 последних).
4. `git fetch` + `git merge --ff-only` (если вы правили файлы руками — остановится и попросит `git stash`).
5. **Дописывает** в конец `.env` только новые параметры (`IMAGE_PROVIDERS`, `HORDE_API_KEY`, `AI_*`…);
   ваши существующие строки остаются на месте байт в байт.
6. `docker compose config -q`, затем `docker compose up -d --build` (без `down -v`, тома не удаляются).

Откат: `git reset --hard <старый-коммит> && docker compose up -d --build`
(хэш выводится в конце деплоя). Ключи: `cp .env.backup-<дата> .env`.

## Если на сервере ещё нет папки с проектом, но ключи есть
```bash
git clone https://github.com/Tishir614/Kira-tg-bot-ai.git
cp /старый/путь/.env Kira-tg-bot-ai/.env && chmod 600 Kira-tg-bot-ai/.env
cd Kira-tg-bot-ai && bash deploy.sh
```
Репозиторий приватный? Добавьте на сервер deploy key (Settings → Deploy keys) или клонируйте через
HTTPS с personal access token. Том `kira-persistent-data` подхватится автоматически, если не менять
имя проекта compose.

## Первая установка с нуля
`bash setup.sh` — интерактивный мастер (спросит TOKEN, сам поставит Docker). Повторный запуск `setup.sh`
тоже делает копию `.env` и предлагает оставить существующий TOKEN.

## Установка из zip-архива вместо git
`bash upgrade.sh release.zip` (`tools/safe_upgrade.py`): `.env`, `static/`, `.git` защищены от замены.

## Что настроить после первого запуска
- Профили compose (Ollama, ComfyUI, голос) включаются в `.env`: `COMPOSE_PROFILES=ollama,voice`.
- Картинки: по умолчанию `IMAGE_PROVIDERS=horde,perchance,comfyui`. Свой ключ AI Horde — `HORDE_API_KEY`.
- Слабый сервер: `KIRA_LIGHT_MODE=auto`; лимиты зависаний — `AI_TOTAL_TIMEOUT`, `AI_MAX_QUEUE` и др.
- Проверка: `docker compose ps`, `docker compose logs -f kira`, в Telegram `/status`, `/ai_health`, `/stats`.
