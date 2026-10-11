# Security notes

KiraBot accepts user-controlled URLs and files, so deployment should be treated as an
internet-facing service.

- Never commit `.env`, Telegram tokens, Gemini keys or panel tokens.
- Keep the web panel on `127.0.0.1` unless it is behind HTTPS and an authenticated reverse proxy.
- Use a random `PANEL_TOKEN` of at least 24 characters.
- Keep `INTERNET_MAX_DOWNLOAD_MB`, `MEDIA_MAX_DOWNLOAD_MB` and `FILE_ANALYSIS_MAX_MB`
  appropriate for the server's RAM/disk and Telegram upload mode.
- Public downloader/research code blocks loopback, private, link-local and non-global addresses.
- Downloaded content is treated as data and is never executed by KiraBot.
- Use Redis authentication/TLS when Redis is not on a private Docker network.
- Back up `DATA_DIR` before schema or application upgrades.
- Run `/doctor` after deployment and `/doctor full` only when you intentionally want live external checks.

Report vulnerabilities privately to the project maintainer rather than posting secrets or exploit
payloads in public issue trackers.
