"""add competition series and stage

Revision ID: 0006_competition_series_stage
Revises: 0005_verify_email_phone
Create Date: 2024-05-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_competition_series_stage"
down_revision = "0005_verify_email_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "competition_series",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
    )
    op.add_column(
        "competitions",
        sa.Column("stage", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "competitions",
        sa.Column("series_id", sa.Integer, nullable=True),
    )
    op.create_index("ix_competitions_series_id", "competitions", ["series_id"])
    op.create_foreign_key(
        "fk_competitions_series_id",
        "competitions",
        "competition_series",
        ["series_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_competitions_series_id", "competitions", type_="foreignkey")
    op.drop_index("ix_competitions_series_id", table_name="competitions")
    op.drop_column("competitions", "series_id")
    op.drop_column("competitions", "stage")
    op.drop_table("competition_series")
