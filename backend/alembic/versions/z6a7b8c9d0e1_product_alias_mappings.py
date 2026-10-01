"""Product alias mappings for Super Admin normalization.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-10-01

Stores distributor product name → normalized product name. Creates the table
only; no mappings are inserted and ``sales_records`` is not touched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None

_TABLE = "product_alias_mappings"


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE in set(sa.inspect(conn).get_table_names()):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "distributor_id",
            sa.Integer(),
            sa.ForeignKey("distributors.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("original_product_name", sa.String(255), nullable=False),
        sa.Column("normalized_product_name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_product_alias_mappings_dist_original_active",
        _TABLE,
        ["distributor_id", sa.text("lower(original_product_name)")],
        unique=True,
        postgresql_where=sa.text("is_active = true AND distributor_id IS NOT NULL"),
    )
    op.create_index(
        "uq_product_alias_mappings_global_original_active",
        _TABLE,
        [sa.text("lower(original_product_name)")],
        unique=True,
        postgresql_where=sa.text("is_active = true AND distributor_id IS NULL"),
    )
    op.create_index("ix_product_alias_mappings_distributor_id", _TABLE, ["distributor_id"])
    op.create_index("ix_product_alias_mappings_normalized", _TABLE, ["normalized_product_name"])
    op.create_index("ix_product_alias_mappings_created_at", _TABLE, ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_product_alias_mappings_created_at", table_name=_TABLE)
    op.drop_index("ix_product_alias_mappings_normalized", table_name=_TABLE)
    op.drop_index("ix_product_alias_mappings_distributor_id", table_name=_TABLE)
    op.drop_index("uq_product_alias_mappings_global_original_active", table_name=_TABLE)
    op.drop_index("uq_product_alias_mappings_dist_original_active", table_name=_TABLE)
    op.drop_table(_TABLE)
