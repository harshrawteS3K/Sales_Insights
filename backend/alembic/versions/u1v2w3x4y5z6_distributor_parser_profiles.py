"""Saved parser strategy per distributor.

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-09-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u1v2w3x4y5z6"
down_revision = "t0u1v2w3x4y5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "distributor_parser_profiles" in tables:
        return
    op.create_table(
        "distributor_parser_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("distributor_id", sa.Integer(), nullable=False),
        sa.Column("parser_strategy", sa.String(length=80), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("last_used", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["distributor_id"],
            ["distributors.id"],
            name="fk_distributor_parser_profiles_distributor",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "distributor_id",
            name="uq_distributor_parser_profiles_distributor",
        ),
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "distributor_parser_profiles" in set(inspector.get_table_names()):
        op.drop_table("distributor_parser_profiles")
