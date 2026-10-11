# KiraBot 2.15.0 Adult model

- `OLLAMA_ADULT_MODEL`: dedicated local model for 18+/RP sessions (any uncensored/abliterated Ollama model). It is tried first in adult sessions (age confirmed + Mature Mode, RP director prompts); the normal chain stays as fallback. `setup.sh`/`install.sh` pull it automatically when it is set in `.env`. Reported as `adult_model` by the AI speed status.
- masturbate and alcohol modules untouched.
