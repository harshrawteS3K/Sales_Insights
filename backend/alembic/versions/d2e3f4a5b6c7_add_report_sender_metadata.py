"""add_report_sender_metadata

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-26

Denormalize Outlook sender metadata onto reports for permanent traceability
even after email processing history is soft-deleted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1a2b3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("sender_name", sa.String(length=255), nullable=True))
    op.add_column("reports", sa.Column("sender_email", sa.String(length=255), nullable=True))
    op.add_column(
        "reports",
        sa.Column("email_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("reports", sa.Column("graph_message_id", sa.String(length=512), nullable=True))
    op.add_column(
        "reports", sa.Column("internet_message_id", sa.String(length=512), nullable=True)
    )
    op.add_column("reports", sa.Column("mailbox", sa.String(length=255), nullable=True))

    # Backfill from linked email_messages where available
    op.execute(
        """
        UPDATE reports r
        SET
            sender_name = e.sender_name,
            sender_email = e.sender_email,
            email_received_at = e.received_at,
            graph_message_id = e.graph_message_id,
            internet_message_id = e.internet_message_id,
            mailbox = e.mailbox
        FROM email_messages e
        WHERE r.email_message_id = e.id
          AND r.sender_email IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("reports", "mailbox")
    op.drop_column("reports", "internet_message_id")
    op.drop_column("reports", "graph_message_id")
    op.drop_column("reports", "email_received_at")
    op.drop_column("reports", "sender_email")
    op.drop_column("reports", "sender_name")
