"""registration team optional fields"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_registration_team_fields"
down_revision = "0011_add_heats_lanes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "registrations",
        "team_name",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.add_column(
        "registrations",
        sa.Column("team_representative", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "registrations",
        sa.Column(
            "team_members_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE registrations
            SET team_representative = representative_name
            WHERE representative_name IS NOT NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE registrations AS r
            SET team_members_count = COALESCE(sub.cnt, 0)
            FROM (
                SELECT team_id, COUNT(*) AS cnt
                FROM participants
                GROUP BY team_id
            ) AS sub
            WHERE sub.team_id = r.id
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE registrations
            SET team_members_count = 1
            WHERE team_members_count IS NULL OR team_members_count < 1
            """
        )
    )
    op.alter_column(
        "registrations",
        "team_members_count",
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "registrations",
        "team_members_count",
        server_default="1",
    )
    op.alter_column(
        "registrations",
        "team_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_column("registrations", "team_members_count")
    op.drop_column("registrations", "team_representative")
