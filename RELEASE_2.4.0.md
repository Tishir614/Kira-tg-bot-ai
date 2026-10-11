# KiraBot 2.4.0 Smart Memory

## Added
- `bot/smart_router.py`: deterministic request router (chat / creative / tech / analysis). No extra model call; tech and analysis get a steadier temperature and the deliberate route, creative a warmer one. Current mode is exposed in `speed_status()["mode"]`.
- `bot/user_facts.py` + `UserFactManager` (table `user_facts`, created automatically): Kira remembers what a user says about themselves (name, age, city, job, likes, dislikes, hobby) via regex, no model call, and adds it to the prompt as data, not instructions. Prompt-injection-looking values and roleplay turns are ignored; single-value facts (name, city...) are replaced by newer ones; max 30 per user. `UserFactManager.forget(user_id)` wipes them.
- Memory dedupe: a consecutive identical turn is no longer stored twice.

## Notes
- 2.3.1 release notes mention Smart Router, memory dedupe and the Vision->Brain pass, but the archive's code contained none of them. Router and dedupe are now implemented; the Vision->Brain pass is still not.
- 11 older tests fail on the unmodified archive (stale version/path assertions, the frozen-hash check on `masturbate/commands.py`); they are unrelated to this release.
