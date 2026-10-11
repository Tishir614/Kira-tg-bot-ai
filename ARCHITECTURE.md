# KiraBot architecture

## Core flow

`Telegram -> aiogram Dispatcher -> middleware -> feature/plugin routers -> services -> SQLAlchemy/SQLite`

Kira 1.1 keeps optional failures isolated: a broken plugin is logged/skipped and should not prevent the core bot from starting.

## Adaptive local AI core

`message -> compact memory context -> heuristic complexity route -> Ollama -> quality guard -> memory`

- **Fast route:** `OLLAMA_FAST_MODEL`, normally Qwen3.5 2B Q4_K_M.
- **Smart route:** `OLLAMA_SMART_MODEL`, normally Qwen3.5 4B when RAM allows.
- No second classifier LLM call is used. Complexity is determined locally from prompt structure/intent.
- Only one local model is intentionally kept resident at once. Switching unloads the previous model before the next one is attempted.
- Simple chat gets a smaller token budget and no thinking mode; analysis/code can use the stronger route and thinking.
- A second review generation is disabled when a dedicated smart route is active, reducing latency.

## Optional/local services

- **Redis**: persistent/distributed FSM; otherwise `MemoryStorage`.
- **Ollama**: local text AI.
- **Piper**: local neural TTS.
- **whisper.cpp**: local speech-to-text.
- **ComfyUI**: local image generation.
- **Pyrogram**: optional Telegram helper; startup does not depend on it.
- **FastAPI panel/Mini App**: optional web surfaces.
- **Shared HTTP pool**: bounded aiohttp connections for web/search helpers.
- **yt-dlp + DDGS**: public media/social metadata, search and downloads.

## Media/social core

`query -> provider search -> expiring user-bound selection -> validated public URL -> bounded download -> Telegram upload`

Search callbacks expire and are bound to the initiating Telegram user. The downloader does not intentionally bypass DRM/private access or load browser cookies. Twitch live streams are not exposed as unbounded file downloads.

## Persistent data

Everything mutable should live under `DATA_DIR`:

- `database.db` and SQLite WAL files;
- `logs/`;
- `backups/`;
- updater state / optional Pyrogram session data.

SQLite schema changes use the existing safe missing-column synchronizer. Kira 1.1 adds the per-chat `speech_style` field this way, so old databases remain usable.

## Background runtimes

- reminder scheduler;
- hourly maintenance (cleanup + SQLite optimize/checkpoint);
- periodic database backup;
- optional FastAPI admin server;
- service watchdog.

All are started and stopped from the main bot lifecycle rather than detached fire-and-forget tasks.

## Extension points

Drop optional modules in `bot/plugins/`. A plugin may expose an aiogram `router` or `setup(router)`. Kira 1.1 keeps media/social user commands in an optional plugin while the reusable service lives in `bot/social_media.py`.
