"""Kira assistant platform tables and economy columns.

Revision ID: 20260915_01
Revises: None
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from bot.sql.orm_tables import TableBase

revision = "20260915_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        existing = {c["name"] for c in inspector.get_columns("users")}
        additions = [
            ("xp", sa.Integer(), "0", False),
            ("level", sa.Integer(), "1", False),
            ("coins", sa.Integer(), "100", False),
            ("daily_streak", sa.Integer(), "0", False),
            ("last_daily_at", sa.Integer(), "0", False),
            ("birthday_day", sa.Integer(), None, True),
            ("birthday_month", sa.Integer(), None, True),
        ]
        for name, type_, default, nullable in additions:
            if name in existing:
                continue
            op.add_column(
                "users",
                sa.Column(name, type_, nullable=nullable, server_default=sa.text(default) if default is not None else None),
            )

    # New tables are created from the same metadata used by the bot. Existing
    # tables are left intact by checkfirst=True.
    TableBase.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    # Downgrade intentionally keeps user data. Destructive removal can be done
    # manually if ever needed.
    pass
