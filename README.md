# KiraBot 1.2.0 — One App + Repair Pack

Kira 1.2 repairs the features that most directly affect everyday use: local image generation, D&D, Telegram Mini App embedding and local Piper voice. The `/kira` Mini App is now the single hub for profile, cosmetics/shop, D&D, commands, memory and privacy. Profile cosmetics use levels and Kira coins, and the selected gender/nickname are available to the AI/RP context without becoming instructions to the model.

Upgrade an existing installation with `bash upgrade_1_2.sh`. It preserves `.env` and Docker volumes, migrates only Kira's old stock image-model defaults and starts the local image/voice profiles.

## 1.1 Adaptive Core + Media Hub + Social

New user features:

- `/мат выкл|умеренно|вкл` controls Kira's profanity style. The default for new chats is free/natural speech; server/privacy protections remain intact.
- `/найти_видео`, `/найти_музыку`, `/найти_картинку` search several results and let the user download the chosen item with an inline button.
- `/ютуб`, `/тикток`, `/твич` provide public search/link inspection and supported downloads. Twitch live streams are inspected but not downloaded as unbounded files.
- `/скорость_ии` now shows the adaptive route, fast/smart model and actual response/load timings.

Public media support is intended for content the user is allowed to save. The bot does not bypass DRM/private access or steal browser cookies.

## 0.6.2 Sequential Local AI + Quality + Local Media

KiraBot can run TTS and text-to-image generation entirely on the same server. Piper TTS is bundled through Python and stores voice models in `static/piper`. Image generation uses a private Docker-only ComfyUI service; setup can download the public SD 1.5 inference model without any API token. On CPU, 512×512 rendering can take minutes.

> **Версия 0.4.3:** инструкции безопасного перехода с 0.4.2 и ограничения — [RELEASE_0.4.3.md](RELEASE_0.4.3.md). Для перехода используйте новый Python-установщик, а не старый upgrade.sh.


## Установка одной командой

После распаковки проекта запусти:

```bash
bash setup.sh
```

Мастер сам проверит Docker/Compose. Первым шагом терминал попросит вставить Telegram Bot Token от `@BotFather`; ввод скрывается, токен атомарно сохраняется в `.env` с правами `600`. При повторном запуске можно оставить сохранённый токен или заменить его. Затем мастер предложит резервные AI-провайдеры и Ollama, поднимет Redis и KiraBot и покажет статус контейнеров.

# KiraBot 0.3

KiraBot is a modular Telegram bot built on **Aiogram 3**, **SQLAlchemy/SQLite**, optional **Redis/Pyrogram**, a multi-provider **Gemini → Groq/Qwen → Hugging Face → Ollama** AI failover chain and **Edge Neural TTS** for voice. The project also contains internet search/research, downloads, TikTok/media helpers, file analysis, reminders, moderation, economy/mini-games, plugins and an optional admin panel.

The 0.3 release focuses on stability and deployment quality: validated configuration, Redis FSM support, SQLite WAL/backups, bounded concurrency, safer web fetching, diagnostics, tests, Docker Compose and CI.

> The existing `bot/handlers/masturbate/` command module is intentionally preserved byte-for-byte in this upgrade.

## Quick start

Requirements: Python **3.12+**, `uv`, and preferably `ffmpeg` for media features.

```bash
cp example.env .env
# Edit TOKEN and other values you need.
uv sync
uv run -m bot
```

Required:

```env
TOKEN=123456:telegram_bot_token
```

Strongly recommended:

```env
OWNER_ID=123456789
SUPPORT_CHAT_ID=@kira26481
BOT_TIMEZONE=Europe/Vilnius
```

`API_ID` and `API_HASH` are now optional. If they are absent, Pyrogram-dependent helpers are disabled instead of taking the whole bot down.

## Docker Compose

The recommended server setup includes Redis-backed FSM and a persistent data volume:

```bash
cp example.env .env
# configure .env
docker compose up -d --build
```

Compose stores bot state under the `kira-data` volume and Redis data under `kira-redis`.

## Configuration and data

All mutable application state is under `DATA_DIR` (default `static`):

- SQLite database and WAL files;
- rotating logs;
- automatic backups;
- runtime/updater state.

Useful runtime controls:

```env
DATA_DIR=static
LOG_LEVEL=INFO
LOG_TO_FILE=1
LOG_RETENTION_DAYS=14
REQUEST_LIMIT=30
REQUEST_WINDOW_SECONDS=10
MAX_CONCURRENT_AI=4
MAX_CONCURRENT_DOWNLOADS=3
FILE_ANALYSIS_MAX_MB=20
BACKUP_INTERVAL_HOURS=24
BACKUP_KEEP=7
```

