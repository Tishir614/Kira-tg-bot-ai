# KiraBot 2.3.0 Stability & Recovery

- Qwen2.5 1.5B local profile retained and hardened against cross-turn duplicate answers.
- Bounded AI generation, one retry for verbatim duplicate output, serialized local inference and existing provider timeouts remain enabled.
- Stable Docker volume name `kira-persistent-data` prevents database resets when the project directory/version changes.
- `upgrade_2_3.sh` discovers the largest previous `*kira-data*` SQLite database when the persistent volume is empty, copies the complete data directory, creates backups on later upgrades, and runs SQLite integrity_check.
- Existing crash recovery remains enabled: incident fingerprints, SQLite maintenance, owner notification, bounded self-restart and crash-loop protection.
- Existing `/doctor` and `/recovery` diagnostics are retained.
- Mature mode/persona is retained for adult conversation and profanity while existing safety boundaries remain in place.
- No features are intentionally disabled.
- Masturbate and alcohol modules are intentionally untouched.
