"""Add users.outlook_sync_permission for Sync Outlook RBAC.

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s9t0u1v2w3x4"
down_revision = "r8s9t0u1v2w3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "users" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("users")}
    if "outlook_sync_permission" not in cols:
        op.add_column(
            "users",
            sa.Column(
                "outlook_sync_permission",
                sa.String(length=20),
                nullable=False,
                server_default="own",
            ),
        )

    op.execute(
        sa.text(
            "UPDATE users SET outlook_sync_permission = 'all' "
            "WHERE role IN ('admin', 'super_admin')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE users SET outlook_sync_permission = 'own' "
            "WHERE role = 'user' AND (outlook_sync_permission IS NULL OR outlook_sync_permission = '')"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "users" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "outlook_sync_permission" in cols:
        op.drop_column("users", "outlook_sync_permission")
