"""Parser profile fingerprint, version, and layout.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-09-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2w3x4y5z6a7"
down_revision = "u1v2w3x4y5z6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "distributor_parser_profiles" not in set(inspector.get_table_names()):
        return
    columns = {col["name"] for col in inspector.get_columns("distributor_parser_profiles")}
    if "parser_name" not in columns:
        op.add_column(
            "distributor_parser_profiles",
            sa.Column("parser_name", sa.String(length=80), nullable=True),
        )
    if "parser_version" not in columns:
        op.add_column(
            "distributor_parser_profiles",
            sa.Column("parser_version", sa.String(length=20), nullable=True),
        )
    if "layout_type" not in columns:
        op.add_column(
            "distributor_parser_profiles",
            sa.Column("layout_type", sa.String(length=80), nullable=True),
        )
    if "fingerprint_hash" not in columns:
        op.add_column(
            "distributor_parser_profiles",
            sa.Column("fingerprint_hash", sa.String(length=16), nullable=True),
        )
    if "successful_runs" not in columns:
        op.add_column(
            "distributor_parser_profiles",
            sa.Column("successful_runs", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "distributor_parser_profiles" not in set(inspector.get_table_names()):
        return
    columns = {col["name"] for col in inspector.get_columns("distributor_parser_profiles")}
    for name in (
        "successful_runs",
        "fingerprint_hash",
        "layout_type",
        "parser_version",
        "parser_name",
    ):
        if name in columns:
            op.drop_column("distributor_parser_profiles", name)
