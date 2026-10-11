# KiraBot 0.6.2 — Sequential Local AI

Local inference now uses **Qwen3 1.7B first, then Llama 3.2 3B only as a fallback**.

- Primary: `qwen3:1.7b`
- Fallback: `llama3.2:3b`
- No parallel requests between these models.
- Ollama receives `keep_alive: 0s`, so a completed/failed model is unloaded before another local model is loaded.
- Cloud Groq/Hugging Face remain later fallbacks if configured.

This is designed for low-memory VPS deployments. Downloading both models stores both on disk; it does not mean both are kept in RAM.
