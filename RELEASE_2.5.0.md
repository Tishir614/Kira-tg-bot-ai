# KiraBot 2.5.0 Uncensored RP & Furry Images

## Added
- `/rp` (рп): smart RP module (`bot/rp_engine.py`, `bot/handlers/rp.py`). Persistent scenes, character cards for Kira and the user (`/rp char`, `/rp me`), world/genre, rolling auto-summary every 8 turns, `retry`, `undo`, `recap`, `pause/resume/stop`, `(( out of character ))`. The director prompt forbids controlling the user's character, pushes the plot forward and keeps continuity.
- Perchance furry-ai image provider (`bot/perchance_furry.py`), tried first, ComfyUI as fallback (`IMAGE_PROVIDERS`). **Perchance has no public API; the client follows the generator page's requests and could not be tested from the build sandbox (perchance.org blocked). If it breaks, adjust the PERCHANCE_* settings or it silently falls back to ComfyUI.**
- Russian image prompts: translated to English booru-style tags by the LLM (`bot/prompt_translate.py`), offline glossary fallback.

## Changed
- Removed the explicit-image block and the "non-explicit" prompt suffixes.
- System prompt: no moralizing/disclaimers/refusals for fiction; adult RP prompt allows dark and hard fictional scenes between adults.
- `/mature accept` in a private chat now also enables Mature Mode.

## Kept on purpose
- One-time `/mature accept` 18+ confirmation (responsibility of the operator; needed in group chats).
- Hard line: no sexual content with minors (text and images; image prompts mentioning children/ages under 18 are rejected) and no real-world harm.

## AI Horde (added)
- `bot/horde_client.py`: official AI Horde API, anonymous key `0000000000` by default (`HORDE_API_KEY` to use your own). Requests `nsfw=true`, `censor_nsfw=false`, picks live furry models (Fluffyrock, Furry Epoch, yiffy, Pony Diffusion XL...) via `HORDE_MODELS`. Provider order: `IMAGE_PROVIDERS=horde,perchance,comfyui`; each failure falls through to the next.
- Written from the public API docs and unit-tested with a mocked server; not run against the live service from the build sandbox. Horde itself refuses CSAM and may queue anonymous jobs for minutes.
