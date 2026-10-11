from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_new_community_tables_are_shipped():
    source = (ROOT / "bot/sql/orm_tables.py").read_text(encoding="utf-8")
    for name in ("GroupStaff", "CommunityMarriage", "MarriageProposal", "MatureRPProposal"):
        assert f"class {name}(TableBase):" in source


def test_staff_permissions_and_commands_are_present():
    systems = (ROOT / "bot/community_systems.py").read_text(encoding="utf-8")
    handlers = (ROOT / "bot/handlers/community_life.py").read_text(encoding="utf-8")
    assert '"helper": {"warn", "reports_view"}' in systems
    assert '"moderator"' in systems and '"admin"' in systems
    for command in ("staff", "role", "unrole", "marry", "spouse", "divorce", "marriages"):
        assert f'Command("{command}")' in handlers


def test_existing_moderation_uses_role_permissions():
    source = (ROOT / "bot/handlers/community.py").read_text(encoding="utf-8")
    assert '_require_permission(message, "warn"' in source
    assert '_require_permission(message, "mute"' in source
    assert '_require_permission(message, "kick"' in source
    assert '_require_permission(message, "ban"' in source
    assert '_require_permission(message, "reports_manage"' in source


def test_mature_pair_actions_are_consent_gated_and_non_graphic():
    systems = (ROOT / "bot/community_systems.py").read_text(encoding="utf-8").lower()
    handlers = (ROOT / "bot/handlers/community_life.py").read_text(encoding="utf-8").lower()
    assert '"секс"' in systems
    assert 'maturerpproposalmanager' in handlers
    assert 'is_adult_confirmed' in handlers
    assert 'mature_mode' in handlers
    assert 'согласен(на)' in handlers
    assert 'выебал' not in systems
    assert 'выебал' not in handlers


def test_router_and_help_catalog_include_new_features():
    routers = (ROOT / "bot/handlers/__init__.py").read_text(encoding="utf-8")
    help_ui = (ROOT / "bot/help_ui.py").read_text(encoding="utf-8")
    bot = (ROOT / "bot/bot.py").read_text(encoding="utf-8")
    assert "community_life.router" in routers
    # Since 0.7 the Telegram slash menu is intentionally compact; /help is the full catalog.
    assert "telegram_menu_commands()" in bot
    assert '("/staff"' in help_ui
    assert '("/marry"' in help_ui
    assert '("/rp18_actions"' in help_ui
