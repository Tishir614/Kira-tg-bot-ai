# KiraBot 0.5.2 — D&D Hub

Релиз добавляет Telegram Mini App для совместимых с d20 механик без копирования текста официальных правил.

## Запуск

1. Сохраните существующие `.env` и `static`.
2. Задайте `DND_WEBAPP_URL=https://домен.example/dnd` (Telegram требует HTTPS для публичного WebApp).
3. Запустите `docker compose up -d --build`.
4. Откройте `/dnd` командой `/dnd`.

API проверяет `X-Telegram-Init-Data` через HMAC-SHA256 и срок действия `auth_date`; переданный клиентом user_id не используется для авторизации.

## Проверки

`compileall` и `bash -n` проходят. В текущем рабочем окружении пакет `pytest` не установлен; CI проекта установит dev-зависимости из `pyproject.toml` и выполнит полный набор тестов.
