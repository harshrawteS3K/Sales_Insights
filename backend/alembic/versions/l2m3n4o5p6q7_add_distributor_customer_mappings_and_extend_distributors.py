"""add distributor customer mappings and extend distributors

Revision ID: l2m3n4o5p6q7
Revises: k1f2a3b4c5d6
Create Date: 2026-08-10

Phase-2: extend distributors with code/contact_person/cc_email;
create distributor_customer_mappings for Q2+ template isolation.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, None] = "k1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("distributors", sa.Column("code", sa.String(length=64), nullable=True))
    op.add_column(
        "distributors", sa.Column("contact_person", sa.String(length=255), nullable=True)
    )
    op.add_column("distributors", sa.Column("cc_email", sa.String(length=255), nullable=True))
    op.create_index(
        "uq_distributors_code_active",
        "distributors",
        ["code"],
        unique=True,
        postgresql_where=sa.text(
            "is_deleted = false AND code IS NOT NULL AND TRIM(code) <> ''"
        ),
    )

    op.create_table(
        "distributor_customer_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("distributor_id", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=False),
        sa.Column("source_report_id", sa.Integer(), nullable=True),
        sa.Column("first_seen_quarter", sa.String(length=50), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["distributor_id"], ["distributors.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_report_id"], ["reports.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "distributor_id",
            "customer_name",
            name="uq_distributor_customer_mappings_dist_customer",
        ),
    )
    op.create_index(
        "ix_distributor_customer_mappings_distributor_id",
        "distributor_customer_mappings",
        ["distributor_id"],
        unique=False,
    )
    op.create_index(
        "ix_distributor_customer_mappings_active",
        "distributor_customer_mappings",
        ["distributor_id"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_distributor_customer_mappings_active",
        table_name="distributor_customer_mappings",
        postgresql_where=sa.text("is_active = true"),
    )
    op.drop_index(
        "ix_distributor_customer_mappings_distributor_id",
        table_name="distributor_customer_mappings",
    )
    op.drop_table("distributor_customer_mappings")
    op.drop_index(
        "uq_distributors_code_active",
        table_name="distributors",
        postgresql_where=sa.text(
            "is_deleted = false AND code IS NOT NULL AND TRIM(code) <> ''"
        ),
    )
    op.drop_column("distributors", "cc_email")
    op.drop_column("distributors", "contact_person")
    op.drop_column("distributors", "code")
