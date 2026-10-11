# KiraBot 2.16.1 Colorful installer

- `install.sh`: banner, 5 numbered steps with progress bars, animated spinners for quiet steps (output is kept and the tail is shown on failure), server summary (OS, CPU, RAM, free disk), install plan with sizes and a disk-space check, final "done" box with next commands. `--plan` prints the plan and changes nothing. Honors `NO_COLOR` and works without a TTY.
- Downloads everything the bot needs: Docker/Compose, git/curl, images (bot, Redis, Ollama, voice/STT), local models (fast, smart on RAM ≥ 6 GB, fallback, `OLLAMA_ADULT_MODEL`), Piper voices, Whisper model, and local ComfyUI automatically when the server has RAM ≥ 6 GB and ≥ 25 GB free (`KIRA_LOCAL_IMAGE=auto|1|0`).
- With an existing `.env` (used as is) every model it mentions is pulled: `OLLAMA_MODELS`, `OLLAMA_MODEL`, `OLLAMA_FAST_MODEL`, `OLLAMA_SMART_MODEL`, `OLLAMA_ADULT_MODEL`.
- `setup.sh` output is colored with step headings.
- masturbate and alcohol modules untouched.

## Existing .env is found and used automatically
- `install.sh` looks for a `.env` with `TOKEN` (project dir, `ENV_FILE=…`, working dir of a running Kira container, `~/Kira*`, `/opt`, `/srv`, `/home/*`), copies it into the project folder (original untouched), continues the previous compose project (same data volumes) and never asks for token/ID. If `.env` has no `TOKEN` it stops with a clear message instead of asking.
- `setup.sh` now skips the wizard whenever `.env` already has a `TOKEN` (`KIRA_RECONFIGURE=1` brings the wizard back).

## Wider .env search (fix: installer still asked for the token)
The installer now looks for the existing `.env` in this order: `ENV_FILE`, project folder, working dir of a (stopped or running) Kira container, folder of a running `python -m bot` process, usual places, then a deep search of /root, /home, /opt, /srv, /var, /usr/local, /data, /mnt… (any `.env`, `*.env`, `.env.*` with a valid `TOKEN=`; quoted tokens accepted), and finally the environment of the old Kira container. It prefers files that look like Kira's (OLLAMA_*, AI_*, KIRA_*…), uses a lone unrelated match with a warning, refuses to guess between several other bots' files, and uses `.env.backup-*` only if nothing else exists. If nothing is found and a terminal is attached it asks for a PATH (not the token).
