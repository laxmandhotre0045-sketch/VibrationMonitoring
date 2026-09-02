"""collection interval, channel mapping and MQTT settings per sensor

Extends the per-sensor acquisition configuration so the edge uploader can fetch
everything it needs from one endpoint instead of carrying its own constants:

  * collection_interval_minutes — how often a new acquisition is taken. This is
    NOT the sample rate and NOT the FFT block time.
  * channel_map — per-channel signal type and axis (CH1..CHn).
  * mqtt_broker / mqtt_port / mqtt_topic — where the device publishes.

Purely additive. Every column is nullable or carries a server default, so
existing rows keep working untouched and nothing is rewritten or dropped.

Revision ID: 017
Revises: 016
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "plot_configurations"

DEFAULT_INTERVAL_MINUTES = 2
DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_TOPIC = "Vibration_Data"


def _columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    existing = _columns()

    if "collection_interval_minutes" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "collection_interval_minutes",
                sa.Integer(),
                nullable=False,
                server_default=str(DEFAULT_INTERVAL_MINUTES),
            ),
        )

    if "channel_map" not in existing:
        # Empty means "not configured"; the API fills a sensible default rather
        # than this migration inventing an axis layout for existing sensors.
        op.add_column(
            TABLE,
            sa.Column("channel_map", JSONB(), nullable=False, server_default="[]"),
        )

    if "mqtt_broker" not in existing:
        op.add_column(TABLE, sa.Column("mqtt_broker", sa.String(255), nullable=True))

    if "mqtt_port" not in existing:
        op.add_column(
            TABLE,
            sa.Column("mqtt_port", sa.Integer(), nullable=False, server_default=str(DEFAULT_MQTT_PORT)),
        )

    if "mqtt_topic" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "mqtt_topic",
                sa.String(255),
                nullable=False,
                server_default=DEFAULT_MQTT_TOPIC,
            ),
        )


def downgrade() -> None:
    existing = _columns()
    for name in (
        "mqtt_topic",
        "mqtt_port",
        "mqtt_broker",
        "channel_map",
        "collection_interval_minutes",
    ):
        if name in existing:
            op.drop_column(TABLE, name)
