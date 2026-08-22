"""device ingest provenance — measured_at, rotation speed, originating api key

Revision ID: 014
Revises: 013
Create Date: 2026-08-18 15:10:00.000000

A device-posted measurement carries two timestamps that must not be conflated:
`created_at` is when the server received it, `measured_at` is when the device
actually captured the waveform. Devices buffer over dropped links and their
clocks drift, so the two can differ by hours and only `measured_at` is
meaningful for trending.

`rotation_speed_rpm` is the speed at the moment of capture. equipment_masters
already carries rated_rpm and an operating range, but those are nameplate
values — every bearing fault frequency is a multiple of the *actual* speed, so
without it the diagnostics fall back to estimating shaft speed from the
spectrum.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "sensor_data_uploads"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {col["name"] for col in inspector.get_columns(TABLE)}
    indexes = {ix["name"] for ix in inspector.get_indexes(TABLE)}

    if "measured_at" not in existing:
        # timestamptz to match created_at / parsed_at / plots_computed_at on this
        # table. A naive sibling would be compared against them via an implicit
        # cast that silently depends on the session TimeZone setting.
        op.add_column(TABLE, sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True))
        # Everything already stored arrived by manual upload, where the only
        # timestamp we ever had was the moment of upload. Seeding measured_at
        # from it keeps the column usable for ordering without inventing data.
        op.execute(f"UPDATE {TABLE} SET measured_at = created_at WHERE measured_at IS NULL")

    if "rotation_speed_rpm" not in existing:
        op.add_column(
            TABLE, sa.Column("rotation_speed_rpm", sa.Numeric(10, 2), nullable=True)
        )

    if "api_key_id" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "api_key_id",
                UUID(as_uuid=True),
                # The measurement outlives the credential that delivered it, so
                # revoking or deleting a key must not take readings with it.
                sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    # Trending reads a sensor's history in capture order, not arrival order.
    if "ix_sensor_data_uploads_sensor_id_measured_at" not in indexes:
        op.create_index(
            "ix_sensor_data_uploads_sensor_id_measured_at",
            TABLE,
            ["sensor_id", "measured_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_sensor_data_uploads_sensor_id_measured_at", table_name=TABLE)
    op.drop_column(TABLE, "api_key_id")
    op.drop_column(TABLE, "rotation_speed_rpm")
    op.drop_column(TABLE, "measured_at")
