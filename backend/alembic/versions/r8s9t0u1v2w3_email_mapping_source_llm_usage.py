"""Add email mapping_source + llm_usage_logs for admin LLM settings.

Revision ID: r8s9t0u1v2w3
Revises: q7r8s9t0u1v2
Create Date: 2026-09-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r8s9t0u1v2w3"
down_revision = "q7r8s9t0u1v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "email_messages" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("email_messages")}
        if "mapping_source" not in cols:
            op.add_column(
                "email_messages",
                sa.Column("mapping_source", sa.String(length=30), nullable=True),
            )

    if "llm_usage_logs" not in inspector.get_table_names():
        op.create_table(
            "llm_usage_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("model", sa.String(length=100), nullable=False),
            sa.Column("purpose", sa.String(length=80), nullable=False),
            sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("email_id", sa.Integer(), nullable=True),
            sa.Column("actor", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["email_id"], ["email_messages.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_llm_usage_logs_created_at", "llm_usage_logs", ["created_at"])
        op.create_index("ix_llm_usage_logs_purpose", "llm_usage_logs", ["purpose"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "llm_usage_logs" in inspector.get_table_names():
        op.drop_index("ix_llm_usage_logs_purpose", table_name="llm_usage_logs")
        op.drop_index("ix_llm_usage_logs_created_at", table_name="llm_usage_logs")
        op.drop_table("llm_usage_logs")
    if "email_messages" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("email_messages")}
        if "mapping_source" in cols:
            op.drop_column("email_messages", "mapping_source")
