"""Priority queue and the analyst feedback loop — Phase 4, sections 15/16.

Revision ID: 041
Revises: 040

Phase 3 can name a fault on one machine. Neither of the two things a
maintenance team actually does with that has existed until now: deciding
which machine to walk to first, and telling the platform whether it was
right.

**Section 15 wants eleven inputs and two of them were not recordable.**
Safety impact and production impact are not derivable from vibration --
whether a pump failing hurts somebody or stops a line is a fact about the
plant that a human enters once. They go on the equipment record, and they
are nullable: a machine nobody has classified must not be silently treated
as safe and unimportant, so the priority engine reports them as unknown
rather than defaulting them to "low".

**Section 16 wants eleven kinds of feedback and three existed.**
`analyst_verdict` allowed confirmed / rejected / unsure, which cannot
express "right fault, wrong severity", "it was the sensor", or "this is
normal for this machine, stop telling me". Those are different corrections
with different consequences and collapsing them loses exactly the
information the loop exists to collect.

**Feedback is a log, not a column.** An analyst can be wrong, can change
their mind, and a second analyst can disagree with the first. A single
mutable verdict field cannot represent any of that, and it silently
destroys the history that section 16.2 says the feedback is *for*. So
every submission is a row, the finding carries the latest as a convenience,
and nothing is ever overwritten.

**Suppression is time-boxed and never silent.** "Ignore for this machine"
is the one feedback option that can hide a real fault, so it expires, it
records who asked for it and why, and a suppressed finding still exists and
still escalates if it gets materially worse. A permanent, invisible mute is
how a monitoring system ends up not monitoring.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None

FINDINGS = "fault_findings"
FEEDBACK = "analyst_feedback"
EQUIPMENT = "equipment_masters"

#: Section 16.1's list, verbatim, as stored values.
VERDICTS = (
    "correct_detection",
    "false_alarm",
    "wrong_fault_type",
    "severity_too_high",
    "severity_too_low",
    "maintenance_confirmed",
    "fault_not_found",
    "sensor_issue",
    "process_related",
    "ignore_for_machine",
    "new_fault_label",
)

#: Where a finding sits in the triage workflow (section 15.2's "Status").
TRIAGE = ("new", "assigned", "investigating", "awaiting_shutdown",
          "resolved", "closed")

#: Section 15.1's safety and production impact. Ordered, and deliberately
#: without a default -- see the module docstring.
IMPACT = ("none", "low", "medium", "high", "severe")


def upgrade() -> None:
    # ---------------------------------------------- section 15.1 inputs --
    for column in ("safety_impact", "production_impact"):
        op.add_column(EQUIPMENT, sa.Column(column, sa.String(16),
                                           nullable=True))
        op.create_check_constraint(
            f"ck_{EQUIPMENT}_{column}", EQUIPMENT,
            f"{column} IS NULL OR {column} IN ("
            + ", ".join(f"'{i}'" for i in IMPACT) + ")")

    # --------------------------------------------- section 15.2 outputs --
    op.add_column(FINDINGS, sa.Column("assigned_to", sa.String(120),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("assigned_at",
                                      sa.DateTime(timezone=True),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column(
        "triage_status", sa.String(24), nullable=False,
        server_default="new"))
    op.create_check_constraint(
        f"ck_{FINDINGS}_triage_status", FINDINGS,
        "triage_status IN (" + ", ".join(f"'{t}'" for t in TRIAGE) + ")")
    # A finding cannot be assigned to nobody and simultaneously claim
    # somebody is working on it.
    op.create_check_constraint(
        f"ck_{FINDINGS}_assigned_has_owner", FINDINGS,
        "triage_status NOT IN ('assigned', 'investigating') "
        "OR assigned_to IS NOT NULL")

    # The computed priority, stored so the queue can be ordered in SQL and
    # so a rank can be compared with what it was yesterday.
    op.add_column(FINDINGS, sa.Column("priority_score", sa.Float(),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("priority_band", sa.String(16),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("priority_reason", sa.Text(),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("priority_inputs", postgresql.JSONB(),
                                      nullable=False,
                                      server_default=sa.text("'{}'::jsonb")))

    # ----------------------------------------------- suppression -------
    # Time-boxed, attributed, and never silent.
    op.add_column(FINDINGS, sa.Column("suppressed_until",
                                      sa.DateTime(timezone=True),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("suppressed_by", sa.String(120),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("suppressed_reason", sa.Text(),
                                      nullable=True))
    # The score at which the mute was granted. A suppressed finding that
    # gets materially worse than this comes back on its own -- otherwise
    # "ignore for this machine" is how a developing fault disappears.
    op.add_column(FINDINGS, sa.Column("suppressed_at_score", sa.Float(),
                                      nullable=True))
    op.create_check_constraint(
        f"ck_{FINDINGS}_suppression_is_attributed", FINDINGS,
        "suppressed_until IS NULL OR "
        "(suppressed_by IS NOT NULL AND suppressed_reason IS NOT NULL)")

    # The latest verdict, as a convenience for the queue. The log below is
    # the record; this is a cache of its most recent row.
    op.add_column(FINDINGS, sa.Column("latest_feedback", sa.String(32),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("latest_feedback_at",
                                      sa.DateTime(timezone=True),
                                      nullable=True))
    op.create_check_constraint(
        f"ck_{FINDINGS}_latest_feedback", FINDINGS,
        "latest_feedback IS NULL OR latest_feedback IN ("
        + ", ".join(f"'{v}'" for v in VERDICTS) + ")")

    # ------------------------------------------- section 16: the log ----
    op.create_table(
        FEEDBACK,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Kept by identity rather than by foreign key to the finding row:
        # a finding can be resolved and re-opened, and the feedback given
        # about it the first time is still evidence the second time.
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True),
                  nullable=True),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("fault_key", sa.String(64), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("verdict", sa.String(32), nullable=False),
        # For `wrong_fault_type` and `new_fault_label`: what it actually
        # was. This is the single most valuable field in the table -- a
        # correction that says what the right answer is can retrain a rule;
        # one that only says "wrong" cannot.
        sa.Column("corrected_fault_key", sa.String(64), nullable=True),
        sa.Column("corrected_fault_label", sa.String(120), nullable=True),
        sa.Column("corrected_severity", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),

        # What the platform thought at the moment it was corrected. Without
        # this the feedback cannot be used to improve anything: "the analyst
        # said false alarm" is useless without knowing what was claimed.
        sa.Column("engine_stage", sa.String(32), nullable=True),
        sa.Column("engine_severity", sa.Integer(), nullable=True),
        sa.Column("engine_score", sa.Float(), nullable=True),
        sa.Column("engine_confidence", sa.Float(), nullable=True),
        sa.Column("engine_version", sa.String(8), nullable=True),
        sa.Column("data_quality", sa.String(16), nullable=True),

        sa.Column("analyst", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # Never updated, never deleted. A retraction is another row.
        sa.Column("retracts_id", postgresql.UUID(as_uuid=True),
                  nullable=True),
    )
    op.create_check_constraint(
        f"ck_{FEEDBACK}_verdict", FEEDBACK,
        "verdict IN (" + ", ".join(f"'{v}'" for v in VERDICTS) + ")")
    # A correction that does not say what the right answer was cannot be
    # learned from, so the two verdicts that exist to carry one must.
    op.create_check_constraint(
        f"ck_{FEEDBACK}_correction_names_the_fault", FEEDBACK,
        "verdict NOT IN ('wrong_fault_type', 'new_fault_label') "
        "OR corrected_fault_key IS NOT NULL "
        "OR corrected_fault_label IS NOT NULL")
    op.create_check_constraint(
        f"ck_{FEEDBACK}_severity_range", FEEDBACK,
        "corrected_severity IS NULL OR "
        "(corrected_severity >= 0 AND corrected_severity <= 5)")
    op.create_check_constraint(
        f"ck_{FEEDBACK}_channel", FEEDBACK, "channel >= 0")

    op.create_index(f"ix_{FEEDBACK}_sensor", FEEDBACK,
                    ["sensor_id", "channel", "fault_key"])
    op.create_index(f"ix_{FEEDBACK}_fault", FEEDBACK,
                    ["fault_key", "verdict"])
    op.create_index(f"ix_{FEEDBACK}_when", FEEDBACK, ["created_at"])


def downgrade() -> None:
    op.drop_table(FEEDBACK)
    for name in ("latest_feedback_at", "latest_feedback",
                 "suppressed_at_score", "suppressed_reason", "suppressed_by",
                 "suppressed_until", "priority_inputs", "priority_reason",
                 "priority_band", "priority_score", "triage_status",
                 "assigned_at", "assigned_to"):
        op.drop_column(FINDINGS, name)
    for column in ("production_impact", "safety_impact"):
        op.drop_column(EQUIPMENT, column)
