"""Enterprise audit trail columns: role, module, status + filter indexes.

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-08-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i9d0e1f2a3b4"
down_revision = "h8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_trail",
        sa.Column("user_role", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "audit_trail",
        sa.Column("module", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "audit_trail",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="Success",
        ),
    )
    op.create_index("ix_audit_trail_user_role", "audit_trail", ["user_role"])
    op.create_index("ix_audit_trail_module", "audit_trail", ["module"])
    op.create_index("ix_audit_trail_status", "audit_trail", ["status"])
    op.create_index(
        "ix_audit_trail_module_created",
        "audit_trail",
        ["module", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_trail_module_created", table_name="audit_trail")
    op.drop_index("ix_audit_trail_status", table_name="audit_trail")
    op.drop_index("ix_audit_trail_module", table_name="audit_trail")
    op.drop_index("ix_audit_trail_user_role", table_name="audit_trail")
    op.drop_column("audit_trail", "status")
    op.drop_column("audit_trail", "module")
    op.drop_column("audit_trail", "user_role")
