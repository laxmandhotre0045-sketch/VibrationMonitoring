"""plot_results table — store computed graph x/y in JSONB

Revision ID: 006
Revises: 005
Create Date: 2026-06-10 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plot_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sensor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plot_type", sa.String(40), nullable=False),
        sa.Column("channel", sa.Integer, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("x_label", sa.String(80), nullable=False),
        sa.Column("y_label", sa.String(80), nullable=False),
        sa.Column("x_data", postgresql.JSONB, nullable=False),
        sa.Column("y_data", postgresql.JSONB, nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("point_count", sa.Integer, nullable=False),
        sa.Column("sampling_rate_hz", sa.Numeric(12, 4), nullable=False),
        sa.Column("fft_lines", sa.Integer, nullable=True),
        sa.Column("frequency_max_hz", sa.Numeric(12, 4), nullable=True),
        sa.Column("config_fingerprint", sa.String(64), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
    )
    op.create_index("ix_plot_results_upload_id", "plot_results", ["upload_id"])
    op.create_index("ix_plot_results_sensor_id", "plot_results", ["sensor_id"])
    op.create_unique_constraint(
        "uq_plot_results_upload_plot_channel_fingerprint",
        "plot_results",
        ["upload_id", "plot_type", "channel", "config_fingerprint"],
    )

    op.add_column(
        "sensor_data_uploads",
        sa.Column("plots_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "sensor_data_uploads",
        sa.Column("plots_error", sa.Text, nullable=True),
    )
    op.add_column(
        "sensor_data_uploads",
        sa.Column("plots_computed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sensor_data_uploads", "plots_computed_at")
    op.drop_column("sensor_data_uploads", "plots_error")
    op.drop_column("sensor_data_uploads", "plots_status")
    op.drop_table("plot_results")
