# KiraBot 0.6.1 — AI Quality Fix

This release focuses on one problem: Kira sometimes answered with unrelated, repetitive or nonsensical text.

## Main fixes

- Stronger normal-chat prompt that prioritizes the latest user message.
- Compact clean memory instead of dumping large mixed RP/chat history into the model.
- RP and mature sessions no longer contaminate normal assistant memory.
- Normal chat temperature is 0.45; creative RP is 0.72; research is 0.25.
- Qwen/Ollama hidden thinking is disabled and reasoning/template artifacts are stripped.
- Obvious repetition loops are rejected and fail over to the next model/provider.
- Current quality-oriented Groq model defaults.
- `ai_quality.sh` can upgrade local Ollama quality without exposing or replacing Telegram/API secrets.

## After updating

If old bad replies are still influencing one chat, run `/ai_reset` once in that chat.

If you rely mainly on Ollama, optionally run:

```bash
bash ai_quality.sh
```

Then use `/ai_providers` and `/ai_health` to see the active provider/model.
