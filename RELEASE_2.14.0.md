# KiraBot 2.14.0 Variants & One-command Installer

- Multiple image variants: add `количество:N` (also `вариантов:N`, `count:N`; max `IMAGE_MAX_VARIANTS`, default 4) to `/image`, `/kira_image`, `/me_image`. Variants are generated two at a time and sent as one album; failed ones are skipped ("Готово: 3 из 4"). A button message under the album repeats or changes style.
- `install.sh`: one-command installer. Installs git/curl/python3 and Docker + Compose, clones or updates the project, backs up an existing `.env`, then runs `setup.sh` in automatic mode (`KIRA_AUTO=1`: no questions except TOKEN/OWNER_ID if missing). Free online image generators are used by default; `KIRA_LOCAL_IMAGE=1` also installs local ComfyUI.
- `setup.sh`: new automatic mode, and it now appends new defaults from `example.env` (image providers, AI Horde, anti-hang limits) without touching existing values.
- masturbate and alcohol modules untouched.

## .env is never modified by the installer
- If `.env` exists, `install.sh` exports `KIRA_KEEP_ENV=1` and `setup.sh` uses the file exactly as is: no questions, no rewrite, no merge, no chmod, no legacy-default `sed`. Services (Ollama, ComfyUI, panel) are chosen by reading its values. A backup copy `.env.backup-*` is placed next to it. Verified by a test that runs the real `setup.sh` against a fake docker and compares bytes, mtime and permissions.
- `NO_ENV_MERGE=1 bash deploy.sh` does the same for updates.
