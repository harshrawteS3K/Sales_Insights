"""Segment-wise RBAC and user_segments table migration.

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-09-17
"""

from __future__ import annotations

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "o5p6q7r8s9t0"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


EMPLOYEE_USERS = [
    ("admin", "debrabata@apcotex.com", "Mr. Debrabata", "Admin", "admin123", "admin", ["Paper", "Carpet", "Construction", "Rubber", "Gloves"]),
    ("anup", "anup@apcotex.com", "Mr. Anup Pandey", "Sales Owner", "Sales@123", "user", ["Construction"]),
    ("sachin", "sachin@apcotex.com", "Mr. Sachin Kasar", "Sales Owner", "Sales@123", "user", ["Rubber"]),
    ("jitendra", "jitendra@apcotex.com", "Mr. Jitendra", "Sales Owner", "Sales@123", "user", ["Paper"]),
]

ALL_SEGMENTS = ["Paper", "Carpet", "Construction", "Rubber", "Gloves"]


def upgrade() -> None:
    conn = op.get_bind()

    # Ensure user_segments table has assigned_by column if table exists, or create table
    has_table = conn.execute(
        text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'user_segments')")
    ).scalar()

    if not has_table:
        op.create_table(
            "user_segments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("segment", sa.String(length=150), nullable=False),
            sa.Column("assigned_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "segment", name="uq_user_segments_user_segment"),
        )
        op.create_index("ix_user_segments_user_id", "user_segments", ["user_id"])
        op.create_index("ix_user_segments_segment", "user_segments", ["segment"])
    else:
        has_col = conn.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'user_segments' AND column_name = 'assigned_by')")
        ).scalar()
        if not has_col:
            op.add_column("user_segments", sa.Column("assigned_by", sa.Integer(), nullable=True))
            op.create_foreign_key(
                "fk_user_segments_assigned_by_users",
                "user_segments",
                "users",
                ["assigned_by"],
                ["id"],
                ondelete="SET NULL",
            )

    # Seed/update employee users and assign initial segments
    for username, email, full_name, title, password, role, segments in EMPLOYEE_USERS:
        row = conn.execute(
            text("SELECT id FROM users WHERE username = :u AND is_deleted = false"),
            {"u": username},
        ).fetchone()
        if row:
            uid = row[0]
            conn.execute(
                text(
                    "UPDATE users SET email = :e, full_name = :fn, title = :t, "
                    "password_hash = :ph, role = :role, is_active = true WHERE id = :id"
                ),
                {"e": email, "fn": full_name, "t": title, "ph": _hash(password), "role": role, "id": uid},
            )
        else:
            uid = conn.execute(
                text(
                    "INSERT INTO users (username, email, full_name, title, password_hash, role, "
                    "is_active, is_deleted, created_at, updated_at) "
                    "VALUES (:u, :e, :fn, :t, :ph, :role, true, false, NOW(), NOW()) RETURNING id"
                ),
                {"u": username, "e": email, "fn": full_name, "t": title, "ph": _hash(password), "role": role},
            ).scalar()

        # Update segment assignments
        conn.execute(
            text("DELETE FROM user_segments WHERE user_id = :uid"),
            {"uid": uid},
        )
        for seg in segments:
            conn.execute(
                text(
                    "INSERT INTO user_segments (user_id, segment, created_at, updated_at) "
                    "VALUES (:uid, :seg, NOW(), NOW()) ON CONFLICT DO NOTHING"
                ),
                {"uid": uid, "seg": seg},
            )


def downgrade() -> None:
    pass
