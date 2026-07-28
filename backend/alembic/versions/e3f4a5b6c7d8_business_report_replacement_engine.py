"""business_report_replacement_engine

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-26

Phase 1 final:
- reports.confidence_score first-class column
- unique active (distributor_id, period) business identity
- soft-delete-aware unique graph_message_id / graph_attachment_id
- retire ghost reports (null distributor/period or zero sales)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("confidence_score", sa.Integer(), nullable=True))

    # Backfill confidence from JSON extraction metadata
    op.execute(
        """
        UPDATE reports
        SET confidence_score = CAST(categories->'extraction'->>'quality_score' AS INTEGER)
        WHERE categories IS NOT NULL
          AND categories->'extraction'->>'quality_score' IS NOT NULL
          AND confidence_score IS NULL
        """
    )

    # Soft-delete ghost / invalid active reports before unique business key
    op.execute(
        """
        UPDATE sales_records s
        SET is_deleted = true, deleted_at = NOW()
        FROM reports r
        WHERE s.report_id = r.id
          AND s.is_deleted = false
          AND r.is_deleted = false
          AND (
            r.distributor_id IS NULL
            OR r.period IS NULL
            OR TRIM(r.period) = ''
            OR NOT EXISTS (
              SELECT 1 FROM sales_records sx
              WHERE sx.report_id = r.id AND sx.is_deleted = false
            )
          )
        """
    )
    op.execute(
        """
        UPDATE reports
        SET is_deleted = true, deleted_at = NOW()
        WHERE is_deleted = false
          AND (
            distributor_id IS NULL
            OR period IS NULL
            OR TRIM(period) = ''
            OR NOT EXISTS (
              SELECT 1 FROM sales_records s
              WHERE s.report_id = reports.id AND s.is_deleted = false
            )
          )
        """
    )

    # If multiple active reports share distributor+period, keep newest, retire others
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 ROW_NUMBER() OVER (
                   PARTITION BY distributor_id, period
                   ORDER BY created_at DESC, id DESC
                 ) AS rn
          FROM reports
          WHERE is_deleted = false
            AND distributor_id IS NOT NULL
            AND period IS NOT NULL
            AND TRIM(period) <> ''
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
                   PARTITION BY distributor_id, period
                   ORDER BY created_at DESC, id DESC
                 ) AS rn
          FROM reports
          WHERE is_deleted = false
            AND distributor_id IS NOT NULL
            AND period IS NOT NULL
            AND TRIM(period) <> ''
        )
        UPDATE reports
        SET is_deleted = true, deleted_at = NOW()
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )

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

    # Soft-delete-aware uniqueness for Graph IDs
    op.drop_constraint("uq_email_messages_graph_id", "email_messages", type_="unique")
    op.create_index(
        "uq_email_messages_graph_id_active",
        "email_messages",
        ["graph_message_id"],
        unique=True,
        postgresql_where="is_deleted = false",
    )

    op.drop_constraint("uq_email_attachments_graph_id", "email_attachments", type_="unique")
    op.create_index(
        "uq_email_attachments_graph_id_active",
        "email_attachments",
        ["graph_attachment_id"],
        unique=True,
        postgresql_where="is_deleted = false",
    )


def downgrade() -> None:
    op.drop_index("uq_email_attachments_graph_id_active", table_name="email_attachments")
    op.create_unique_constraint(
        "uq_email_attachments_graph_id", "email_attachments", ["graph_attachment_id"]
    )

    op.drop_index("uq_email_messages_graph_id_active", table_name="email_messages")
    op.create_unique_constraint(
        "uq_email_messages_graph_id", "email_messages", ["graph_message_id"]
    )

    op.drop_index("uq_reports_distributor_period_active", table_name="reports")
    op.drop_column("reports", "confidence_score")
