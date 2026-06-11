"""add device_id to sensor_configurations for edge lookup

Revision ID: 005
Revises: 004
Create Date: 2026-06-10 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sensor_configurations",
        sa.Column("device_id", sa.String(64), nullable=True),
    )
    op.create_index("ix_sensor_configurations_device_id", "sensor_configurations", ["device_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_sensor_configurations_device_id", table_name="sensor_configurations")
    op.drop_column("sensor_configurations", "device_id")
