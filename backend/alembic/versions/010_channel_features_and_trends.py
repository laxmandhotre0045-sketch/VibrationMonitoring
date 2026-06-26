"""channel features, segment trends, threshold seeds (idempotent for partial installs)

Revision ID: 010
Revises: 009
Create Date: 2026-06-08 12:00:00.000000
"""
from typing import Sequence, Union
import json
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FEATURE_DEFINITIONS = [
    ("rms", "RMS", "scaled_eng", "Root mean square amplitude", 0),
    ("peak", "Peak", "scaled_eng", "Maximum absolute amplitude", 1),
    ("crest_factor", "Crest Factor", "dimensionless", "Peak / RMS", 2),
    ("kurtosis", "Kurtosis", "dimensionless", "Excess kurtosis", 3),
    ("fft_band_energy_0_500", "FFT Band Energy (0-500 Hz)", "scaled_eng_sq", "Sum of squared FFT magnitudes 0-500 Hz", 4),
    ("amplitude_1x", "1X Amplitude", "scaled_eng", "FFT magnitude at running speed", 5),
    ("amplitude_2x", "2X Amplitude", "scaled_eng", "FFT magnitude at 2x running speed", 6),
    ("amplitude_3x", "3X Amplitude", "scaled_eng", "FFT magnitude at 3x running speed", 7),
    ("envelope_rms", "Envelope RMS", "scaled_eng", "RMS of Hilbert envelope", 8),
    ("noise_floor", "Noise Floor", "dB", "Mean FFT magnitude in dB", 9),
]

