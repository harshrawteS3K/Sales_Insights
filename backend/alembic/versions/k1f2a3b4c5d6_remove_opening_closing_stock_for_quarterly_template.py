"""remove_opening_closing_stock_for_quarterly_template

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-08-09

Quarterly distributor template no longer collects Opening/Closing Stock.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k1f2a3b4c5d6"
down_revision: Union[str, None] = "j0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("sales_records", "closing_stock")
    op.drop_column("sales_records", "opening_stock")


def downgrade() -> None:
    op.add_column(
        "sales_records",
        sa.Column("opening_stock", sa.Numeric(precision=18, scale=3), nullable=True),
    )
    op.add_column(
        "sales_records",
        sa.Column("closing_stock", sa.Numeric(precision=18, scale=3), nullable=True),
    )
