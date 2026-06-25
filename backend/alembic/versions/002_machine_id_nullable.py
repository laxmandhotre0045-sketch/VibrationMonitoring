"""make machine_id nullable

Revision ID: 002
Revises: 001
Create Date: 2026-06-06

"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("equipment_masters", "machine_id", nullable=True)


def downgrade() -> None:
    op.alter_column("equipment_masters", "machine_id", nullable=False)
