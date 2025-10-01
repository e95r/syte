"""Add essential indexes and case-insensitive email constraint"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import NoSuchTableError


# revision identifiers, used by Alembic.
revision = "0010_indexes"
down_revision = "0009_audit_log_and_roles"
branch_labels = None
depends_on = None


def _table_has_index(inspector: sa.Inspector, table: str, name: str) -> bool:
    try:
        indexes = inspector.get_indexes(table)
    except NoSuchTableError:
        return False
    return any(ix["name"] == name for ix in indexes)


def _table_exists(inspector: sa.Inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _unique_constraint_exists(inspector: sa.Inspector, table: str, name: str) -> bool:
    try:
        uniques = inspector.get_unique_constraints(table)
    except NoSuchTableError:
        return False
    return any(uc["name"] == name for uc in uniques)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "registrations") and not _table_has_index(
        inspector, "registrations", "ix_registrations_competition_id"
    ):
        op.create_index("ix_registrations_competition_id", "registrations", ["competition_id"])

    results_table: str | None = None
    for candidate in ("results", "swim_results"):
        if _table_exists(inspector, candidate):
            results_table = candidate
            break

    if results_table:
        index_name = f"ix_{results_table}_user_id"
        if not _table_has_index(inspector, results_table, index_name):
            op.create_index(index_name, results_table, ["user_id"])

    if _unique_constraint_exists(inspector, "users", "users_email_key"):
        op.drop_constraint("users_email_key", "users", type_="unique")

    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_has_index(inspector, "registrations", "ix_registrations_competition_id"):
        op.drop_index("ix_registrations_competition_id", table_name="registrations")

    for table in ("results", "swim_results"):
        index_name = f"ix_{table}_user_id"
        if _table_has_index(inspector, table, index_name):
            op.drop_index(index_name, table_name=table)

    if _table_has_index(inspector, "users", "uq_users_email_lower"):
        op.drop_index("uq_users_email_lower", table_name="users")

    if not _unique_constraint_exists(inspector, "users", "users_email_key"):
        op.create_unique_constraint("users_email_key", "users", ["email"])
