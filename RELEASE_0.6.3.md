# KiraBot 0.6.3 — Local-only AI

- Text AI is hard-locked to local Ollama inference.
- Sequential model chain: `qwen3:1.7b` → `llama3.2:3b`.
- Only one local model is loaded at a time (`keep_alive: 0s`).
- Groq and Hugging Face Inference are disabled even if stale keys remain in an old `.env`.
- `setup.sh` no longer asks for cloud AI keys.
- `ai_quality.sh` removes stale Groq/HF AI keys and forces `AI_LOCAL_ONLY=1` plus `AI_PROVIDER_ORDER=ollama`.
- `/ai_providers` and `/ai_health` now report local-only status.
- Local Piper TTS and local image generation remain unchanged.
