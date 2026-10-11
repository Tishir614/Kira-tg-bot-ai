# KiraBot 2.11.0 No-Hang & Smarter Modes

## No more hanging
- `bot/ai_guard.py`: bounded wait for the model slot (`AI_QUEUE_TIMEOUT`, 90 s), bounded queue (`AI_MAX_QUEUE`, 6) and a per-chat backlog limit (`AI_USER_BACKLOG`, 2). Overload now yields a polite "try again in a minute" instead of piling up.
- Hard overall deadline per answer (`AI_TOTAL_TIMEOUT`, 240 s); a hung model is cancelled and the conversation lock and model slot are released. Optional review pass is skipped when half the budget is spent.
- Busy replies are not counted as AI failures (no false owner alerts); timeouts are, and show up in `/stats` as `ai_timeout` / `ai_busy`.

## Smarter
- Mode-specific guidance (tech: verify conditions, full code, state assumptions, ask one precise question; analysis: conclusion, arguments, risks, facts vs guesses; creative; chat: short and human) appended to the default prompt only.
- Language mirroring for clearly non-Russian prompts.

masturbate and alcohol modules untouched.
