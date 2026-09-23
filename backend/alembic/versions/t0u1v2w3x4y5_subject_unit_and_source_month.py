"""Store subject unit and sales source month for trend + KG conversion.

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t0u1v2w3x4y5"
down_revision = "s9t0u1v2w3x4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())

    if "email_messages" in tables:
        cols = {c["name"] for c in inspector.get_columns("email_messages")}
        if "parsed_unit" not in cols:
            op.add_column(
                "email_messages",
                sa.Column("parsed_unit", sa.String(length=20), nullable=True),
            )

    if "sales_records" in tables:
        cols = {c["name"] for c in inspector.get_columns("sales_records")}
        if "source_month" not in cols:
            op.add_column(
                "sales_records",
                sa.Column("source_month", sa.String(length=40), nullable=True),
            )
        if "original_unit" not in cols:
            op.add_column(
                "sales_records",
                sa.Column("original_unit", sa.String(length=20), nullable=True),
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    if "sales_records" in tables:
        cols = {c["name"] for c in inspector.get_columns("sales_records")}
        if "original_unit" in cols:
            op.drop_column("sales_records", "original_unit")
        if "source_month" in cols:
            op.drop_column("sales_records", "source_month")
    if "email_messages" in tables:
        cols = {c["name"] for c in inspector.get_columns("email_messages")}
        if "parsed_unit" in cols:
            op.drop_column("email_messages", "parsed_unit")
