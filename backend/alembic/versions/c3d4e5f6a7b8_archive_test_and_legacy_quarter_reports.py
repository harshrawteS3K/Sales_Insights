"""archive_test_and_legacy_quarter_reports

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-27

1. Soft-delete active reports created by integration tests
   (Dist *, DateReplace *, Vis Dist *, Stock Dist *, Old Stock *).
2. Soft-delete legacy quarter-format active reports (Q1–Q4 …)
   when the same distributor already has an active Month YYYY report
   (official template uses Reporting Month, not quarters).
3. Soft-delete orphaned active sales under archived reports.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1) Archive pytest / development distributor reports ---
    op.execute(
        """
        UPDATE sales_records s
        SET is_deleted = true, deleted_at = NOW()
        FROM reports r
        JOIN distributors d ON d.id = r.distributor_id
        WHERE s.report_id = r.id
          AND s.is_deleted = false
          AND r.is_deleted = false
          AND (
            d.name ~* '^(Dist |DateReplace|Vis Dist|Stock Dist|Old Stock)'
            OR d.name ~* '(Replace|FileDup|Months|Periods|Ghost|Delete) [0-9a-f]{6,}'
          )
        """
    )
    op.execute(
        """
        UPDATE reports r
        SET is_deleted = true, deleted_at = NOW()
        FROM distributors d
        WHERE d.id = r.distributor_id
          AND r.is_deleted = false
          AND (
            d.name ~* '^(Dist |DateReplace|Vis Dist|Stock Dist|Old Stock)'
            OR d.name ~* '(Replace|FileDup|Months|Periods|Ghost|Delete) [0-9a-f]{6,}'
          )
        """
    )

    # --- 2) Archive quarter-style reports when Month YYYY also active ---
    # Official workflow: Reporting Month (e.g. July 2026) supersedes Q2 FY26
    op.execute(
        """
        WITH month_active AS (
          SELECT DISTINCT distributor_id
          FROM reports
          WHERE is_deleted = false
            AND distributor_id IS NOT NULL
            AND reporting_month ~ '^[A-Za-z]+ [0-9]{4}$'
        ),
        quarter_to_retire AS (
          SELECT r.id
          FROM reports r
          WHERE r.is_deleted = false
            AND r.distributor_id IN (SELECT distributor_id FROM month_active)
            AND r.reporting_month ~* '^Q[1-4]'
        )
        UPDATE sales_records s
        SET is_deleted = true, deleted_at = NOW()
        WHERE s.is_deleted = false
          AND s.report_id IN (SELECT id FROM quarter_to_retire)
        """
    )
    op.execute(
        """
        WITH month_active AS (
          SELECT DISTINCT distributor_id
          FROM reports
          WHERE is_deleted = false
            AND distributor_id IS NOT NULL
            AND reporting_month ~ '^[A-Za-z]+ [0-9]{4}$'
        )
        UPDATE reports r
        SET is_deleted = true, deleted_at = NOW()
        WHERE r.is_deleted = false
          AND r.distributor_id IN (SELECT distributor_id FROM month_active)
          AND r.reporting_month ~* '^Q[1-4]'
        """
    )

    # --- 3) Orphan safety ---
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
    # Soft-delete cleanup is intentional / irreversible
    pass
