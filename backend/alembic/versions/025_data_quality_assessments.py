"""Store what each capture's data was worth — VIK-022.

Revision ID: 025
Revises: 024

One row per channel per capture: the level, the confidence factor every
engine downstream multiplies by, and the checks that failed with their
reasons.

Stored rather than recomputed for two reasons. A finding recorded last month
has to be explainable now, and "confidence reduced due to poor signal
quality" is only auditable if the assessment that reduced it survives
alongside it. And the thresholds here are calibrated against this hardware,
so they will move -- at which point an old finding must still show the
judgement that was actually made, not the one today's code would make.

`checks` keeps every check, not only the failures, so a reader can see what
was measured and what could not be assessed. The distinction matters: a
capture too short to judge steadiness is not a capture with steady speed.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None

TABLE = "data_quality_assessments"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Null means the assessment for the capture as a whole, which takes
        # its worst channel. A per-channel row and a whole-capture row are
        # different answers and both are wanted: an engine reading one
        # channel should not be held back by another channel's dead sensor.
        sa.Column("channel", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("confidence_factor", sa.Numeric(4, 3), nullable=False),
        sa.Column("failed_checks", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("not_assessed", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("checks", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        # The thresholds are calibrated against this gateway and will change.
        # Without this, an assessment from before a recalibration cannot be
        # told apart from one after it.
        sa.Column("engine_version", sa.String(32), nullable=False,
                  server_default="1"),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(f"ix_{TABLE}_upload", TABLE, ["upload_id"])
    op.create_index(f"ix_{TABLE}_sensor_level", TABLE, ["sensor_id", "level"])
    # One assessment per channel per capture. Re-running the engine replaces
    # the row rather than appending a second opinion.
    op.create_unique_constraint(
        f"uq_{TABLE}_upload_channel", TABLE, ["upload_id", "channel"])


def downgrade() -> None:
    op.drop_table(TABLE)
