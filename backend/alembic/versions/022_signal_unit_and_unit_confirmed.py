"""Record what unit a sensor's samples are stored in, and whether that is known.

Revision ID: 022
Revises: 021a

VIK-006. Numbered 022 rather than the ticket's 019, which was taken twice over
by the time this was written -- once by the raw-channel summary stats and once
by the bearing catalogue.

Readings are currently stored exactly as they arrive, with nothing recording
whether they are volts or g. Those differ by a factor of ten, and the level at
which a machine is damaging itself is around 7 to 11 mm/s: read one way the
test pump measures 34, read the other 344. Both look entirely ordinary on a
screen.

`signal_unit` says what the stored numbers are. `unit_confirmed` says whether
anyone actually knows, and it exists because the honest answer today is no.

Existing rows are backfilled to unconfirmed rather than to 'g'. Assuming g
would be right for this deployment and wrong for the next one, and the whole
point of the column is to stop the system assuming. A downstream engine that
finds `unit_confirmed = false` is expected to refuse rather than to guess --
which is the behaviour VIK-005 relies on.

Per-channel sensitivity is deliberately NOT added here as a column. The
channel_map JSONB on plot_configurations already describes each channel's
wiring -- index, axis, signal type, label -- and sensitivity is a property of
the transducer on that channel, so it belongs in the same record. Adding a
parallel array or a new table would be a second way to say which channel is
which, and the codebase already has one. See app/schemas/measurement.py.
"""

from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None

TABLE = "sensor_configurations"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("signal_unit", sa.String(16), nullable=True))
    op.add_column(
        TABLE,
        sa.Column("unit_confirmed", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )

    # Not 'g'. Every existing row predates anyone recording this, so the true
    # state is "nobody checked", and that is what gets written.
    op.execute(f"""
        UPDATE {TABLE}
           SET signal_unit = 'unconfirmed', unit_confirmed = false
         WHERE signal_unit IS NULL
    """)


def downgrade() -> None:
    op.drop_column(TABLE, "unit_confirmed")
    op.drop_column(TABLE, "signal_unit")
