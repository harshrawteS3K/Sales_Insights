"""Add username + password_hash for identity management; seed demo admin/user.

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-08-04
"""

from __future__ import annotations

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "j0e1f2a3b4c5"
down_revision = "i9d0e1f2a3b4"
branch_labels = None
depends_on = None


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        text("SELECT id, email, full_name FROM users WHERE is_deleted = false")
    ).fetchall()

    used: set[str] = set()
    for row in rows:
        local = (row.email or f"user{row.id}").split("@")[0].strip().lower() or f"user{row.id}"
        candidate = local
        suffix = 1
        while candidate in used:
            candidate = f"{local}{suffix}"
            suffix += 1
        used.add(candidate)
        conn.execute(
            text("UPDATE users SET username = :u WHERE id = :id"),
            {"u": candidate, "id": row.id},
        )

    # Ensure demo Admin / User accounts exist for continuity with prior local login
    existing_usernames = {
        r[0]
        for r in conn.execute(
            text("SELECT username FROM users WHERE is_deleted = false AND username IS NOT NULL")
        ).fetchall()
    }
    seeds = [
        ("admin", "Debabrata C", "admin", "admin123", "CMO", "admin@apcotex.local"),
        ("user", "Rajesh Kumar", "user", "user123", "Research Analyst", "user@apcotex.local"),
    ]
    for username, full_name, role, password, title, email in seeds:
        if username in existing_usernames:
            # Refresh password hash if missing so demo login keeps working
            conn.execute(
                text(
                    "UPDATE users SET password_hash = COALESCE(password_hash, :ph), "
                    "is_active = true WHERE username = :u AND is_deleted = false"
                ),
                {"ph": _hash(password), "u": username},
            )
            continue
        conn.execute(
            text(
                "INSERT INTO users (username, email, full_name, title, password_hash, role, "
                "is_active, is_deleted, created_at, updated_at) "
                "VALUES (:username, :email, :full_name, :title, :password_hash, :role, "
                "true, false, NOW(), NOW())"
            ),
            {
                "username": username,
                "email": email,
                "full_name": full_name,
                "title": title,
                "password_hash": _hash(password),
                "role": role,
            },
        )

    # Any remaining null usernames (deleted rows) get a placeholder
    conn.execute(
        text(
            "UPDATE users SET username = 'deleted_' || id::text "
            "WHERE username IS NULL"
        )
    )

    op.alter_column("users", "username", existing_type=sa.String(length=100), nullable=False)
    op.create_index(
        "ix_users_username_active",
        "users",
        ["username"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_username_active", table_name="users")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
