# KiraBot 2.17.0 Horde hardening

AI Horde client rewritten to survive the usual anonymous-key failures:
- Anonymous key: size is clamped to ≤ 512×512 pixels (aspect ratio kept, multiples of 64) and ≤ 25 steps, avoiding the `KudosUpfront` rejection; a rejection triggers one minimal retry (512×512, 20 steps).
- SD1.5 furry models are preferred (small canvases work); SDXL/Pony only if nothing else is live. `clip_skip=2` for furry checkpoints.
- No live worker / `is_possible=false` / "No active worker" -> automatic retry with general models (`HORDE_FALLBACK_MODELS`); the abandoned job is cancelled.
- 429 rate limit -> wait and retry; anonymous jobs are serialized (1 at a time). Censored/faulted results -> resubmitted.
- Age words are stripped from the negative prompt sent to Horde (our own minors guard still runs first).
- WebP results are converted to JPEG for Telegram.
- `/image_health` now performs a Horde `dry_run` of the real payload: it verifies the key, size limits and models without queuing a job, and shows the exact rejection if any.
- A free personal key (`HORDE_API_KEY`, https://aihorde.net/register) lifts the anonymous limits.
