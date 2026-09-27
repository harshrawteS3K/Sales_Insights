"""Allow one distributor to keep a parser profile per workbook fingerprint.

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-09-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "x4y5z6a7b8c9"
down_revision = "w3x4y5z6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "distributor_parser_profiles" not in set(inspector.get_table_names()):
        return
    uniques = {item["name"] for item in inspector.get_unique_constraints("distributor_parser_profiles")}
    if "uq_distributor_parser_profiles_distributor" in uniques:
        op.drop_constraint(
            "uq_distributor_parser_profiles_distributor",
            "distributor_parser_profiles",
            type_="unique",
        )
    uniques = {item["name"] for item in sa.inspect(conn).get_unique_constraints("distributor_parser_profiles")}
    if "uq_distributor_parser_profiles_fingerprint" not in uniques:
        op.create_unique_constraint(
            "uq_distributor_parser_profiles_fingerprint",
            "distributor_parser_profiles",
            ["distributor_id", "fingerprint_hash"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_distributor_parser_profiles_fingerprint",
        "distributor_parser_profiles",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_distributor_parser_profiles_distributor",
        "distributor_parser_profiles",
        ["distributor_id"],
    )
