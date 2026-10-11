# Changelog

## 1.5.0
- Full static project audit and compatibility checks.
- Replaced stable-diffusion.cpp image backend with ComfyUI v0.36.0.
- Switched default checkpoint to DreamShaper 8 pruned safetensors.
- Updated image health checks, setup scripts, local-media helper and environment template.
- Refreshed selected compatible dependency floors and Docker helper images.
- Added release-specific ComfyUI regression tests.

## 0.3.1 — Multi-AI Failover

- Gemini remains primary with its Flash-Lite model fallback.
- Groq/Qwen added as the first cloud reserve using the official Groq API.
- Hugging Face Inference Providers added as the second cloud reserve.
- Optional local Ollama added as a no-cloud-quota final reserve.
- Circuit breaker skips providers after rate-limit, timeout and 5xx failures, then restores them after cooldown.
- Groq Whisper Large V3 Turbo backs up voice transcription.
- `/ai_health` now checks every configured provider plus Edge TTS.
- `/ai_providers` shows configured providers and circuit state without exposing secrets.
- Frozen `masturbate` command remains byte-for-byte unchanged.

## 0.3.0 — Full Upgrade

### Reliability
- Centralized validated configuration and persistent `DATA_DIR`.
- Optional Redis FSM with memory fallback.
- Graceful Pyrogram degradation when API credentials are absent or unavailable.
- SQLite WAL, foreign keys, busy timeout, periodic optimization and cleanup.
- Scheduled consistent database backups with retention.
- Retry/defer behavior for transient reminder delivery failures.
- Concurrency limits for AI and downloads plus dispatcher abuse protection.
- Shared bounded aiohttp connection pool for lightweight public API modules.
- Rotating file logs and safer crash logging.

### Security
- SSRF protection re-validates every redirect and connected peer for web research/downloads.
- File-analysis size limits and safer archive handling.
- Admin panel defaults to localhost, hides API docs, requires a non-placeholder strong token,
  uses constant-time token comparison and emits restrictive security headers.
- Atomic inventory transfer and more consistent economy writes.
- Docker runs as an unprivileged user and excludes secrets/runtime state from the image context.

### AI / voice
- Added multi-provider text failover: Gemini → Groq/Qwen → Hugging Face Inference Providers → optional local Ollama.
- Added per-provider circuit breakers for rate limits, timeouts and 5xx outages.
- Added Groq Whisper fallback for voice transcription when Gemini audio is unavailable.
- `/ai_health` now probes each configured AI provider separately.
- Gemini 3.8 Flash remains the primary cloud AI.
- Automatic fallback to Gemini 3.5 Flash-Lite for transient/quota failures.
- Removed deprecated Gemini 3.8 sampling knobs from requests.
- Edge Neural TTS keeps Russian/English voice fallback and bounded concurrent synthesis.
- `/ai_health` and `/doctor full` can perform explicit live service checks.

### Internet / media
- DDGS metasearch primary with HTML fallbacks.
- Bounded web-research page reads and redirect-safe URL validation.
- TikTok now has TikWM, legacy API and yt-dlp fallback paths.
- Universal yt-dlp downloads use concurrency/size guards.

### Operations / development
- `/doctor` diagnostics and richer `/status`.
- Telegram slash command menu setup at startup.
- Docker Compose includes Redis and persistent volumes.
- GitLab CI compiles and runs tests before image build.
- Added smoke tests for configuration, downloads and file parsing.
- Updated dependency ranges to stable 2026 releases.

### Compatibility guarantee
The `bot/handlers/masturbate/` command module was intentionally left byte-for-byte unchanged.
Its related database functions were also kept AST-equivalent to the previous release.
## 0.5.0 — Kira D&D Hub

- Добавлено мобильное Telegram Mini App `/dnd` с листом персонажа, фурри- и фэнтези-расами, характеристиками, XP, инвентарём и бросками d4–d100.
- Добавлены кампании с кодом приглашения, ролями DM/player и безопасным хранением в SQLite.
- Mini App принимает только проверенный Telegram `initData` (HMAC по bot token), user_id из запроса не доверяется.
- Команды `/dnd`, `/character_sheet`, `/roll`, `/campaign` и кнопка WebApp добавлены в меню бота.
- `/research` получил таймаут, нормализацию запроса и понятный ответ при пустом результате.
## 0.5.1 — D&D interface polish

- Обновлён мобильный fantasy-интерфейс Mini App в стиле Kira.
- Добавлена навигация «Герой / Кампания / Кости».
- Добавлены быстрые карточки партии и квестов, создание и вступление по коду.
- Добавлены модификатор, advantage/disadvantage и локальный журнал бросков.
- Предусмотрены гостевой/offline-режим и безопасное экранирование данных кампании.
## 0.5.2 — Campaign tools

- Добавлены защищённые API детализации кампании и DM-обновления журнала, квестов, инициативы, HP/условий и лута.
- Добавлен API истории бросков пользователя.
- Механики и поля сверены с открытым SRD: характеристики, модификаторы, инициатива, скорость, HP, состояния и слоты заклинаний реализуются собственными формулировками.
## 0.5.3 — Character completeness

- В Mini App добавлены навыки, спасброски, владения, бонус мастерства, инициативу, кость хитов, атаки, заклинания, слоты, черты, условия и спасброски от смерти.
- Новые поля сохраняются в существующий JSON листа персонажа без изменения старых таблиц.
- Добавлена панель журнала и квестов кампании.
## 0.5.5 — RPG HUD polish

- Обновлён игровой HUD: аватар, уровень, HP, AC и прогресс XP.
- Добавлены динамические модификаторы характеристик.
- Исправлен лишний фрагмент JavaScript в панели кубов.
## 0.5.6 — Tishir code

- Обновлена информация о разработчике: Tishir code.
- Сборка предназначена для бесшовного обновления текущего сервера.

## 1.7.0
- Игровая алкошкала: `выпить`, `топ алкоголизм`, кулдаун и миграция БД.
- Проведён обзор доступных GitHub-репозиториев пользователя; идеи развития вынесены в `IDEAS_1.7.md`.
