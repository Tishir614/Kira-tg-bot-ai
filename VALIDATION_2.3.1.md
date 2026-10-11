# Validation 2.3.1

- `python -m compileall bot`: PASS in build workspace.
- Protected module source comparison against 2.3.0: PASS for `bot/handlers/masturbate/**` and `bot/handlers/alcohol/**`.
- Changes are additive/fallback-safe: Vision Brain pass falls back to the raw Kimi-VL result on failure.
- Full Docker/Telegram/Ollama/Redis integration must be smoke-tested on the deployment server because those services are not present in the build workspace.
