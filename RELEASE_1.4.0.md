# KiraBot 1.4.0 — OmniGet + SketchForge 3D

- OmniGet CLI 0.9.2 pinned inside the Kira image.
- `/скачать URL`, `/аудио URL`, `/инфо URL` and `/omniget` integration.
- URL validation and subprocess isolation; no shell interpolation.
- SketchForge 3D runs as an optional isolated Docker service (`--profile 3d`).
- SketchForge image pinned to `ghcr.io/formsmith746/sketchforge-3d:sha-4f3859f`.
- Persistent `kira-sketchforge-projects` volume.
- `/3d` and `/sketchforge` open the editor from Telegram.
- Nginx `/sketchforge/` reverse proxy added for HTTPS deployments.

## Start

```bash
docker compose --profile voice --profile image --profile 3d --profile webapp up -d --build
```

Set `KIRA_WEBAPP_URL=https://your-domain/kira`. Kira automatically derives
`https://your-domain/sketchforge/`, or set `SKETCHFORGE_PUBLIC_URL` explicitly.

Existing Kira data volumes are unchanged. Never update with `docker compose down -v`.
