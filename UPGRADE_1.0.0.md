# Upgrade to Kira 1.0.0

1. Back up `.env` and `static/kira.sqlite3`.
2. Replace application files with this release.
3. Merge new variables from `example.env`.
4. Start local services:

```bash
docker compose --profile ollama --profile image --profile voice up -d --build
```

5. For Mini App set `KIRA_WEBAPP_URL=https://YOUR_DOMAIN/kira` and proxy `/kira` + `/api/kira/*` to Kira's FastAPI port.
6. In Telegram, enable group memory explicitly with `/privacy chat on` if wanted.
7. Test: `/memory`, `/aimod assist 3`, `/digest 24h`, reply `/summary_voice` to a voice note, `/image fox under neon rain`, `/kira_app`.

Existing SQLite tables are preserved. New Kira 1.0 tables are created automatically through SQLAlchemy `create_all`.
