# Upgrade to KiraBot 1.1.0

1. Replace project files while preserving the current `.env` and Docker volumes.
2. From the project directory run:

```bash
bash upgrade_1_1.sh
```

The script backs up `.env`, detects RAM, configures the adaptive Ollama route, downloads missing local models, rebuilds Kira and does not run `docker compose down -v`.

After upgrade check:

```bash
docker compose ps
docker compose logs --tail=100 kira
```

Telegram checks:

```text
/скорость_ии
/мат
/найти_видео test
/ютуб test
/тикток test
/твич channel_name
```
