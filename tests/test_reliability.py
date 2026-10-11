import asyncio
import importlib.util
from pathlib import Path
from bot.conversation_lock import ConversationLocks
from bot.redaction import redact

ROOT = Path(__file__).resolve().parents[1]

def test_secret_redaction(monkeypatch):
    monkeypatch.setenv('HF_TOKEN', 'synthetic-secret-value')
    assert 'synthetic-secret-value' not in redact('failure: synthetic-secret-value')
    assert 'abc123' not in redact('https://example.org/?access_token=abc123')

def test_conversation_order_and_cleanup():
    async def scenario():
        locks = ConversationLocks(); events = []
        async def work(n):
            async with locks.hold((1, 2)):
                events.append(('start', n))
                await asyncio.sleep(0)
                events.append(('end', n))
        await asyncio.gather(work(1), work(2))
        assert events == [('start', 1), ('end', 1), ('start', 2), ('end', 2)]
        assert not locks._entries
    asyncio.run(scenario())

def test_cancelled_waiter_does_not_leak():
    async def scenario():
        locks = ConversationLocks()
        async def waiter():
            async with locks.hold(1): pass
        async with locks.hold(1):
            task = asyncio.create_task(waiter())
            await asyncio.sleep(0)
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        assert not locks._entries
    asyncio.run(scenario())

def test_env_merge_preserves_custom_values():
    spec = importlib.util.spec_from_file_location('merge_env', ROOT / 'tools/merge_env.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    old = '# keep\r\nTOKEN=existing\r\nCUSTOM=private\r\n'
    result = module.merge(old, 'TOKEN=replacement\nNEW=default\n')
    assert result.startswith(old)
    assert 'replacement' not in result
    assert 'NEW=default' in result
    assert module.merge(result, 'TOKEN=x\nNEW=default\n') == result


def test_plain_reply_emoji_is_within_telegram_limit():
    # Extract the helper to avoid importing unrelated optional media services.
    import ast
    from unittest.mock import AsyncMock
    from types import SimpleNamespace
    tree = ast.parse((ROOT / 'bot/handlers/suite.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_send_plain')
    scope = {'Message': object}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<helper>', 'exec'), scope)
    async def scenario():
        message = SimpleNamespace(reply=AsyncMock(), answer=AsyncMock())
        text = '🦊' * 4000
        await scope['_send_plain'](message, text)
        calls = message.reply.await_args_list + message.answer.await_args_list
        assert ''.join(c.args[0] for c in calls) == text
        assert all(len(c.args[0].encode('utf-16-le')) // 2 <= 3900 for c in calls)
        assert all(c.kwargs['parse_mode'] is None for c in calls)
    asyncio.run(scenario())
