# Идеи развития Kira после обзора GitHub

Доступные репозитории показывают три полезных направления: отдельное AI-ядро, большой Telegram/web прототип и несколько пустых/экспериментальных Kira-репозиториев. Вместо копирования кода между ними стоит постепенно свести функции в один стабильный KiraBot.

Приоритеты:
1. Unified activity/streak engine: серии активности, ежедневные задания и достижения.
2. Event bus + feature flags: любой тяжёлый модуль можно выключить без падения бота.
3. Health dashboard Mini App: состояние Ollama/ComfyUI/STT/TTS/Redis/D&D/OmniGet/SketchForge.
4. Recovery supervisor: circuit breaker, таймауты, retry и понятный degraded mode для внешних сервисов.
5. AI tool permissions: отдельные разрешения owner/admin/public для памяти, генерации, загрузок и админ-действий.
6. Group games framework: алкошкала, хвост, дроч, викторины и будущие игры на общем движке cooldown/stats/top.
7. Semantic chat recall с подтверждением памяти и удалением пользовательских данных.
8. Achievements/leaderboards в Mini App с прозрачной историей начислений.
