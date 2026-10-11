# KiraBot 1.0.0 — Memory Core

Крупный local-first релиз.

## Новое
- Долговременная память: `/memory`, `/remember`, `/forget_me`.
- Настройки приватности `/privacy`; память истории группы выключена по умолчанию.
- Память чата и локальный semantic/fuzzy поиск `/find_memory`.
- Сводки `/digest 24h`.
- Контекстный AI-модератор `/aimod off|assist|auto 1..5`.
- AI-панель администратора `/admin_ai ...` с подтверждением перед применением.
- Локальная STT через whisper.cpp + `/summary_voice`; Piper остаётся локальным TTS.
- Характер Киры `/personality normal|friendly|serious|humorous|rp`.
- Kira Mini App: `/kira_app` и веб-маршрут `/kira`.
- Контент: `/rewrite`, `/fixtext`, `/translate`, `/congrats`, `/avatar`, `/meme`.
- Новые функции изолированы в плагине `bot/plugins/kira_1_0.py`.

## Local AI
- Текст: Ollama.
- Голос -> текст: whisper.cpp.
- Текст -> голос: Piper.
- Изображения: stable-diffusion.cpp.

Для локальных путей API-ключи не обязательны.
