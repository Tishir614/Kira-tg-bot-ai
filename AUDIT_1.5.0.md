# KiraBot 1.5.0 audit

## Checks performed
- Parsed every Python module under `bot/`.
- `compileall` passed for bot/tests/tools/deploy.
- Shell syntax passed for setup and upgrade scripts.
- Docker Compose YAML parsed and service references were checked.
- Basic accidental-secret scan passed.
- 27 targeted regression tests passed.

## Image backend finding
The 1.4 image path depended on a custom stable-diffusion.cpp build/wrapper and an old SD1.5 GGUF. It has been removed from the active stack. Kira now submits a stock-node workflow to ComfyUI v0.36.0 and uses DreamShaper 8 pruned safetensors by default.

## Environment limitation
A complete dependency install/full historical pytest suite could not be run in this build sandbox because outbound package resolution is unavailable and the sandbox lacks aiogram/aiosqlite. This is not reported as a full runtime deployment test.
