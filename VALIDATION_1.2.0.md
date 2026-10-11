# Validation — KiraBot 1.2.0

Проверено перед упаковкой финального архива:

- `python -m compileall` для `bot/`, `tests/`, `tools/` и локального image-wrapper — без синтаксических ошибок.
- JavaScript единого Kira Mini App проверен через `node --check` — без синтаксических ошибок.
- `bash -n` для `setup.sh`, `upgrade_1_2.sh` и `local_media.sh` — без ошибок shell-синтаксиса.
- 22 целевых теста релизов 1.0.2/1.1/1.2, русских алиасов и D&D/Mini App — passed.
- 140 русских slash-алиасов, без коллизий значений.
- Локальный image-wrapper smoke-test с фальшивым `sd-cli`: `/health` и `/generate` вернули успешный ответ/PNG.
- Проверена совместимость флагов текущего `stable-diffusion.cpp`: `-W/--width`, `-H/--height`, `--steps`, `--threads`, `-n/--negative-prompt`, `-o/--output`.
- Dockerfile image-wrapper копирует весь `build/bin`, включая runtime-библиотеки ggml CPU backend, а не только бинарник `sd-cli`.
- Piper приведён к CLI `piper-tts 1.8+` и в runtime, и в `setup.sh`; legacy fallback оставлен только для старых установок.
- Финальный ZIP проверяется через `unzip -t` после упаковки.

Полный исторический `pytest` в рабочем контейнере не собирается из-за отсутствующих в этой среде runtime-пакетов `aiogram`/`aiosqlite`. Это ограничение среды проверки, а не падение тестов релиза. В Docker проекта эти пакеты объявлены в `pyproject.toml` и устанавливаются при сборке.
