"""add soft delete fields for registrations

Revision ID: 0008_registrations_trash
Revises: 0007_account_delete_otp
Create Date: 2024-07-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_registrations_trash"
down_revision = "0007_account_delete_otp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registrations",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "registrations",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.alter_column("registrations", "is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_column("registrations", "deleted_at")
    op.drop_column("registrations", "is_deleted")
