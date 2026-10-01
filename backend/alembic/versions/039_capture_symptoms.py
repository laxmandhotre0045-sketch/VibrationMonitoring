"""Symptoms belong to the capture, not to the fault — VIK-051 corrected.

Revision ID: 039
Revises: 038

038 put a `symptoms` column on `fault_findings`, and reprocessing a real
capture showed why that alone is not enough.

**The detection sat behind the shaft-speed gate.** `persist_findings`
returns early when no shaft speed could be established, because every rule
in the table is written in orders and an order computed against a guessed
speed is wrong by the ratio of the guess. Symptoms were detected inside the
per-channel loop, which is after that return. On this gateway no capture has
ever established a shaft speed -- so the symptom layer ran zero times in
production, and the column added one migration ago was never written to.

The ticket's own justification is what this broke. VIK-051 exists so that a
capture matching no rule still has something said about it, and this is
exactly the machine where no capture matches any rule. The one place the
feature was meant to earn its keep was the one place it could not run.

**And a symptom is not a property of a fault.** It is a property of a
channel in a capture: the waveform is impacting, energy sits in the bearing
band. Hanging it off a finding meant it could only exist where a finding
did. This table is the right shape, and it is written before the shaft-speed
gate rather than after it.

The column on `fault_findings` stays. A finding travels alone to whoever
reads it and has to carry its own context, the same reason `resolution` is
repeated on every row. This table is where the observations live when there
is no finding to carry them -- which, here, is always.

**Half a symptom set is still recorded as half.** Without a shaft speed
there are no orders, so the harmonic-series, sideband and sub-synchronous
checks cannot run; the crest-factor and band-energy ones can. `shaft_usable`
says which of those two situations produced the row, so an empty list is
never mistaken for a quiet machine.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None

TABLE = "capture_symptoms"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        # The observations, each with the sentences that produced it.
        sa.Column("symptoms", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        # Which checks were able to run. Without a shaft speed the
        # order-based ones cannot, and an empty list from a capture that
        # could only run two checks means something different from an empty
        # list from a capture that ran five.
        sa.Column("shaft_usable", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("checks_run", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("checks_possible", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # One row per channel per capture. Reprocessing updates it rather than
    # adding a second, the same rule findings follow.
    op.create_unique_constraint(
        f"uq_{TABLE}_upload_channel", TABLE, ["upload_id", "channel"])
    op.create_index(f"ix_{TABLE}_sensor", TABLE, ["sensor_id", "created_at"])
    op.create_check_constraint(f"ck_{TABLE}_channel", TABLE, "channel >= 0")
    op.create_check_constraint(
        f"ck_{TABLE}_checks", TABLE,
        "checks_run >= 0 AND checks_run <= checks_possible")


def downgrade() -> None:
    op.drop_table(TABLE)
