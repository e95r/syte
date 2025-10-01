"""add heats and lanes tables"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_add_heats_lanes"
down_revision = "0010_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "heats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("session_name", sa.String(length=128), nullable=True),
        sa.Column("distance", sa.String(length=128), nullable=False),
        sa.Column("age_category", sa.String(length=64), nullable=True),
        sa.Column("heat_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "competition_id",
            "session_name",
            "distance",
            "age_category",
            "heat_number",
            name="uq_heat_number_per_event",
        ),
    )

    op.create_index("ix_heats_competition_id", "heats", ["competition_id"])
    op.create_index("ix_heats_session_name", "heats", ["session_name"])
    op.create_index("ix_heats_distance", "heats", ["distance"])

    op.create_table(
        "lanes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("heat_id", sa.Integer(), nullable=False),
        sa.Column("lane_number", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=True),
        sa.Column("seed_time_ms", sa.Integer(), nullable=True),
        sa.Column("seed_time_text", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["heat_id"], ["heats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("heat_id", "lane_number", name="uq_lane_per_heat"),
    )

    op.create_index("ix_lanes_heat_id", "lanes", ["heat_id"])
    op.create_index("ix_lanes_participant_id", "lanes", ["participant_id"])


def downgrade() -> None:
    op.drop_index("ix_lanes_participant_id", table_name="lanes")
    op.drop_index("ix_lanes_heat_id", table_name="lanes")
    op.drop_table("lanes")

    op.drop_index("ix_heats_distance", table_name="heats")
    op.drop_index("ix_heats_session_name", table_name="heats")
    op.drop_index("ix_heats_competition_id", table_name="heats")
    op.drop_table("heats")
