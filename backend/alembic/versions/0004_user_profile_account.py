"""user profile + account + quick regs
"""

from alembic import op
import sqlalchemy as sa

# Убедитесь, что длина ниже не превышает ограничение alembic_version (мы ранее обсуждали)
revision = "0004_user_profile_account"
down_revision = "0003_reg_status_created"  # например: "0003_reg_status_created"
branch_labels = None
depends_on = None

def upgrade():
    # User: новые поля
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("username", sa.String(length=64), nullable=False, server_default=""))
        b.add_column(sa.Column("avatar_path", sa.String(length=255), nullable=False, server_default=""))
        b.add_column(sa.Column("gender", sa.String(length=16), nullable=False, server_default=""))
        b.add_column(sa.Column("birth_date", sa.Date(), nullable=True))
        b.add_column(sa.Column("phone", sa.String(length=32), nullable=False, server_default=""))
        b.add_column(sa.Column("city", sa.String(length=128), nullable=False, server_default=""))
        b.add_column(sa.Column("about", sa.Text(), nullable=False, server_default=""))
    op.create_unique_constraint("uq_users_username", "users", ["username"])

    # user_event_registrations
    op.create_table(
        "user_event_registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("distance", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_user_event_reg_user", "user_event_registrations", ["user_id"])
    op.create_index("ix_user_event_reg_comp", "user_event_registrations", ["competition_id"])
    op.create_unique_constraint("uq_user_competition", "user_event_registrations", ["user_id", "competition_id"])

    # notifications
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_notifications_user", "notifications", ["user_id"])

    # reminders
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competition_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("remind_at", sa.DateTime(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="email"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_reminders_user", "reminders", ["user_id"])
    op.create_index("ix_reminders_comp", "reminders", ["competition_id"])


def downgrade():
    op.drop_index("ix_reminders_comp", table_name="reminders")
    op.drop_index("ix_reminders_user", table_name="reminders")
    op.drop_table("reminders")

    op.drop_index("ix_notifications_user", table_name="notifications")
    op.drop_table("notifications")

    op.drop_constraint("uq_user_competition", "user_event_registrations", type_="unique")
    op.drop_index("ix_user_event_reg_comp", table_name="user_event_registrations")
    op.drop_index("ix_user_event_reg_user", table_name="user_event_registrations")
    op.drop_table("user_event_registrations")

    with op.batch_alter_table("users") as b:
        b.drop_column("about")
        b.drop_column("city")
        b.drop_column("phone")
        b.drop_column("birth_date")
        b.drop_column("gender")
        b.drop_column("avatar_path")
        b.drop_column("username")
    op.drop_constraint("uq_users_username", "users", type_="unique")