### Persistent FSM with Redis

Without Redis the bot uses Aiogram `MemoryStorage`. To keep FSM state across restarts or run multiple replicas:

```env
FSM_REDIS_URL=redis://localhost:6379/0
```

Docker Compose injects its own internal Redis URL automatically.

## AI assistant

AI is optional. Kira 0.8.0 uses a smart local-dialogue profile: reply-aware context, longer relevant memory, lower temperature for coherence, hidden-reasoning cleanup, weak-answer detection, and sequential local-model fallback.

```env

# Fully local adaptive text AI. Only one model is intentionally resident at once.
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen3.5:2b-q4_K_M
OLLAMA_FAST_MODEL=qwen3.5:2b-q4_K_M
OLLAMA_SMART_MODEL=qwen3.5:4b
OLLAMA_MODELS=qwen3.5:2b-q4_K_M,qwen3.5:4b,qwen3:1.7b
OLLAMA_KEEP_ALIVE=10m
OLLAMA_NUM_CTX=4096
AI_ADAPTIVE_ROUTING=1

AI_PROVIDER_COOLDOWN_SECONDS=60
AI_PROVIDER_TIMEOUT_SECONDS=28
AI_PROVIDER_ORDER=ollama
AI_LOCAL_ONLY=1
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
AI_MAX_RESPONSE_TOKENS=950
```

With `AI_LOCAL_ONLY=1`, text dialogue stays on Ollama and does not require cloud API keys. `AI_SMART_DIALOGUE=1` guarantees a useful minimum conversation window even when an older `.env` still contains the historical 5-message/6000-character defaults. Reply-to messages are injected as quoted context, so short follow-ups such as «почему?» or «сделай так же» keep their meaning. Qwen-family hidden reasoning is not shown to users.

If the bot is running mostly on local Ollama and replies are still weak, run:

```bash
bash ai_quality.sh
```

The script chooses a stronger local model for the server RAM, downloads it once, updates only AI-related `.env` keys, never prints secrets, and restarts the Ollama/Kira services.

Main commands/features:


## Ники Киры и Лисий досуг (1.0.2)

Пользователь может задать ник командой `/ник Лис` или фразой `Кира, называй меня Лис`. Ник используется в обращениях Киры и RP. `/ник глобально Лис` задаёт запасной ник для других чатов. Посмотреть/удалить: `/мой_ник`, `/удалить_ник`.

Для развлечения добавлены `/правда`, `/действие`, `/оракул`, `/дуэль` и `/комплимент`. Они не влияют на игровую экономику.

> Начиная с 1.0.1 у всех slash-команд есть русские имена. Полный каталог: `/команды` или веб-страница `/commands`. Старые английские имена сохранены как совместимые алиасы.

- `/ии <вопрос>` or `Кира, <question>`;
- compact conversational memory per user/chat;
- `/забыть_ии` or `/сброс_ии` to clear old contaminated dialogue history;
- `/провайдеры_ии` to see the actual provider/model and quality settings;
- `/здоровье_ии` for live provider/TTS checks (owner/sudo);
- `/анализ_фото` through the configured Hugging Face vision route;
- cloud transcription is disabled in local-only mode; text AI runs only through Ollama;
- translation, summaries, and deep research use lower factual temperatures instead of the creative chat profile.

## Neural TTS

Voice synthesis is fully local and uses **Piper TTS**. No API key or cloud TTS is required. The default Russian voice is `ru_RU-irina-medium`; the model is downloaded once into persistent bot data and reused locally:

```env
TTS_VOICE_RU=ru-RU-SvetlanaNeural
TTS_VOICE_EN=en-US-AvaNeural
TTS_RATE=-2%
TTS_VOLUME=+0%
TTS_PITCH=+0Hz
```

Commands:

- `/озвучить текст` or `озвучь text`;
- `/tts` as a reply to a message;
- `/голоса`;
- `/здоровье_ии`.

Russian TTS has configured voice fallbacks so a temporary voice-catalog issue does not immediately kill synthesis.

## Internet search and research

- `найди <запрос>` / `/поиск` for fast search;
- `исследуй <тему>` / `/исследование` for multi-source research and an AI summary when AI is enabled;
- weather, currency, crypto and news helpers.

Search prefers the maintained `ddgs` metasearch package and falls back to HTML providers. Web-research page fetching validates redirects and connected peers, blocks non-public server/network addresses and uses response-size limits.

## Downloads and TikTok

