"""email & phone verification"""
from alembic import op
import sqlalchemy as sa

revision = "0005_verify_email_phone"
down_revision = "0004_user_profile_account"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("email_verified_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("phone_verified_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("phone_otp", sa.String(length=6), nullable=True))
        b.add_column(sa.Column("phone_otp_expires_at", sa.DateTime(), nullable=True))

def downgrade():
    with op.batch_alter_table("users") as b:
        b.drop_column("phone_otp_expires_at")
        b.drop_column("phone_otp")
        b.drop_column("phone_verified_at")
        b.drop_column("email_verified_at")
