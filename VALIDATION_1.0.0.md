# Validation 1.0.0

Validated in the build workspace:
- Python syntax/AST parse: all bot Python files pass.
- `python -m compileall -q bot`: pass.
- `bash -n setup.sh`: pass.
- `bash -n local_media.sh`: pass.
- project version: `1.0.0`.

Full pytest was not runnable in the artifact workspace because runtime dependencies (`aiogram`, `aiosqlite`) are not installed there. This is an environment limitation rather than a collected test failure in Kira itself.

External interfaces checked against current upstream docs:
- stable-diffusion.cpp exposes `/sdapi/v1/txt2img` and `/sdapi/v1/sd-models`.
- whisper.cpp server exposes multipart `/inference`, `--convert`, `--language`, and `--no-timestamps`.