- `скачай <URL>` / `/скачать` for regular HTTP/HTTPS files;
- `скачай видео <URL>` / `/видео` for supported yt-dlp media;
- `скачай аудио <URL>` / `/аудио` for audio extraction;
- TikTok reactions `👀` (video) and `⚡` (audio).

TikTok has multiple paths: TikWM, the legacy fallback and yt-dlp. Downloads are bounded by concurrency and size settings.

```env
INTERNET_MAX_DOWNLOAD_MB=49
MEDIA_MAX_DOWNLOAD_MB=49
```

The regular Telegram Bot API has its own upload limits. For larger files, configure a local Telegram Bot API server and then raise the bot limits deliberately:

```env
BOT_API_BASE_URL=http://127.0.0.1:8081
```

Kira never executes downloaded files.

## Files

Reply to a document with `прочитай файл`, `анализ файла` or `/file`.

Supported formats include PDF, DOCX, TXT/Markdown/source code, JSON, CSV, YAML/TOML and ZIP inspection. File analysis is capped by `FILE_ANALYSIS_MAX_MB`, and archives are inspected with extraction limits.

## Reminders

Examples:

- `напомни через 30 минут проверить духовку`;
- `напомни каждые 2 часа размяться`;
- `напомни завтра в 18:00 позвонить`;
- `/reminders`;
- `/delremind ID`.

Reminders live in SQLite. Temporary Telegram/network errors are deferred instead of silently losing the reminder.

## Economy, social and mini-games

The suite contains XP/levels, coins, daily rewards, shop/inventory, gifts, achievements, relationships, pets and lightweight games such as coin/dice/fishing/duels/quiz and virtual-coin roulette. Inventory transfers now happen transactionally to avoid losing items between separate commits.

## Moderation

Group helpers include configurable anti-flood/anti-spam, link policy, muting/unmuting, blacklist and audit logging. Dispatcher-level request throttling also protects expensive handlers from a single user flooding the bot.

## Diagnostics

`/status` shows version, uptime, Python version, storage/backend status and runtime counters.

`/doctor` (owner/sudo) checks local deployment health such as:

- SQLite and writable data directory;
- free disk space;
- `ffmpeg` / Node presence;
- Gemini key configuration;
- Redis FSM / Pyrogram state.

`/doctor full` additionally performs intentional live external AI/TTS/search checks. It is not run automatically, so restarts do not waste free API quota.

## Automatic maintenance and backups

An hourly maintenance task:

- cleans stale in-memory anti-flood/rate-limit buckets;
- removes old audit/finished-reminder rows;
- asks SQLite to optimize/checkpoint WAL;
- creates consistent backups according to `BACKUP_INTERVAL_HOURS`.

Backups are retained according to `BACKUP_KEEP`. Use `/backupdb` for an explicit owner/sudo backup.

## Admin panel

Disabled by default. Safe default binding is localhost:

```env
WEB_PANEL_ENABLED=1
WEB_PANEL_HOST=127.0.0.1
WEB_PANEL_PORT=8080
PANEL_TOKEN=generate_a_long_random_secret_here
```

The panel rejects weak/example tokens, uses constant-time token comparison, disables public OpenAPI/Swagger pages and sends restrictive security headers. If publishing it outside localhost, put it behind HTTPS/reverse proxy and additional access control.

## Plugins

Put optional modules in `bot/plugins/`. A plugin can expose either:

```python
router = Router()
```

or a `setup(router)` hook. A broken optional plugin is logged and skipped rather than aborting core startup.

## Database and migrations

The compatibility `create_all + add missing columns` path is retained for existing installations. Alembic is also available:

```bash
uv run alembic upgrade head
```

SQLite is configured with WAL, foreign keys and busy timeout for better concurrent reliability.

## Tests

Run the local smoke suite:

```bash
uv run pytest -q
uv run python -m compileall -q bot alembic
```

GitLab CI performs compilation and tests before building the Docker image.

## Dependency lock

`uv.lock` is intentionally not bundled when it cannot be resolved against the current package index. Run `uv lock` (or simply `uv sync`) on a machine with package-index access and commit the generated lockfile for fully reproducible production builds.

See also: `CHANGELOG.md`, `SECURITY.md`, and `ARCHITECTURE.md`.

## Kira visuals and voice (0.3.7)

- `/image <prompt>` or `нарисуй <prompt>` — generates an image locally through ComfyUI; no image API key is used.
- `/kira_image <scene>` — generates Kira using the bundled character reference/profile.
- `/kira_ref` — shows Kira's bundled visual reference.
- `/voice_auto on|off` — opt-in spontaneous Kira voice notes.
- `/voice_auto chance 20` — controls the probability per background check (1–100%).
- `/voice_auto test` — sends a TTS test voice message.

