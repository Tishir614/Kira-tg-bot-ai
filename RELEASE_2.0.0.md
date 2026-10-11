# KiraBot 2.0.0 — Living World

- Persistent per-chat **Kira World** stored atomically in `DATA_DIR/kira_world.json`.
- `/kira_world` / `мир киры`: mood, energy, chat warmth, current activity, event and boss.
- `/pet` / `погладить`: raises chat warmth, changes Kira's mood and grants a tiny XP reward.
- `/quest` / `событие киры`: starts a lightweight group event.
- `/boss` / `босс`: cooperative chat boss with random damage, crits, XP and coin rewards.
- Plugin remains isolated by the existing plugin loader, so a load failure does not take the whole bot down.
- Existing 1.9 side effects, Premium Emoji, economy, inventory, relationships and Crash Guard are preserved.
