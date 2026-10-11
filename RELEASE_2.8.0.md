# KiraBot 2.8.0 Light Core

## Faster
- `respond()` now runs its six DB lookups (history, speech style, nickname, profile, summary, facts) concurrently instead of one by one.
- RP: the reply is sent first; the history summary pass and TTS no longer delay the text. Turns of one scene are serialized with a lock so nothing is lost.
- `KIRA_LIGHT_MODE=auto|1|0` (auto = RAM < 6 GB): web grounding timeout 3 s instead of 7 s, background memory folding every 16 messages instead of 8 and only while the model is idle, RP summary every 16 turns instead of 8.

## Untouched
- masturbate and alcohol modules.
