"""Distributor-based RBAC and individual employee logins.

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-09-16
"""

from __future__ import annotations

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "n4o5p6q7r8s9"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


EMPLOYEE_USERS = [
    ("admin", "debrabata@apcotex.com", "Mr. Debrabata", "Admin", "admin123", "admin"),
    ("anup", "anup@apcotex.com", "Mr. Anup Pandey", "Sales Owner", "Sales@123", "user"),
    ("sachin", "sachin@apcotex.com", "Mr. Sachin Kasar", "Sales Owner", "Sales@123", "user"),
]

LEGACY_PERSONAS = ["salesPaper", "salesCarpet", "salesConstruction", "salesRubber", "salesGloves"]


def upgrade() -> None:
    op.create_table(
        "user_distributors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("distributor_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["distributor_id"], ["distributors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "distributor_id", name="uq_user_distributors_user_distributor"),
    )
    op.create_index("ix_user_distributors_user_id", "user_distributors", ["user_id"])
    op.create_index("ix_user_distributors_distributor_id", "user_distributors", ["distributor_id"])

    conn = op.get_bind()

    # Seed/update individual employee logins
    for username, email, full_name, title, password, role in EMPLOYEE_USERS:
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
            conn.execute(
                text(
                    "INSERT INTO users (username, email, full_name, title, password_hash, role, "
                    "is_active, is_deleted, created_at, updated_at) "
                    "VALUES (:u, :e, :fn, :t, :ph, :role, true, false, NOW(), NOW())"
                ),
                {"u": username, "e": email, "fn": full_name, "t": title, "ph": _hash(password), "role": role},
            )

    # Deactivate legacy persona users
    for persona in LEGACY_PERSONAS:
        conn.execute(
            text("UPDATE users SET is_active = false WHERE username = :u"),
            {"u": persona},
        )


def downgrade() -> None:
    op.drop_table("user_distributors")
