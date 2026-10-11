# KiraBot 2.16.1 Colorful installer

- `install.sh`: banner, 5 numbered steps with progress bars, animated spinners for quiet steps (output is kept and the tail is shown on failure), server summary (OS, CPU, RAM, free disk), install plan with sizes and a disk-space check, final "done" box with next commands. `--plan` prints the plan and changes nothing. Honors `NO_COLOR` and works without a TTY.
- Downloads everything the bot needs: Docker/Compose, git/curl, images (bot, Redis, Ollama, voice/STT), local models (fast, smart on RAM ≥ 6 GB, fallback, `OLLAMA_ADULT_MODEL`), Piper voices, Whisper model, and local ComfyUI automatically when the server has RAM ≥ 6 GB and ≥ 25 GB free (`KIRA_LOCAL_IMAGE=auto|1|0`).
- With an existing `.env` (used as is) every model it mentions is pulled: `OLLAMA_MODELS`, `OLLAMA_MODEL`, `OLLAMA_FAST_MODEL`, `OLLAMA_SMART_MODEL`, `OLLAMA_ADULT_MODEL`.
- `setup.sh` output is colored with step headings.
- masturbate and alcohol modules untouched.
