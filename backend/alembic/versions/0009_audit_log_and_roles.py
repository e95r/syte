"""add roles and audit log tables

Revision ID: 0009_audit_log_and_roles
Revises: 0008_registrations_trash
Create Date: 2024-07-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009_audit_log_and_roles"
down_revision = "0008_registrations_trash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.String(length=255), nullable=True),
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id", name="pk_user_roles"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=True),
        sa.Column("object_id", sa.Integer(), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    bind = op.get_bind()

    result = bind.execute(
        sa.text(
            "INSERT INTO roles (name, description) VALUES (:name, :description) "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id"
        ),
        {"name": "admin", "description": "Администратор"},
    )
    admin_role_id = result.scalar()

    if admin_role_id:
        bind.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT id, :role_id FROM users WHERE is_admin = TRUE "
                "ON CONFLICT DO NOTHING"
            ),
            {"role_id": admin_role_id},
        )


def downgrade() -> None:
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("user_roles")
    op.drop_table("roles")
