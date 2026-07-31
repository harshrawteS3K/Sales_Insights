"""Add outlook_web_link to email_messages for View navigation.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_messages",
        sa.Column("outlook_web_link", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_messages", "outlook_web_link")
