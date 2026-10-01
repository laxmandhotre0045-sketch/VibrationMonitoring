"""A finding: what the machine is probably doing, and why — VIK-057/058.

Revision ID: 037
Revises: 036

This is the AI card as a table. Everything before it measured, scored and
alarmed; a finding is the first thing that names a fault.

**A finding evolves, it is not re-created.** VIK-058 is explicit and it is
an acceptance criterion: re-loading the same capture must not produce a
second finding. So the identity of a finding is the machine, the channel
and the fault -- not the capture. A capture updates the finding it belongs
to.

That is the whole reason `first_detected_at` can mean anything. A row per
capture would restate the fault every two minutes, and "this has been
developing for nine days" would be unanswerable from a table that only ever
knew about the last two minutes.

**The evidence is stored, not the conclusion alone.** `evidence` holds the
orders and amplitudes the rules fired on; `contradicting_evidence` holds
what argued against. A finding nobody can interrogate is a finding nobody
should act on, and "1x dominant, no axial component, 2x absent" is what
makes an analyst able to agree or overrule.

**`resolution` records whether the spectrum could see the fault at all.**
On this gateway it cannot: a 0.278 s record resolves 3.60 Hz per bin and
the outer-race frequency sits 1.58 Hz from the third shaft harmonic. So a
finding carries the instrument's own limits beside its conclusion, and the
absence of a bearing fault on a record that could not have shown one is
recorded as exactly that rather than as a clean bill of health.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None

TABLE = "fault_findings"

#: Set by VIK-054. Ordered, because a stage only rises under the persistence
#: conditions and comparisons between them have to mean something.
STAGES = ("normal", "watch", "early_fault_suspected", "developing",
          "severe", "critical")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.Integer(), nullable=False),
        # The rule that fired, e.g. 'bearing_outer_race'. With sensor and
        # channel this is the finding's identity -- see the unique
        # constraint below, which is what VIK-058 turns on.
        sa.Column("fault_key", sa.String(64), nullable=False),
        sa.Column("fault_name", sa.String(120), nullable=False),

        # --- what the engine concluded -----------------------------------
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False,
                  server_default="watch"),
        sa.Column("severity", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("mechanism", sa.Text(), nullable=True),

        # --- why, in a form somebody can argue with -----------------------
        sa.Column("evidence", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("contradicting_evidence", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("confirming_checks", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        # What the spectrum could and could not separate when this was
        # decided. A finding's absence is only meaningful if the instrument
        # could have shown it.
        sa.Column("resolution", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        # Which rule families were never in the running because the machine
        # record does not describe them.
        sa.Column("context_completeness", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),

        # --- how it has moved --------------------------------------------
        # The whole point of a finding evolving rather than repeating.
        sa.Column("first_detected_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("times_seen", sa.Integer(), nullable=False,
                  server_default="1"),
        sa.Column("peak_score", sa.Float(), nullable=True),
        sa.Column("peak_stage", sa.String(32), nullable=True),
        # Null until it stops being found. Kept rather than deleted: a fault
        # that appeared for a fortnight and went away is a maintenance
        # record, and deleting it loses the only trace that it happened.
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("first_upload_id", postgresql.UUID(as_uuid=True),
                  nullable=True),
        sa.Column("last_upload_id", postgresql.UUID(as_uuid=True),
                  nullable=True),
        sa.Column("mode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(120), nullable=True),
        sa.Column("analyst_verdict", sa.String(16), nullable=True),
        sa.Column("analyst_note", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.String(8), nullable=False,
                  server_default="1"),
    )

    # VIK-058, enforced rather than intended. One finding per fault per
    # channel per machine; a capture updates it.
    op.create_unique_constraint(
        f"uq_{TABLE}_identity", TABLE, ["sensor_id", "channel", "fault_key"])
    op.create_index(f"ix_{TABLE}_open", TABLE, ["sensor_id", "severity"],
                    postgresql_where=sa.text("resolved_at IS NULL"))
    op.create_index(f"ix_{TABLE}_equipment", TABLE,
                    ["equipment_id", "stage"])

    op.create_check_constraint(
        f"ck_{TABLE}_stage", TABLE,
        "stage IN (" + ", ".join(f"'{s}'" for s in STAGES) + ")")
    op.create_check_constraint(
        f"ck_{TABLE}_peak_stage", TABLE,
        "peak_stage IS NULL OR peak_stage IN ("
        + ", ".join(f"'{s}'" for s in STAGES) + ")")
    op.create_check_constraint(
        f"ck_{TABLE}_severity", TABLE, "severity >= 0 AND severity <= 5")
    op.create_check_constraint(
        f"ck_{TABLE}_score_range", TABLE, "score >= 0 AND score <= 1")
    op.create_check_constraint(
        f"ck_{TABLE}_confidence_range", TABLE,
        "confidence >= 0 AND confidence <= 1")
    # An analyst agreeing or disagreeing is the feedback loop's raw
    # material, and a free-text verdict would be unusable for it.
    op.create_check_constraint(
        f"ck_{TABLE}_verdict", TABLE,
        "analyst_verdict IS NULL OR analyst_verdict IN "
        "('confirmed', 'rejected', 'unsure')")
    # A finding cannot have been seen before it was first detected.
    op.create_check_constraint(
        f"ck_{TABLE}_seen_after_detected", TABLE,
        "last_seen_at >= first_detected_at")
    op.create_check_constraint(
        f"ck_{TABLE}_times_seen", TABLE, "times_seen >= 1")


def downgrade() -> None:
    op.drop_table(TABLE)
