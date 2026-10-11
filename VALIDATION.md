# KiraBot 0.8.0 validation

Validated during the 0.8.0 support/economy/local-AI upgrade.

## Passed

- All Python files under `bot/` compile with `python -m py_compile`.
- `setup.sh` and `ai_quality.sh` pass `bash -n`.
- 66 available regression/static tests pass, including support/help, local-only AI, model sequencing, economy/profile, community, rules, reliability, upgrade and legacy command protection.
- `/help` catalog contains all 98 slash commands statically registered under `bot/handlers/`.
- Telegram help pages stay comfortably below the 4096 character message limit before legacy extensions.
- Existing frozen `bot/handlers/masturbate/` files keep their historical SHA256 values; the shared SQL test now validates that feature's data contract rather than freezing the entire evolving database module.

## Environment limitation

A full `pytest` collection cannot run in this artifact-build environment because `aiosqlite` and `aiogram` are not installed here. The two affected runtime test modules fail during import/collection before executing project assertions. Production dependencies remain declared by the project and are installed by the normal Docker/uv deployment path.

## Deployment prerequisites

- Add Kira to `@kira26481` (the support chat) and allow it to send messages.
- Keep `SUPPORT_CHAT_ID=@kira26481`, or replace it with the numeric Telegram chat ID if preferred.
- Run `bash ai_quality.sh` after upgrade to pull/apply the local Ollama model profile.
