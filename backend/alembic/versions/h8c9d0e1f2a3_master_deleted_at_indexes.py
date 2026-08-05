"""Add deleted_at indexes for master history purge performance.

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op

revision = "h8c9d0e1f2a3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_customer_master_deleted_at",
        "customer_master",
        ["is_deleted", "deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_product_master_deleted_at",
        "product_master",
        ["is_deleted", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_product_master_deleted_at", table_name="product_master")
    op.drop_index("ix_customer_master_deleted_at", table_name="customer_master")
