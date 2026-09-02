"""store raw vibration samples in the database

Until now a raw snapshot lived only on disk: the verbatim CSV plus a normalised
JSON file beside it, with `measurement_upload_data.parsed_data` deliberately left
empty because writing ~200k numbers as JSONB cost seconds per snapshot.

That kept ingest fast but left the samples outside the database. These two
tables put them back in, without the JSONB cost, by storing each channel as a
Postgres `double precision[]` — a binary array Postgres does not have to parse
out of JSON text.

  raw_vibration_captures   one row per upload: timebase and shape
  raw_vibration_channels   one row per channel: the sample array itself

Timestamps are NOT stored. Acquisition is uniform, so the time axis is fully
described by `sample_rate_hz` and `sample_count`; keeping a parallel array of
2500+ floats per capture would double the storage to record numbers that are
already implied.

Purely additive: two new tables, nothing altered, nothing dropped. Existing
snapshots keep reading from disk — the read path prefers these tables and falls
back — so no backfill is required for old data to keep working.

Revision ID: 018
Revises: 017
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CAPTURES = "raw_vibration_captures"
CHANNELS = "raw_vibration_channels"


def _tables() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    existing = _tables()

    if CAPTURES not in existing:
        op.create_table(
            CAPTURES,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
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
            sa.Column("sample_rate_hz", sa.Float(), nullable=False),
            sa.Column("sample_count", sa.Integer(), nullable=False),
            sa.Column("channel_count", sa.Integer(), nullable=False),
            # Absolute capture start, when the device wrote wall-clock time. The
            # per-sample axis is elapsed seconds from zero; this is what zero
            # corresponds to.
            sa.Column("start_epoch_s", sa.Float(), nullable=True),
            # Which unit the device's time column turned out to be written in.
            sa.Column(
                "timebase_unit",
                sa.String(4),
                nullable=False,
                server_default="s",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_raw_captures_sensor_created", CAPTURES, ["sensor_id", "created_at"]
        )

    if CHANNELS not in existing:
        op.create_table(
            CHANNELS,
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "capture_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey(f"{CAPTURES}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("channel_index", sa.Integer(), nullable=False),
            sa.Column(
                "samples",
                postgresql.ARRAY(sa.Float(precision=53)),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "capture_id", "channel_index", name="uq_raw_channel_per_capture"
            ),
        )
        op.create_index("ix_raw_channels_capture", CHANNELS, ["capture_id"])


def downgrade() -> None:
    existing = _tables()
    if CHANNELS in existing:
        op.drop_table(CHANNELS)
    if CAPTURES in existing:
        op.drop_table(CAPTURES)
