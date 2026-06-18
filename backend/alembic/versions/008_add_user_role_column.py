"""add user role column and seed admin/user roles

Revision ID: 008
Revises: 007
Create Date: 2026-06-17 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'user'"),
        ),
    )

    op.execute(
        """
        UPDATE users
        SET role = 'super_admin'
        WHERE id IN (
            SELECT user_id FROM user_roles JOIN roles ON roles.id = user_roles.role_id WHERE roles.name = 'super_admin'
        )
        """
    )
    op.execute(
        """
        UPDATE users
        SET role = 'admin'
        WHERE role = 'user'
          AND id IN (
            SELECT user_id FROM user_roles JOIN roles ON roles.id = user_roles.role_id WHERE roles.name IN ('admin', 'plant_admin', 'engineer')
        )
        """
    )

    op.execute(
        """
        INSERT INTO roles (name, description)
        VALUES
          ('admin', 'Application administrator with full write access.'),
          ('user', 'Read-only platform user.')
        ON CONFLICT (name) DO NOTHING
        """
    )

    op.create_check_constraint(
        "ck_users_role_allowed",
        "users",
        "role IN ('super_admin', 'admin', 'user')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_role_allowed", "users", type_="check")
    op.drop_column("users", "role")
