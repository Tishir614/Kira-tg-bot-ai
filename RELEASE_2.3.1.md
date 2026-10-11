# KiraBot 2.3.1 Living Core

Incremental reliability/personality update on top of 2.3.0. Existing features remain enabled.

## Added
- Deterministic Smart Router modes: chat, creative, tech, analysis. No extra classifier model call.
- Tech/analysis routes use a steadier lower temperature; creative requests keep the creative profile.
- Memory deduplication prevents reconnect/retry paths from storing consecutive identical turns.
- Vision -> Brain pass: Kimi-VL extracts visual facts, then the main Qwen model composes the final Kira-persona response with conversation memory. If the second pass fails, raw vision still works.
- `/crashes` is an alias for the existing recovery journal.
- `KIRA_VISION_BRAIN_PASS=1` switch. It can be disabled without disabling Vision.

## Preserved
- Persistent database migration and integrity checks from 2.3.0.
- Crash-loop protection, watchdog, recovery journal and background-service restart.
- Existing commands/plugins remain enabled.
- Masturbate and alcohol modules were not modified; their source hashes match 2.3.0.
