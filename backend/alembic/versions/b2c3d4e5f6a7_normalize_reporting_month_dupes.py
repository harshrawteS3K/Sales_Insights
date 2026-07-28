"""normalize_reporting_month_and_retire_dupes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-27

Normalize Excel-datetime reporting_month values (e.g. ``2026-07-01 00:00:00``
→ ``July 2026``) and soft-delete duplicate active reports for the same
Distributor + Reporting Month, keeping the newest.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Normalize ISO / datetime-like reporting_month → Month YYYY
    op.execute(
        """
        UPDATE reports
        SET reporting_month = TO_CHAR(reporting_month::timestamp, 'FMMonth YYYY')
        WHERE reporting_month IS NOT NULL
          AND reporting_month ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        """
    )
    # Keep denormalized sales.period in sync when it looks like a datetime
    op.execute(
        """
        UPDATE sales_records
        SET period = TO_CHAR(period::timestamp, 'FMMonth YYYY')
        WHERE period IS NOT NULL
          AND period ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
        """
    )

    # Soft-delete duplicate active reports for same distributor + month (keep newest)
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 ROW_NUMBER() OVER (
                   PARTITION BY distributor_id, reporting_month
                   ORDER BY created_at DESC, id DESC
                 ) AS rn
          FROM reports
          WHERE is_deleted = false
            AND distributor_id IS NOT NULL
            AND reporting_month IS NOT NULL
            AND TRIM(reporting_month) <> ''
        )
        UPDATE sales_records s
        SET is_deleted = true, deleted_at = NOW()
        FROM ranked r
        WHERE s.report_id = r.id
          AND r.rn > 1
          AND s.is_deleted = false
        """
    )
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 ROW_NUMBER() OVER (
                   PARTITION BY distributor_id, reporting_month
                   ORDER BY created_at DESC, id DESC
                 ) AS rn
          FROM reports
          WHERE is_deleted = false
            AND distributor_id IS NOT NULL
            AND reporting_month IS NOT NULL
            AND TRIM(reporting_month) <> ''
        )
        UPDATE reports
        SET is_deleted = true, deleted_at = NOW()
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )

    # Orphan safety: archive sales still active under deleted reports
    op.execute(
        """
        UPDATE sales_records s
        SET is_deleted = true, deleted_at = NOW()
        FROM reports r
        WHERE s.report_id = r.id
          AND r.is_deleted = true
          AND s.is_deleted = false
        """
    )


def downgrade() -> None:
    # Irreversible data normalization — no-op
    pass
