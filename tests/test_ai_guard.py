import asyncio
from unittest.mock import AsyncMock

import pytest

from bot import smart_router
from bot.ai_client import AIUnavailable, AssistantMemoryManager, KiraAI, UserFactManager
from bot.ai_guard import AIBusy, AdmissionGate


def test_gate_rejects_when_queue_full(monkeypatch):
    monkeypatch.setenv("AI_MAX_QUEUE", "1")
    monkeypatch.setenv("AI_QUEUE_TIMEOUT", "5")

    async def scenario():
        sem, gate = asyncio.Semaphore(1), AdmissionGate()
        started = asyncio.Event()

        async def holder():
            async with gate.slot(sem):
                started.set()
                await asyncio.sleep(0.3)

        async def waiter():
            async with gate.slot(sem):
                return "ok"

        h = asyncio.create_task(holder())
        await started.wait()
        w = asyncio.create_task(waiter())
        await asyncio.sleep(0.05)
        with pytest.raises(AIBusy):  # second waiter exceeds cap of 1
            async with gate.slot(sem):
                pass
        assert await w == "ok"
        await h
        assert not sem.locked() and gate.waiting == 0
    asyncio.run(scenario())


def test_gate_wait_timeout(monkeypatch):
    monkeypatch.setenv("AI_QUEUE_TIMEOUT", "5")
    import bot.ai_guard as g
    monkeypatch.setattr(g, "queue_timeout", lambda: 0.05)

    async def scenario():
        sem, gate = asyncio.Semaphore(1), AdmissionGate()
        await sem.acquire()
        with pytest.raises(AIBusy):
            async with gate.slot(sem):
                pass
        assert gate.waiting == 0
    asyncio.run(scenario())


def _client(monkeypatch):
    client = KiraAI()
    monkeypatch.setattr(client, "_require_ai", lambda: None)
    monkeypatch.setattr(AssistantMemoryManager, "context", AsyncMock(return_value=[]))
    monkeypatch.setattr(AssistantMemoryManager, "add", AsyncMock(return_value=[]))
    monkeypatch.setattr(UserFactManager, "remember", AsyncMock())
    monkeypatch.setattr(UserFactManager, "list", AsyncMock(return_value=[]))
    return client


def test_total_timeout_aborts_hung_model(monkeypatch):
    import bot.ai_client as ac

    async def hang(*a, **k):
        await asyncio.sleep(30)

    async def scenario():
        client = _client(monkeypatch)
        monkeypatch.setattr(ac, "total_timeout", lambda: 0.2)
        monkeypatch.setattr(client, "_text_failover", hang)
        with pytest.raises(AIUnavailable, match="слишком много времени"):
            await client.respond("привет", user_id=1, chat_id=1)
    asyncio.run(scenario())


def test_user_backlog_rejected(monkeypatch):
    async def slow(*a, **k):
        await asyncio.sleep(0.3)
        return "нормальный ответ"

    async def scenario():
        client = _client(monkeypatch)
        monkeypatch.setattr(client, "_text_failover", slow)
        tasks = [asyncio.create_task(client.respond(f"вопрос номер {i}", user_id=1, chat_id=1)) for i in range(3)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert sum(isinstance(r, AIUnavailable) for r in results) == 1
        assert sum(isinstance(r, str) for r in results) == 2
    asyncio.run(scenario())


def test_mode_guidance_and_language():
    tech = smart_router.classify("исправь баг в python коде")
    assert "техническая задача" in smart_router.guidance(tech, "исправь баг")
    chat = smart_router.classify("hello there how are you today")
    assert "не по-русски" in smart_router.guidance(chat, "hello there how are you today")
    assert "не по-русски" not in smart_router.guidance(smart_router.classify("привет"), "привет")


def test_mode_guidance_reaches_the_model(monkeypatch):
    async def scenario():
        client = _client(monkeypatch)
        failover = AsyncMock(return_value="Вот решение с кодом и пояснением.")
        monkeypatch.setattr(client, "_text_failover", failover)
        await client.respond("исправь баг в python коде", user_id=1, chat_id=1)
        assert "техническая задача" in failover.await_args.args[0][0]["content"]
        await client.respond("привет, как дела?", user_id=1, chat_id=2)
        assert "Режим: разговор" in failover.await_args.args[0][0]["content"]
    asyncio.run(scenario())
