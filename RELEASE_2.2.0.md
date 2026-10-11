# KiraBot 2.2.0 AI Reliability

- Основной локальный AI: Qwen2.5 1.5B Instruct uncensored Q4_K_M через Ollama.
- Параметры генерации адаптированы для небольшой 1.5B модели.
- Системный prompt Kira закрепляет контекст, память, техническую точность и естественную лексику.
- Локальный Kimi-VL подключён к существующим /vision и поиску похожих изображений через OpenAI-compatible llama.cpp endpoint.
- Docker получает host.docker.internal на Linux для доступа к локальному vision server.
- Исправлена Compose-интерполяция FILE/URL в model downloader.
- Добавлены regression tests для AI/vision/Compose.
- Модули alcohol и masturbate не изменялись.