Mature Mode may use a more sensual adult visual style after 18+ confirmation, but explicit pornography and graphic sexual image prompts are not sent to the image provider.


## AI providers in 0.3.8
Gemini удалён полностью. Текстовый failover: **Groq → Hugging Face → Ollama**. Для распознавания речи используется Groq Whisper.
### Kira D&D Mini App (0.5.0)

Установите `DND_WEBAPP_URL` на публичный HTTPS-адрес `/dnd` и перезапустите compose. Команда `/dnd` открывает приложение в Telegram. Все игровые данные хранятся в `static/database.db`; существующие таблицы и старые команды не изменяются. Доступ API разрешён только при валидном Telegram `X-Telegram-Init-Data`.

Для Debian: укажите домен и TLS в reverse proxy, задайте `DND_WEBAPP_URL=https://ваш-домен/dnd`, затем выполните `docker compose up -d --build`. Если TLS уже обслуживается внешним Nginx, проксируйте `/` на порт панели (`WEB_PANEL_PORT`, обычно 8080).


## Local AI chain (0.8.0)

By default Kira uses a sequential Ollama chain: `qwen3.5:2b-q4_K_M` → `qwen3:1.7b`. The 2B Q4 model is the quality-first default for the low-RAM VPS; `ai_quality.sh` can select `qwen3.5:4b-q4_K_M` when at least 6 GB RAM is available. Only one model is intentionally resident in RAM at a time. Complex prompts can enable local reasoning and a bounded review pass without cloud APIs.


## Local-only AI
Kira does not need Groq, Hugging Face Inference, Gemini, or another cloud text-AI API in local-only mode. Text generation runs through Ollama.

## Подробные уведомления об обновлении (0.6.4)

После реального изменения версии/сборки Kira отправляет владельцу из `OWNER_ID` отдельный подробный отчёт: предыдущая и новая версия, создатель проекта, идентификатор сборки и список изменений. Для подробностей используется `RELEASE_<версия>.md`, а при его отсутствии соответствующий раздел `CHANGELOG.md`.

Если Telegram временно недоступен, отчёт сохраняется как pending в `static/.owner_update.json` и повторяется при следующем запуске. Чистая первая установка не считается обновлением. Для будущих релизов рекомендуется всегда добавлять подробный `RELEASE_<версия>.md`, чтобы Кира могла рассказать хозяину об изменениях человеческим языком.

## Активность, модерация и self-recovery (0.6.5)

В группах Kira считает активность отдельно для каждого чата. `/activity` показывает рейтинг по уровню и сообщениям, `/myactivity` — личный прогресс, `/groupstats` — общую статистику. Уровень активности не смешивается между разными группами.

Модерация включает `/warn`, `/unwarn`, `/warnings`, `/ban`, `/unban`, `/kick`, `/mute`, `/unmute`, `/modlog`. После трёх предупреждений Kira пытается автоматически выдать часовой мут.

Для более живого общения в личке можно писать Кире обычным текстом без команды. В группе Kira реагирует на обращение/упоминание/reply и, если включено, иногда сама подключается к разговору. Администраторы управляют этим через `/kira_chat on|off` и `/kira_chance 0..25`.

Self-recovery работает консервативно: Kira ведёт журнал сбоев, выполняет безопасное обслуживание SQLite, а при повторении одной ошибки может сделать ограниченный перезапуск процесса. Docker поднимает контейнер снова, после чего Kira сообщает `OWNER_ID`, что проверила восстановление. Исходный код во время работы никогда не переписывается автоматически. `/recovery` показывает последние инциденты владельцу.



## Fast AI и жалобы (0.6.6)

Обычный локальный чат остаётся оптимизированным для CPU, но профиль `AI_SMART_DIALOGUE=1` теперь держит до 10 последних релевантных сообщений и до 10000 символов истории. Reply-контекст добавляется прямо к запросу, а явно слишком короткий/сломанный ответ может отправить запрос на следующую локальную модель. `/ai_speed` показывает фактический размер контекста и режим Smart dialogue.

Система жалоб работает внутри групп. Ответьте на проблемное сообщение командой `/report причина` или `жалоба причина`. Администраторы используют `/reports`, `/report_info ID`, `/report_done ID комментарий`, `/report_reject ID комментарий`. Жалобы имеют защиту от дублей/спама, сохраняют краткое доказательство и отправляют уведомление владельцу или в связанный админ-чат.

## Правила и минимальная автомодерация (0.6.7)

