from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_alcohol_handler_wired():
    text=(ROOT/'bot/handlers/__init__.py').read_text()
    assert 'alcohol' in text and 'alcohol.router' in text

def test_alcohol_schema_and_manager():
    orm=(ROOT/'bot/sql/orm_tables.py').read_text()
    sql=(ROOT/'bot/sql/__init__.py').read_text()
    assert 'alcohol_score' in orm and 'alcohol_cooldown_until' in orm
    assert 'update_alcohol_stats' in sql and 'get_top_alcohol' in sql

def test_alcohol_is_explicitly_fictional():
    text=(ROOT/'bot/handlers/alcohol/commands.py').read_text()
    assert 'не показывает реальное опьянение' in text
    assert 'BAC' in text

def test_upgrade_runs_migration_without_volume_delete():
    text=(ROOT/'upgrade_1_7.sh').read_text()
    assert 'alembic upgrade head' in text
    assert 'down -v' not in text
