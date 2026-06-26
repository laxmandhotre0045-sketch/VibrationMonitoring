"""add measurement_channel_feature_trends (partial 010 recovery)

Revision ID: 011
Revises: 010
Create Date: 2026-06-08 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "measurement_channel_feature_trends" in inspector.get_table_names():
        return

    op.create_table(
        "measurement_channel_feature_trends",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("upload_id", UUID(as_uuid=True), sa.ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sensor_id", UUID(as_uuid=True), sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("feature_code", sa.String(40), sa.ForeignKey("feature_definitions.code"), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("time_s", sa.Numeric(18, 8), nullable=False),
        sa.Column("value", sa.Numeric(18, 8), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "upload_id", "channel", "feature_code", "segment_index",
            name="uq_measurement_channel_feature_trend",
        ),
    )
    op.create_index(
        "ix_measurement_channel_feature_trends_upload",
        "measurement_channel_feature_trends",
        ["upload_id", "channel"],
    )


def downgrade() -> None:
    op.drop_index("ix_measurement_channel_feature_trends_upload", table_name="measurement_channel_feature_trends")
    op.drop_table("measurement_channel_feature_trends")