- `/rules` или `правила` — показать правила сообщества.
- `/rules status` — статус контроля.
- `/rules on` / `/rules off` — включение/выключение администратором.
- Контроль включён по умолчанию во всех группах.
- Kira выдаёт авто-предупреждение только за очевидные нарушения и не выполняет авто-бан/авто-мут по эвристике.
- Неоднозначные случаи отправляются администрации через обычную систему жалоб `/report`.

## Поддержка, экономика, беседы и Smart Local AI (0.8.0)

- `/help` безопасно экранирует аргументы команд и имеет резервный plain-text режим.
- `/support` и кнопка **«🛟 Поддержка»** запускают приватное обращение; вопрос уходит в `SUPPORT_CHAT_ID` с отметкой пользователя.
- Администратор support-чата или владелец отвечает через `/support_reply USER_ID текст`.
- Профиль и экономика: `/bio`, `/wallet`, `/work`, `/pay`, `/richlist`.
- Для групп: `/who`, `/pair`, `/topic`, `/chatmood`.
- Локальный AI: `qwen3.5:2b-q4_K_M` → `qwen3:1.7b`, reasoning для сложных запросов и локальная самопроверка ответа.
- Telegram Reply и расширенная история продолжают использоваться для связного диалога.

## Браки, роли команды и парные RP18 (0.6.8)

### Браки беседы

```text
/marry              # ответом на сообщение или /marry @username
/spouse
/divorce
/marriages
```

Брак хранится отдельно для каждой беседы. Получатель предложения должен нажать кнопку принятия. Старые браки RPG-персонажей продолжают работать независимо.

### Роли команды

```text
/staff
/role helper         # ответом на сообщение
/role moderator @user
/role admin @user    # только владелец
/unrole @user
```

Полномочия распределены по принципу минимально необходимых прав: помощник работает с предупреждениями/жалобами, модератор получает мут/кик и обработку жалоб, администратор получает бан и настройки, владелец может назначать администраторов.

### RP18 с явным согласием

```text
/rp18_actions
секс @username
переспать            # ответом на сообщение
ночь вместе @username
страстно поцеловать  # ответом на сообщение
```

Для парных взрослых действий нужны: подтверждение 18+ у обоих участников, включённый Mature Mode и отдельное согласие второго человека кнопкой. Ответы остаются не-графичными.

## Kira 1.0 — Memory Core

Kira 1.0 adds a local-first memory/moderation layer without requiring external AI APIs:

- `/memory`, `/remember`, `/forget_me`, `/privacy` — long-term memory and privacy controls.
- Group history is **off by default**. Admins enable it with `/privacy chat on`; users can opt out with `/privacy groups off`.
- `/find_memory` plus natural questions such as `Кира, что мы решили...` search locally stored chat history.
- `/digest 24h` creates a group digest.
- `/aimod assist 3` enables contextual AI moderation; `auto` only deletes high-confidence risky messages.
- `/admin_ai ...` converts natural-language admin requests into a proposal and requires confirmation.
- `/summary_voice` uses local `whisper.cpp`; `/tts` uses Piper.
- `/image`, `/avatar`, `/meme` use the private `ComfyUI` service.
- `/kira_app` opens the Mini App when `KIRA_WEBAPP_URL` points to the HTTPS `/kira` route.
- Plugins can be disabled with `KIRA_DISABLED_PLUGINS=plugin_a,plugin_b`.

Local services can be started with Docker Compose profiles `ollama`, `image`, and `voice`.


## Kira 1.3.0 — точное распознавание трека из видео

Ответьте `/трек` на видео или аудио. Kira распознаёт основу через Shazam, ищет варианты через локальный media pipeline и сверяет кандидатов с исходником через Chromaprint. Если акустическое совпадение недостаточно сильное, бот честно не выдаёт другой remix/edit за точный.

## Kira 1.6 Mini Apps
- `/kira` opens the standalone Kira Mini App with built-in AI chat.
- `/dnd` opens a separate D&D Mini App. D&D UI failures are isolated from Kira.
- Upgrade with `./upgrade_1_6.sh`; it does not remove Docker volumes.

## Что нового в 2.5–2.7
- `/rp` — умный RP-модуль (сцены, карточки персонажей, библиотека, кубики, память, retry/undo, экспорт).
- Генерация изображений: AI Horde → Perchance furry-ai → ComfyUI (`IMAGE_PROVIDERS`), русские промпты, стили (`стиль:аниме`), кнопки «Ещё вариант» / «Другой стиль».
- Память: факты о пользователе (`/memory`, `/forget`), долговременная сводка разговора, автопоиск в интернете для вопросов про свежее.
- Подробности — в `RELEASE_2.5.0.md`, `RELEASE_2.6.0.md`, `RELEASE_2.7.0.md`.
