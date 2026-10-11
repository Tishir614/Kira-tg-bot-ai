import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from bot.ai_client import KiraAI, AssistantMemoryManager

def test_stateless_response_avoids_memory(monkeypatch):
    async def scenario():
        client = KiraAI()
        monkeypatch.setattr(client, '_require_ai', lambda: None)
        monkeypatch.setattr(client, '_text_failover', AsyncMock(return_value='hello'))
        context, add = AsyncMock(), AsyncMock()
        monkeypatch.setattr(AssistantMemoryManager, 'context', context)
        monkeypatch.setattr(AssistantMemoryManager, 'add', add)
        result = await client.respond('hello', user_id=0, chat_id=1, remember=False)
        assert result == 'hello'
        context.assert_not_awaited(); add.assert_not_awaited()
    asyncio.run(scenario())

def test_proactive_voice_uses_valid_ai_signature(monkeypatch):
    from bot.runtime import ProactiveVoiceRuntime
    from bot.ai_client import ai
    async def scenario():
        monkeypatch.setattr(type(ai), 'enabled', property(lambda self: True))
        respond = AsyncMock(spec=ai.respond, return_value='Привет <друг>')
        monkeypatch.setattr(ai, 'respond', respond)
        monkeypatch.setattr(ai, 'speech', AsyncMock(return_value=b'audio'))
        bot = SimpleNamespace(send_voice=AsyncMock())
        await ProactiveVoiceRuntime()._send(bot, 123)
        assert respond.await_args.kwargs == {'user_id': 0, 'chat_id': 123, 'remember': False}
        assert '&lt;друг&gt;' in bot.send_voice.await_args.kwargs['caption']
    asyncio.run(scenario())

def test_ai_sanitizes_hidden_reasoning_and_duplicate_paragraphs(monkeypatch):
    client = KiraAI()
    raw = "<think>private chain</think>Привет!\n\nПолезный ответ.\n\nПолезный ответ."
    cleaned = client._sanitize_model_output(raw)
    assert "private chain" not in cleaned
    assert "<think>" not in cleaned
    assert cleaned.count("Полезный ответ.") == 1


def test_ai_history_drops_roleplay_from_normal_chat(monkeypatch):
    client = KiraAI()
    rows = [
        SimpleNamespace(role="user", content="Привет"),
        SimpleNamespace(role="assistant", content="Привет!"),
        SimpleNamespace(role="user", content="*обнял тебя*"),
        SimpleNamespace(role="assistant", content="*обняла в ответ*"),
        SimpleNamespace(role="user", content="Как работает Linux?"),
        SimpleNamespace(role="assistant", content="Linux — семейство ОС."),
    ]
    messages = client._openai_messages(rows, "А что такое Arch?", "SYS")
    joined = "\n".join(str(x.get("content", "")) for x in messages)
    assert "*обнял тебя*" not in joined
    assert "*обняла в ответ*" not in joined
    assert "Как работает Linux?" in joined
    assert messages[-1]["content"] == "А что такое Arch?"


def test_ai_quality_detector_catches_repetition_loop(monkeypatch):
    client = KiraAI()
    bad = "Это повтор. " * 40
    assert client._quality_issue(bad) is not None
    assert client._quality_issue("Короткий связный ответ по теме.") is None
