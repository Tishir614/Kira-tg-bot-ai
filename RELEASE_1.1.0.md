# KiraBot 1.1.0 — Adaptive Core + Media Hub + Social

## AI core

- Added heuristic adaptive local routing without a second classifier request.
- Fast route: `OLLAMA_FAST_MODEL` (default/recommended `qwen3.5:2b-q4_K_M`).
- Smart route: optional `OLLAMA_SMART_MODEL` (`qwen3.5:4b` on servers with enough RAM).
- Simple chat gets a smaller output budget and `think=false`; complex analysis/code uses the smart route and reasoning.
- When a dedicated smart model is active the old second review pass is skipped, avoiding two expensive generations for one answer.
- `OLLAMA_KEEP_ALIVE` recommendation raised to 10m to reduce repeated cold loads.
- `/скорость_ии` now exposes route, fast/smart model, load time and generation time.
- `ai_quality.sh` detects server RAM, pulls the appropriate models and configures the adaptive route locally.

## Free speech style

- New `/мат выкл|умеренно|вкл` command.
- Speech style is persisted per chat in SQLite and auto-migrates on existing databases.
- `free` mode allows natural uncensored profanity without forcing it into every sentence.
- This affects tone only. Privacy, anti-spam, permission checks, secret redaction and server-safety controls stay enabled.
- The AI admin proposal engine can understand requests such as «Кира, включи свободный мат» and still requires confirmation.

## Search + downloads

- `/найти_видео <запрос>`: multiple YouTube search results, then choose what to download.
- `/найти_музыку <запрос>`: search and download the selected result as audio.
- `/найти_картинку <запрос>`: image search plus a download button for each result.
- Search selections expire after 15 minutes and can only be used by the user who started the search.
- Existing `/поиск`, `/скачать`, `/видео`, `/аудио` remain compatible.

## YouTube / TikTok / Twitch

- `/ютуб <query|URL>`: public search, metadata and video/audio download actions.
- `/тикток <query|URL>`: public search, metadata and supported public-video downloads.
- `/твич <channel|URL>`: channel/search metadata and clip/VOD handling where supported.
- Active Twitch live streams are not offered as unbounded downloads.
- yt-dlp is used without browser-cookie theft or DRM/private-access bypassing.

## Compatibility

- Old English command names remain valid.
- All new slash commands have Russian aliases and are included in the command catalogue.
- Existing `.env`, SQLite data and Docker volumes can be kept.
