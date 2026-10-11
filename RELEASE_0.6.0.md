# KiraBot 0.6.0 — Local Media

This release moves Kira image generation and TTS off cloud providers.

## Local TTS
- Piper TTS, no API key.
- `ru_RU-irina-medium` and `en_US-lessac-medium`.
- Models persist in `/app/static/piper`.
- Output is converted to OGG/Opus for Telegram voice messages.

## Local images
- stable-diffusion.cpp runs on the Docker network only.
- The setup wizard can enable the `image` profile.
- The default public SD 1.5 checkpoint is downloaded once (~4.3 GB) into a Docker volume.
- Default render size: 512×512, 20 steps. CPU inference can take several minutes.

## Reliability
- Character creation FSM stores only JSON-safe primitives in Redis. This fixes `TypeError: Object of type Message is not JSON serializable`.
