"""Consolidate distributor identity on Company; one ACTIVE report per company+month.

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Soft-delete duplicate ACTIVE reports for the same company + month
    #    BEFORE merging distributor rows (avoids unique constraint collisions).
    conn.execute(
        sa.text(
            """
            WITH active AS (
                SELECT
                    r.id,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            LOWER(TRIM(COALESCE(d.company, ''))),
                            LOWER(TRIM(COALESCE(r.reporting_month, '')))
                        ORDER BY r.id DESC
                    ) AS rn
                FROM reports r
                JOIN distributors d ON d.id = r.distributor_id
                WHERE r.is_deleted = false
                  AND r.reporting_month IS NOT NULL
                  AND TRIM(r.reporting_month) <> ''
                  AND d.company IS NOT NULL
                  AND TRIM(d.company) <> ''
            ),
            losers AS (
                SELECT id FROM active WHERE rn > 1
            )
            UPDATE sales_records AS sr
            SET is_deleted = true,
                deleted_at = NOW() AT TIME ZONE 'utc'
            FROM losers l
            WHERE sr.report_id = l.id
              AND sr.is_deleted = false
            """
        )
    )
    conn.execute(
        sa.text(
            """
            WITH active AS (
                SELECT
                    r.id,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            LOWER(TRIM(COALESCE(d.company, ''))),
                            LOWER(TRIM(COALESCE(r.reporting_month, '')))
                        ORDER BY r.id DESC
                    ) AS rn
                FROM reports r
                JOIN distributors d ON d.id = r.distributor_id
                WHERE r.is_deleted = false
                  AND r.reporting_month IS NOT NULL
                  AND TRIM(r.reporting_month) <> ''
                  AND d.company IS NOT NULL
                  AND TRIM(d.company) <> ''
            ),
            losers AS (
                SELECT id FROM active WHERE rn > 1
            )
            UPDATE reports AS r
            SET is_deleted = true,
                deleted_at = NOW() AT TIME ZONE 'utc'
            FROM losers l
            WHERE r.id = l.id
              AND r.is_deleted = false
            """
        )
    )

    # 2) Merge duplicate distributor rows sharing the same company key.
    #    Keep lowest id; reassign reports + sales; soft-delete others.
    conn.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    LOWER(TRIM(company)) AS company_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(TRIM(company))
                        ORDER BY id ASC
                    ) AS rn
                FROM distributors
                WHERE is_deleted = false
                  AND company IS NOT NULL
                  AND TRIM(company) <> ''
            ),
            dups AS (
                SELECT r.id AS dup_id, c.id AS keep_id
                FROM ranked r
                JOIN ranked c
                  ON c.company_key = r.company_key
                 AND c.rn = 1
                WHERE r.rn > 1
            )
            UPDATE reports AS rep
            SET distributor_id = d.keep_id
            FROM dups d
            WHERE rep.distributor_id = d.dup_id
            """
        )
    )
    conn.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    LOWER(TRIM(company)) AS company_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(TRIM(company))
                        ORDER BY id ASC
                    ) AS rn
                FROM distributors
                WHERE is_deleted = false
                  AND company IS NOT NULL
                  AND TRIM(company) <> ''
            ),
            dups AS (
                SELECT r.id AS dup_id, c.id AS keep_id
                FROM ranked r
                JOIN ranked c
                  ON c.company_key = r.company_key
                 AND c.rn = 1
                WHERE r.rn > 1
            )
            UPDATE sales_records AS sr
            SET distributor_id = d.keep_id
            FROM dups d
            WHERE sr.distributor_id = d.dup_id
            """
        )
    )
    conn.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    LOWER(TRIM(company)) AS company_key,
                    ROW_NUMBER() OVER (
                        PARTITION BY LOWER(TRIM(company))
                        ORDER BY id ASC
                    ) AS rn
                FROM distributors
                WHERE is_deleted = false
                  AND company IS NOT NULL
                  AND TRIM(company) <> ''
            ),
            dups AS (
                SELECT r.id AS dup_id
                FROM ranked r
                WHERE r.rn > 1
            )
            UPDATE distributors AS dist
            SET is_deleted = true,
                deleted_at = NOW() AT TIME ZONE 'utc'
            FROM dups d
            WHERE dist.id = d.dup_id
              AND dist.is_deleted = false
            """
        )
    )

    # 3) Unique active company index
    op.create_index(
        "uq_distributors_company_active",
        "distributors",
        [sa.text("lower(trim(company))")],
        unique=True,
        postgresql_where=sa.text(
            "is_deleted = false AND company IS NOT NULL AND TRIM(company) <> ''"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_distributors_company_active", table_name="distributors")
