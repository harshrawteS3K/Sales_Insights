"""Composite indexes for visualization filters.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-09-27

Sales rows store the financial year and quarter together in ``period``
(for example ``FY 2025-26 • Q1``). Product is stored in ``product``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_sales_records_distributor_period_active", ["distributor_id", "period", "is_deleted"]),
    ("ix_sales_records_segment_period", ["segment", "period"]),
    ("ix_sales_records_customer_period", ["customer_name", "period"]),
    ("ix_sales_records_product_period", ["product", "period"]),
)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "sales_records" not in set(inspector.get_table_names()):
        return
    existing = {item["name"] for item in inspector.get_indexes("sales_records")}
    for name, columns in _INDEXES:
        if name not in existing:
            op.create_index(name, "sales_records", columns)


def downgrade() -> None:
    for name, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name="sales_records")
