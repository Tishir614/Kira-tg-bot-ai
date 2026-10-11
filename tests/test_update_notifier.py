import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import bot.update_notifier as notifier


def test_build_update_report_contains_owner_version_creator(monkeypatch, tmp_path):
    release = tmp_path / 'RELEASE_9.9.9.md'
    release.write_text('# KiraBot 9.9.9\n\n- Первый пункт\n- Второй пункт\n', encoding='utf-8')
    pyproject = tmp_path / 'pyproject.toml'
    pyproject.write_text('[project]\nversion="9.9.9"\nauthors=[{name="Tishir code"}]\n', encoding='utf-8')
    monkeypatch.setattr(notifier, 'BASE_DIR', tmp_path)
    monkeypatch.setattr(notifier, 'PYPROJECT_FILE', pyproject)
    monkeypatch.setattr(notifier, 'CHANGELOG_FILE', tmp_path / 'CHANGELOG.md')

    messages = notifier.build_owner_update_messages(
        previous_version='9.9.8', current_version='9.9.9', commit_hash='archive'
    )
    text = '\n'.join(messages)
    assert 'KIRA ОБНОВЛЕНА' in text
    assert 'Создатель: Tishir code' in text
    assert '9.9.8  ➜  9.9.9' in text
    assert 'Первый пункт' in text
    assert all(len(message) <= notifier.TELEGRAM_TEXT_LIMIT for message in messages)


def test_owner_notification_retries_and_marks_delivered(monkeypatch, tmp_path):
    state_file = tmp_path / '.owner_update.json'
    monkeypatch.setattr(notifier.OwnerUpdateNotifier, 'STATE_FILE', state_file)
    monkeypatch.setattr(notifier, 'settings', SimpleNamespace(owner_id=12345))
    monkeypatch.setattr(
        notifier,
        'build_owner_update_messages',
        lambda **kwargs: ['🦊✨ KIRA ОБНОВЛЕНА\n📦 1.2.2 ➜ 1.2.3'],
    )

    broken_bot = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError('offline')))
    monkeypatch.setattr(notifier, '_get_bot', lambda: broken_bot)
    delivered = asyncio.run(
        notifier.OwnerUpdateNotifier.check(
            current_version='1.2.3',
            previous_version='1.2.2',
            commit_hash='archive',
            update_detected=True,
        )
    )
    assert delivered is False
    pending = json.loads(state_file.read_text(encoding='utf-8'))['pending']
    assert pending['from'] == '1.2.2'
    assert pending['to'] == '1.2.3'

    good_bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(notifier, '_get_bot', lambda: good_bot)
    delivered = asyncio.run(
        notifier.OwnerUpdateNotifier.check(
            current_version='1.2.3',
            previous_version='1.2.3',
            commit_hash='archive',
            update_detected=False,
        )
    )
    assert delivered is True
    final = json.loads(state_file.read_text(encoding='utf-8'))
    assert final['last_notified_version'] == '1.2.3'
    assert final['pending'] is None
    good_bot.send_message.assert_awaited_once()


def test_initial_install_is_only_baselined(monkeypatch, tmp_path):
    state_file = tmp_path / '.owner_update.json'
    monkeypatch.setattr(notifier.OwnerUpdateNotifier, 'STATE_FILE', state_file)
    notifier.OwnerUpdateNotifier.mark_initial_install('2.0.0', 'archive')
    state = json.loads(state_file.read_text(encoding='utf-8'))
    assert state['last_notified_version'] == '2.0.0'
    assert state['last_notified_hash'] == 'archive'
    assert state['pending'] is None
