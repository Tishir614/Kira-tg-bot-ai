# Validation 2.2.0

## Проверено в сборке

- Python compileall: PASS.
- Новый regression-набор 2.2 + reliability/aliases/files/internet/social: 37 PASS.
- Russian slash aliases дополнены для plugin-команд boss/effects/kira_life/kira_world/pet/quest.
- Local vision теперь использует KIRA_VISION_URL/KIRA_VISION_MODEL и существующие /vision + /similar.
- Compose host-gateway добавлен для Linux; FILE/URL shell variables экранированы от Compose interpolation.
- alcohol и masturbate: исходные файлы не изменены.

## Старые тесты 1.2

Некоторые исторические tests/test_release_120_repair_pack.py проверяют буквально version=1.2.0 и старую архитектуру image/D&D. Эти проверки устарели относительно 2.0 и не являются runtime-регрессиями 2.2. Они не использовались как критерий новой версии.

## Что требует реального сервера

Telegram Bot API, Redis, Ollama model load, Kimi-VL endpoint, ComfyUI/SD, whisper/Piper и публичный Mini App URL требуют интеграционного smoke-test после деплоя, потому что эти сервисы отсутствуют в локальной среде сборки.
