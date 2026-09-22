"""Add active + retain_history to user_segments for soft untick.

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "q7r8s9t0u1v2"
down_revision = "p6q7r8s9t0u1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_segments" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_segments")}
    if "active" not in cols:
        op.add_column(
            "user_segments",
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
    if "retain_history" not in cols:
        op.add_column(
            "user_segments",
            sa.Column(
                "retain_history",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    # Existing rows are active assignments
    conn.execute(text("UPDATE user_segments SET active = true WHERE active IS NULL"))
    conn.execute(
        text("UPDATE user_segments SET retain_history = false WHERE retain_history IS NULL")
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "user_segments" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_segments")}
    if "retain_history" in cols:
        op.drop_column("user_segments", "retain_history")
    if "active" in cols:
        op.drop_column("user_segments", "active")
