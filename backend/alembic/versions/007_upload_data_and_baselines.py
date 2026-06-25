"""measurement_upload_data + sensor_baselines + baseline_plot_results

Revision ID: 007
Revises: 006
Create Date: 2026-06-15 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table 1 — full uploaded file + parsed samples in PostgreSQL
    op.create_table(
        "measurement_upload_data",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "sensor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("file_content", sa.LargeBinary, nullable=False),
        sa.Column("parsed_data", postgresql.JSONB, nullable=False),
        sa.Column("channel_count", sa.Integer, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_measurement_upload_data_sensor_id", "measurement_upload_data", ["sensor_id"])

    # Table 2 — all baselines kept (append-only history for RAG / auto-learning)
    op.create_table(
        "sensor_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "sensor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_upload_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_data_uploads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("labels", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_format", sa.String(10), nullable=False),
        sa.Column("file_content", sa.LargeBinary, nullable=False),
        sa.Column("parsed_data", postgresql.JSONB, nullable=False),
        sa.Column("channel_count", sa.Integer, nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("sampling_rate_hz", sa.Numeric(12, 4), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_sensor_baselines_sensor_id", "sensor_baselines", ["sensor_id"])
    op.create_index("ix_sensor_baselines_created_at", "sensor_baselines", ["created_at"])

    op.create_table(
        "baseline_plot_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "baseline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sensor_baselines.id", ondelete="CASCADE"),
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
    op.create_index("ix_baseline_plot_results_baseline_id", "baseline_plot_results", ["baseline_id"])
    op.create_unique_constraint(
        "uq_baseline_plot_results_baseline_plot_channel_fingerprint",
        "baseline_plot_results",
        ["baseline_id", "plot_type", "channel", "config_fingerprint"],
    )


def downgrade() -> None:
    op.drop_table("baseline_plot_results")
    op.drop_table("sensor_baselines")
    op.drop_table("measurement_upload_data")
