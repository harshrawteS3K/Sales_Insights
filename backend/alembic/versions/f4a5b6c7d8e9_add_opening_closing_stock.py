"""add_opening_closing_stock_to_sales_records

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-26

Product-level inventory fields on sales_records:
- opening_stock (nullable Numeric)
- closing_stock (nullable Numeric)

Backward compatible — historical rows remain NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sales_records",
        sa.Column("opening_stock", sa.Numeric(18, 3), nullable=True),
    )
    op.add_column(
        "sales_records",
        sa.Column("closing_stock", sa.Numeric(18, 3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales_records", "closing_stock")
    op.drop_column("sales_records", "opening_stock")
