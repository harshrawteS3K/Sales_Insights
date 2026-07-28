"""fix_reports_content_hash_soft_delete

Revision ID: c1a2b3d4e5f6
Revises: bb9ee5c97806
Create Date: 2026-07-17

Replace global UNIQUE(content_hash) with a partial unique index so soft-deleted
reports do not block re-upload of the same file.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c1a2b3d4e5f6"
down_revision: Union[str, None] = "bb9ee5c97806"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_reports_content_hash", "reports", type_="unique")
    op.create_index(
        "uq_reports_content_hash_active",
        "reports",
        ["content_hash"],
        unique=True,
        postgresql_where="is_deleted = false AND content_hash IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("uq_reports_content_hash_active", table_name="reports")
    op.create_unique_constraint("uq_reports_content_hash", "reports", ["content_hash"])
