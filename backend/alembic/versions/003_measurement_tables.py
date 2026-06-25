"""measurement and plot configuration tables

Revision ID: 003
Revises: 002
Create Date: 2026-06-08 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plot_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("active_channel", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sampling_rate_hz", sa.Numeric(12, 4), nullable=False, server_default="25600"),
        sa.Column("fft_lines", sa.Integer, nullable=False, server_default="1600"),
        sa.Column("frequency_max_hz", sa.Numeric(12, 4), nullable=True),
        sa.Column("data_type", sa.String(30), nullable=False, server_default="acceleration"),
        sa.Column("enabled_plots", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_plot_config_sensor_id", "plot_configurations", ["sensor_id"], unique=True)

    op.create_table(
        "sensor_data_uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_count", sa.Integer, nullable=False),
        sa.Column("pdf_path", sa.String(500), nullable=False),
        sa.Column("parsed_data_path", sa.String(500), nullable=True),
        sa.Column("sample_count", sa.Integer, nullable=True),
        sa.Column("parse_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("parse_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sensor_upload_sensor_id", "sensor_data_uploads", ["sensor_id"])


def downgrade() -> None:
    op.drop_table("sensor_data_uploads")
    op.drop_table("plot_configurations")
