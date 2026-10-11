# Upgrade report: 0.7.0 → 0.8.0

The upgrade is designed to preserve the existing `.env`, SQLite data, Docker volumes and user state.

Key migration points:

- SQLite auto-migration adds `users.last_work_at` and `users.bio` without deleting existing rows.
- `SUPPORT_CHAT_ID` is merged into `.env` by `setup.sh`; the obsolete direct `ADMIN_CHAT_URL` setting is no longer used by the application.
- Historical untouched Ollama defaults are migrated to `qwen3.5:2b-q4_K_M,qwen3:1.7b`; custom model choices are not blindly overwritten by the setup migration.
- `ai_quality.sh` is the explicit quality migration path. It selects Qwen3.5 2B Q4_K_M below 6 GB RAM and Qwen3.5 4B Q4_K_M at 6+ GB, then keeps Qwen3 1.7B as a light fallback.
- Support requests are private: group buttons/commands redirect users to the bot's private `start=support` deep link.