THRESHOLD_RULES = [
    ("rms", "absolute_max", None, 0.01, 0.02, None, None, {}),
    ("peak", "absolute_max", None, 0.05, 0.10, None, None, {}),
    ("crest_factor", "range", None, 3.0, 5.0, 1.4, 3.0, {}),
    ("kurtosis", "absolute_max", None, 3.5, 5.0, None, None, {}),
    ("fft_band_energy_0_500", "percent_baseline", None, 120.0, 150.0, None, None, {}),
    ("amplitude_1x", "percent_rms", None, 20.0, 40.0, None, None, {}),
    ("amplitude_2x", "percent_rms", None, 10.0, 20.0, None, None, {}),
    ("amplitude_3x", "percent_rms", None, 5.0, 15.0, None, None, {}),
    ("envelope_rms", "percent_baseline", None, 100.0, 125.0, None, None, {"critical_percent": 150.0}),
    ("noise_floor", "absolute_db", None, -60.0, -54.0, None, None, {}),
]


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade() -> None:
    if not _column_exists("sensor_data_uploads", "features_status"):
        op.add_column(
            "sensor_data_uploads",
            sa.Column("features_status", sa.String(20), nullable=False, server_default="pending"),
        )
    if not _column_exists("sensor_data_uploads", "features_error"):
        op.add_column("sensor_data_uploads", sa.Column("features_error", sa.Text(), nullable=True))
    if not _column_exists("sensor_data_uploads", "features_computed_at"):
        op.add_column("sensor_data_uploads", sa.Column("features_computed_at", sa.DateTime(), nullable=True))

    if not _table_exists("feature_definitions"):
        op.create_table(
            "feature_definitions",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("code", sa.String(40), nullable=False, unique=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("unit", sa.String(30), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )

    if not _table_exists("feature_threshold_rules"):
        op.create_table(
            "feature_threshold_rules",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("feature_code", sa.String(40), sa.ForeignKey("feature_definitions.code"), nullable=False),
            sa.Column("rule_type", sa.String(30), nullable=False),
            sa.Column("machine_type", sa.String(80), nullable=True),
            sa.Column("normal_max", sa.Numeric(18, 8), nullable=True),
            sa.Column("warning_max", sa.Numeric(18, 8), nullable=True),
            sa.Column("normal_min", sa.Numeric(18, 8), nullable=True),
            sa.Column("warning_min", sa.Numeric(18, 8), nullable=True),
            sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        )
        op.create_index(
            "ix_feature_threshold_rules_code_machine",
            "feature_threshold_rules",
            ["feature_code", "machine_type"],
        )

    if not _table_exists("measurement_channel_features"):
        op.create_table(
            "measurement_channel_features",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("upload_id", UUID(as_uuid=True), sa.ForeignKey("sensor_data_uploads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sensor_id", UUID(as_uuid=True), sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("channel", sa.Integer(), nullable=False),
            sa.Column("feature_code", sa.String(40), sa.ForeignKey("feature_definitions.code"), nullable=False),
            sa.Column("value", sa.Numeric(18, 8), nullable=False),
            sa.Column("unit", sa.String(30), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("computed_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("upload_id", "channel", "feature_code", name="uq_measurement_channel_feature"),
        )
        op.create_index("ix_measurement_channel_features_upload", "measurement_channel_features", ["upload_id"])

    if not _table_exists("baseline_channel_features"):
        op.create_table(
            "baseline_channel_features",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("baseline_id", UUID(as_uuid=True), sa.ForeignKey("sensor_baselines.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sensor_id", UUID(as_uuid=True), sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("channel", sa.Integer(), nullable=False),
            sa.Column("feature_code", sa.String(40), sa.ForeignKey("feature_definitions.code"), nullable=False),
            sa.Column("value", sa.Numeric(18, 8), nullable=False),
            sa.Column("unit", sa.String(30), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="normal"),
            sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("computed_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("baseline_id", "channel", "feature_code", name="uq_baseline_channel_feature"),
        )
        op.create_index("ix_baseline_channel_features_baseline", "baseline_channel_features", ["baseline_id"])

    conn = op.get_bind()
    existing_defs = conn.execute(sa.text("SELECT COUNT(*) FROM feature_definitions")).scalar() or 0
    if existing_defs == 0:
        for code, name, unit, desc, sort_order in FEATURE_DEFINITIONS:
            conn.execute(
                sa.text(
                    "INSERT INTO feature_definitions (id, code, name, unit, description, sort_order) "
                    "VALUES (:id, :code, :name, :unit, :desc, :sort_order)"
                ),
                {"id": str(uuid.uuid4()), "code": code, "name": name, "unit": unit, "desc": desc, "sort_order": sort_order},
            )

    existing_rules = conn.execute(sa.text("SELECT COUNT(*) FROM feature_threshold_rules")).scalar() or 0
    if existing_rules == 0:
        for code, rule_type, machine_type, n_max, w_max, n_min, w_min, meta in THRESHOLD_RULES:
            conn.execute(
                sa.text(
                    "INSERT INTO feature_threshold_rules "
                    "(id, feature_code, rule_type, machine_type, normal_max, warning_max, normal_min, warning_min, metadata) "
                    "VALUES (:id, :code, :rule_type, :machine_type, :n_max, :w_max, :n_min, :w_min, CAST(:meta AS jsonb))"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "code": code,
                    "rule_type": rule_type,
                    "machine_type": machine_type,
                    "n_max": n_max,
                    "w_max": w_max,
                    "n_min": n_min,
                    "w_min": w_min,
                    "meta": json.dumps(meta),
                },
            )


def downgrade() -> None:
    if _table_exists("baseline_channel_features"):
        op.drop_index("ix_baseline_channel_features_baseline", table_name="baseline_channel_features")
        op.drop_table("baseline_channel_features")
    if _table_exists("measurement_channel_features"):
        op.drop_index("ix_measurement_channel_features_upload", table_name="measurement_channel_features")
        op.drop_table("measurement_channel_features")
    if _table_exists("feature_threshold_rules"):
        op.drop_index("ix_feature_threshold_rules_code_machine", table_name="feature_threshold_rules")
        op.drop_table("feature_threshold_rules")
    if _table_exists("feature_definitions"):
        op.drop_table("feature_definitions")
    if _column_exists("sensor_data_uploads", "features_computed_at"):
        op.drop_column("sensor_data_uploads", "features_computed_at")
    if _column_exists("sensor_data_uploads", "features_error"):
        op.drop_column("sensor_data_uploads", "features_error")
    if _column_exists("sensor_data_uploads", "features_status"):
        op.drop_column("sensor_data_uploads", "features_status")
