"""Part A: email internet_message_id unique + integrity helpers.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-29

Partial unique index on internet_message_id for active emails (dedupe).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Soft-delete duplicate internet_message_id rows keeping the lowest id
    op.execute(
        """
        UPDATE email_messages e
        SET is_deleted = true, deleted_at = NOW()
        WHERE e.is_deleted = false
          AND e.internet_message_id IS NOT NULL
          AND e.id NOT IN (
            SELECT MIN(id)
            FROM email_messages
            WHERE is_deleted = false
              AND internet_message_id IS NOT NULL
            GROUP BY internet_message_id
          )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_email_messages_internet_id_active
        ON email_messages (internet_message_id)
        WHERE is_deleted = false AND internet_message_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_email_messages_internet_id_active")
