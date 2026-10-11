"""Add fictional alcohol-game stats to users.

Revision ID: 20260918_02
Revises: 20260915_01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260918_02"
down_revision = "20260915_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "users" not in set(inspector.get_table_names()):
        return
    existing = {c["name"] for c in inspector.get_columns("users")}
    if "alcohol_score" not in existing:
        op.add_column("users", sa.Column("alcohol_score", sa.Float(), nullable=False, server_default=sa.text("0")))
    if "alcohol_cooldown_until" not in existing:
        op.add_column("users", sa.Column("alcohol_cooldown_until", sa.Integer(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    pass
