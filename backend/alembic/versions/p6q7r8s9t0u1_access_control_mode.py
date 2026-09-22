"""Access control mode setting + system_settings table.

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "p6q7r8s9t0u1"
down_revision = "o5p6q7r8s9t0"
branch_labels = None
depends_on = None

ACCESS_MODE_KEY = "access_mode"
DEFAULT_ACCESS_MODE = "segment"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "system_settings" not in inspector.get_table_names():
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )
    conn.execute(
        text(
            "INSERT INTO system_settings (key, value, created_at, updated_at) "
            "VALUES (:k, :v, NOW(), NOW()) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"k": ACCESS_MODE_KEY, "v": DEFAULT_ACCESS_MODE},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text("DELETE FROM system_settings WHERE key = :k"), {"k": ACCESS_MODE_KEY})
    # Keep table if other keys may exist; only drop when empty
    remaining = conn.execute(text("SELECT COUNT(*) FROM system_settings")).scalar()
    if not remaining:
        op.drop_table("system_settings")
