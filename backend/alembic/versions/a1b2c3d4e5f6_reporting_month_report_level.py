"""reporting_month_report_level

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-07-26

Move Reporting Month to report level (rename reports.period → reporting_month).
Make sales_records.period nullable for new template (no per-row Period column).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename reports.period → reporting_month
    op.drop_index("uq_reports_distributor_period_active", table_name="reports")
    op.drop_index("ix_reports_period", table_name="reports")
    op.alter_column(
        "reports",
        "period",
        new_column_name="reporting_month",
        existing_type=sa.String(length=50),
        existing_nullable=True,
    )
    op.create_index("ix_reports_reporting_month", "reports", ["reporting_month"])
    op.create_index(
        "uq_reports_distributor_month_active",
        "reports",
        ["distributor_id", "reporting_month"],
        unique=True,
        postgresql_where=(
            "is_deleted = false AND distributor_id IS NOT NULL "
            "AND reporting_month IS NOT NULL AND TRIM(reporting_month) <> ''"
        ),
    )

    # Backfill sales.period from report when missing (safety), then allow NULL for new rows
    op.execute(
        """
        UPDATE sales_records s
        SET period = r.reporting_month
        FROM reports r
        WHERE s.report_id = r.id
          AND (s.period IS NULL OR TRIM(s.period) = '')
          AND r.reporting_month IS NOT NULL
          AND TRIM(r.reporting_month) <> ''
        """
    )
    op.alter_column(
        "sales_records",
        "period",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "sales_records",
        "period",
        existing_type=sa.String(length=50),
        nullable=False,
        server_default="",
    )
    op.alter_column("sales_records", "period", server_default=None)

    op.drop_index("uq_reports_distributor_month_active", table_name="reports")
    op.drop_index("ix_reports_reporting_month", table_name="reports")
    op.alter_column(
        "reports",
        "reporting_month",
        new_column_name="period",
        existing_type=sa.String(length=50),
        existing_nullable=True,
    )
    op.create_index("ix_reports_period", "reports", ["period"])
    op.create_index(
        "uq_reports_distributor_period_active",
        "reports",
        ["distributor_id", "period"],
        unique=True,
        postgresql_where=(
            "is_deleted = false AND distributor_id IS NOT NULL "
            "AND period IS NOT NULL AND TRIM(period) <> ''"
        ),
    )
