from alembic import op
import sqlalchemy as sa

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now())
    )
    op.create_table(
        "competitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("city", sa.String(255), server_default=""),
        sa.Column("pool_name", sa.String(255), server_default=""),
        sa.Column("address", sa.String(255), server_default=""),
        sa.Column("start_date", sa.DateTime, nullable=False),
        sa.Column("end_date", sa.DateTime),
        sa.Column("is_open", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("hero_image", sa.String(255), server_default=""),
        sa.Column("regulation_pdf", sa.String(255), server_default=""),
        sa.Column("live_stream_url", sa.String(255), server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "news",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("body", sa.Text, server_default=""),
        sa.Column("published_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("cover_image", sa.String(255), server_default=""),
    )
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("competition_id", sa.Integer, sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("athlete_name", sa.String(255), nullable=False),
        sa.Column("birthdate", sa.Date),
        sa.Column("club", sa.String(255), server_default=""),
        sa.Column("coach", sa.String(255), server_default=""),
        sa.Column("phone", sa.String(64), server_default=""),
        sa.Column("email", sa.String(255), server_default=""),
        sa.Column("distance", sa.String(64), server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("competition_id", "athlete_name", "birthdate", name="uq_reg_athlete")
    )
    op.create_table(
        "result_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("competition_id", sa.Integer, sa.ForeignKey("competitions.id"), nullable=False),
        sa.Column("kind", sa.String(32), server_default="pdf"),
        sa.Column("file_path", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), server_default=""),
        sa.Column("uploaded_at", sa.DateTime, server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table("result_files")
    op.drop_table("registrations")
    op.drop_table("news")
    op.drop_table("competitions")
    op.drop_table("users")
