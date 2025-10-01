"""add delete otp fields for account removal

Revision ID: 0007_account_delete_otp
Revises: 0006_competition_series_stage
Create Date: 2024-06-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_account_delete_otp"
down_revision = "0006_competition_series_stage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("delete_otp", sa.String(length=6), nullable=True))
    op.add_column("users", sa.Column("delete_otp_expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "delete_otp_expires_at")
    op.drop_column("users", "delete_otp")
