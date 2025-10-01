from alembic import op
import sqlalchemy as sa

revision = "0003_reg_status_created"
down_revision = "0002_rework_registrations"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("registrations") as b:
        b.add_column(sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"))
        b.add_column(sa.Column("created_at", sa.DateTime, server_default=sa.func.now()))
    # убрать server_default с status, чтобы в модель работать по умолчанию приложения
    op.execute("ALTER TABLE registrations ALTER COLUMN status DROP DEFAULT")

def downgrade():
    with op.batch_alter_table("registrations") as b:
        b.drop_column("created_at")
        b.drop_column("status")
