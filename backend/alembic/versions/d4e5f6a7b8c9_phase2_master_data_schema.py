"""Phase 2 master data schema alignment.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-28

1. Add product_master.industry_type (from Industry Type Description).
2. Relax legacy NOT NULL columns so Phase 2 can store slim masters
   (customer_name only; industry_type + product_code).
3. Replace global unique constraints with partial unique indexes on
   active rows so soft-delete replace does not collide with history.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_master",
        sa.Column("industry_type", sa.String(length=255), nullable=True),
    )
    op.execute(
        """
        UPDATE product_master
        SET industry_type = COALESCE(NULLIF(TRIM(segment), ''), 'UNASSIGNED')
        WHERE industry_type IS NULL
        """
    )
    op.alter_column(
        "product_master",
        "industry_type",
        existing_type=sa.String(length=255),
        nullable=False,
        server_default="UNASSIGNED",
    )
    op.create_index("ix_product_master_industry_type", "product_master", ["industry_type"])

    op.alter_column("product_master", "product_name", existing_type=sa.String(length=255), nullable=True)
    op.alter_column("product_master", "segment", existing_type=sa.String(length=150), nullable=True)

    # Deduplicate active product codes before partial unique index
    op.execute(
        """
        UPDATE product_master p
        SET is_deleted = true, deleted_at = NOW(), is_active = false
        WHERE p.is_deleted = false
          AND p.id NOT IN (
            SELECT MIN(id) FROM product_master WHERE is_deleted = false GROUP BY product_code
          )
        """
    )

    op.drop_constraint("uq_product_master_code", "product_master", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_product_master_code_active
        ON product_master (product_code)
        WHERE is_deleted = false
        """
    )

    op.alter_column("customer_master", "customer_code", existing_type=sa.String(length=100), nullable=True)
    op.alter_column("customer_master", "segment", existing_type=sa.String(length=150), nullable=True)

    op.execute(
        """
        UPDATE customer_master c
        SET is_deleted = true, deleted_at = NOW(), is_active = false
        WHERE c.is_deleted = false
          AND c.id NOT IN (
            SELECT MIN(id) FROM customer_master WHERE is_deleted = false GROUP BY customer_name
          )
        """
    )

    op.drop_constraint("uq_customer_master_code", "customer_master", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_customer_master_name_active
        ON customer_master (customer_name)
        WHERE is_deleted = false
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_customer_master_name_active")
    op.create_unique_constraint("uq_customer_master_code", "customer_master", ["customer_code"])
    op.alter_column("customer_master", "segment", existing_type=sa.String(length=150), nullable=False)
    op.alter_column("customer_master", "customer_code", existing_type=sa.String(length=100), nullable=False)

    op.execute("DROP INDEX IF EXISTS uq_product_master_code_active")
    op.create_unique_constraint("uq_product_master_code", "product_master", ["product_code"])
    op.alter_column("product_master", "segment", existing_type=sa.String(length=150), nullable=False)
    op.alter_column("product_master", "product_name", existing_type=sa.String(length=255), nullable=False)

    op.drop_index("ix_product_master_industry_type", table_name="product_master")
    op.drop_column("product_master", "industry_type")
