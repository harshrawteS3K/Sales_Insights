"""Persona segment RBAC, email subject fields, sales location.

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-09-16
"""

from __future__ import annotations

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "m3n4o5p6q7r8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


PERSONAS = [
    ("salesPaper", "Sales Paper Head", "Paper", "Sales@123"),
    ("salesCarpet", "Sales Carpet Head", "Carpet", "Sales@123"),
    ("salesConstruction", "Sales Construction Head", "Construction", "Sales@123"),
    ("salesRubber", "Sales Rubber Head", "Rubber", "Sales@123"),
    ("salesGloves", "Sales Gloves Head", "Gloves", "Sales@123"),
]


def upgrade() -> None:
    op.create_table(
        "user_segments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("segment", sa.String(length=150), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "segment", name="uq_user_segments_user_segment"),
    )
    op.create_index("ix_user_segments_user_id", "user_segments", ["user_id"])
    op.create_index("ix_user_segments_segment", "user_segments", ["segment"])

    op.add_column("email_messages", sa.Column("parsed_distributor", sa.String(length=255), nullable=True))
    op.add_column("email_messages", sa.Column("parsed_location", sa.String(length=150), nullable=True))
    op.add_column("email_messages", sa.Column("parsed_segment", sa.String(length=150), nullable=True))
    op.add_column("email_messages", sa.Column("detected_quarter", sa.String(length=50), nullable=True))
    op.add_column(
        "email_messages",
        sa.Column("subject_valid", sa.Boolean(), server_default="false", nullable=False),
    )

    op.add_column(
        "sales_records",
        sa.Column("location", sa.String(length=150), server_default="", nullable=False),
    )

    conn = op.get_bind()

    # Ensure admin password admin123
    conn.execute(
        text(
            "UPDATE users SET password_hash = :ph, role = 'admin', is_active = true "
            "WHERE username = 'admin' AND is_deleted = false"
        ),
        {"ph": _hash("admin123")},
    )

    for username, full_name, segment, password in PERSONAS:
        row = conn.execute(
            text("SELECT id FROM users WHERE username = :u AND is_deleted = false"),
            {"u": username},
        ).fetchone()
        if row:
            uid = row[0]
            conn.execute(
                text(
                    "UPDATE users SET password_hash = :ph, full_name = :fn, role = 'user', "
                    "is_active = true WHERE id = :id"
                ),
                {"ph": _hash(password), "fn": full_name, "id": uid},
            )
        else:
            uid = conn.execute(
                text(
                    "INSERT INTO users (username, email, full_name, title, password_hash, role, "
                    "is_active, is_deleted, created_at, updated_at) "
                    "VALUES (:u, :e, :fn, :t, :ph, 'user', true, false, NOW(), NOW()) RETURNING id"
                ),
                {
                    "u": username,
                    "e": f"{username}@apcotex.local",
                    "fn": full_name,
                    "t": f"{segment} Segment Head",
                    "ph": _hash(password),
                },
            ).scalar()
        conn.execute(
            text("DELETE FROM user_segments WHERE user_id = :uid"),
            {"uid": uid},
        )
        conn.execute(
            text("INSERT INTO user_segments (user_id, segment, created_at, updated_at) VALUES (:uid, :seg, NOW(), NOW())"),
            {"uid": uid, "seg": segment},
        )


def downgrade() -> None:
    op.drop_column("sales_records", "location")
    op.drop_column("email_messages", "subject_valid")
    op.drop_column("email_messages", "detected_quarter")
    op.drop_column("email_messages", "parsed_segment")
    op.drop_column("email_messages", "parsed_location")
    op.drop_column("email_messages", "parsed_distributor")
    op.drop_table("user_segments")
