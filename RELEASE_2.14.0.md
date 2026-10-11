# KiraBot 2.14.0 Variants & One-command Installer

- Multiple image variants: add `количество:N` (also `вариантов:N`, `count:N`; max `IMAGE_MAX_VARIANTS`, default 4) to `/image`, `/kira_image`, `/me_image`. Variants are generated two at a time and sent as one album; failed ones are skipped ("Готово: 3 из 4"). A button message under the album repeats or changes style.
- `install.sh`: one-command installer. Installs git/curl/python3 and Docker + Compose, clones or updates the project, backs up an existing `.env`, then runs `setup.sh` in automatic mode (`KIRA_AUTO=1`: no questions except TOKEN/OWNER_ID if missing). Free online image generators are used by default; `KIRA_LOCAL_IMAGE=1` also installs local ComfyUI.
- `setup.sh`: new automatic mode, and it now appends new defaults from `example.env` (image providers, AI Horde, anti-hang limits) without touching existing values.
- masturbate and alcohol modules untouched.
