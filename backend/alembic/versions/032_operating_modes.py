"""What the machine was doing when the capture was taken — VIK-038.

Revision ID: 032
Revises: 031

One machine has more than one normal. A pump at low load and the same pump
at high load produce different vibration for the same healthy condition, and
a baseline built across both is the average of neither: every capture then
sits some distance from a normal that describes no operating state the
machine has ever been in. The requirement is explicit that baseline and
anomaly detection must be mode-wise.

Two tables, because they answer two different questions.

`operating_modes` is what modes this machine has. A row is a named band --
"High load", 1450 to 1500 rpm -- and it is either configured by someone who
knows the machine or discovered from its history. `source` says which,
because a band somebody typed and a band a clustering pass proposed deserve
different trust, and a later refinement must not silently overwrite the
former with the latter.

`capture_operating_modes` is which of them a given capture was in. One row
per capture, because the mode is a property of the machine at that moment
and not of any transducer bolted to it.

**Unknown is a mode.** `is_unknown` exists and the label is nullable,
because the ticket is explicit: a capture with no clear mode is labelled
unknown, never forced into the nearest one. Forcing it is worse than
refusing -- the capture then joins a baseline it does not belong to and
widens that mode's spread, which is how a real fault comes to look ordinary.
The same rule as "no baseline is not normal", one layer down.

`confidence` is stored rather than recomputed for the same reason the
quality verdict is: a finding recorded against a mode has to stay
explainable after the bands are retuned.

Nothing is dropped and nothing existing is altered. `feature_baseline_stats`
already carries a nullable `mode_id` from migration 026, waiting for this.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None

MODES = "operating_modes"
CAPTURE_MODES = "capture_operating_modes"

#: The vocabulary the requirement names. Stored as text with a check rather
#: than a database enum: adding a mode should be a migration, not a type
#: rewrite, and the check still stops a typo becoming a silent new mode.
MODE_LABELS = (
    "off", "idle", "startup", "shutdown", "normal_running",
    "low_load", "medium_load", "high_load", "variable_speed",
    "unstable", "unknown",
)


def upgrade() -> None:
    op.create_table(
        MODES,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(32), nullable=False),

        # The band that defines the mode. Null at either end means open --
        # "anything above 1450 rpm" is a legitimate band and must not be
        # forced to invent an upper bound nobody knows.
        sa.Column("rpm_min", sa.Float(), nullable=True),
        sa.Column("rpm_max", sa.Float(), nullable=True),
        sa.Column("load_min", sa.Float(), nullable=True),
        sa.Column("load_max", sa.Float(), nullable=True),

        # 'configured' by a person, or 'discovered' from history. A
        # discovered band must never overwrite a configured one.
        sa.Column("source", sa.String(16), nullable=False,
                  server_default="configured"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(f"ix_{MODES}_equipment", MODES, ["equipment_id", "is_active"])
    op.create_unique_constraint(
        f"uq_{MODES}_equipment_label", MODES, ["equipment_id", "label"])
    op.create_check_constraint(
        f"ck_{MODES}_label", MODES,
        "label IN (" + ", ".join(f"'{m}'" for m in MODE_LABELS) + ")")
    op.create_check_constraint(
        f"ck_{MODES}_source", MODES,
        "source IN ('configured', 'discovered')")
    # A band that ends before it starts matches nothing and would silently
    # send every capture to unknown.
    op.create_check_constraint(
        f"ck_{MODES}_rpm_ordered", MODES,
        "rpm_min IS NULL OR rpm_max IS NULL OR rpm_max >= rpm_min")
    op.create_check_constraint(
        f"ck_{MODES}_load_ordered", MODES,
        "load_min IS NULL OR load_max IS NULL OR load_max >= load_min")

    op.create_table(
        CAPTURE_MODES,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),

        # Null when nothing matched. `is_unknown` carries the meaning so a
        # reader never has to interpret a null, and a mode row can be
        # deleted without silently reclassifying every capture that used it.
        sa.Column("mode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("label", sa.String(32), nullable=False,
                  server_default="unknown"),
        sa.Column("is_unknown", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("confidence", sa.Float(), nullable=False,
                  server_default="0"),

        # What the decision was made from, kept so it can be defended.
        sa.Column("shaft_hz", sa.Float(), nullable=True),
        sa.Column("shaft_source", sa.String(32), nullable=True),
        sa.Column("overall_level", sa.Float(), nullable=True),
        sa.Column("stability", sa.String(16), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("engine_version", sa.String(8), nullable=False,
                  server_default="1"),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # One verdict per capture. Re-running the detector is a corrected
    # opinion, not a second one -- the same rule the quality engine follows.
    op.create_unique_constraint(
        f"uq_{CAPTURE_MODES}_upload", CAPTURE_MODES, ["upload_id"])
    op.create_index(f"ix_{CAPTURE_MODES}_lookup", CAPTURE_MODES,
                    ["sensor_id", "label"])
    op.create_check_constraint(
        f"ck_{CAPTURE_MODES}_label", CAPTURE_MODES,
        "label IN (" + ", ".join(f"'{m}'" for m in MODE_LABELS) + ")")
    op.create_check_constraint(
        f"ck_{CAPTURE_MODES}_confidence", CAPTURE_MODES,
        "confidence >= 0 AND confidence <= 1")
    op.create_check_constraint(
        f"ck_{CAPTURE_MODES}_stability", CAPTURE_MODES,
        "stability IS NULL OR stability IN ('steady', 'variable', 'unstable')")
    # Unknown and a named mode are mutually exclusive states, and a row that
    # claims both is one a reader would resolve differently each time.
    op.create_check_constraint(
        f"ck_{CAPTURE_MODES}_unknown_has_no_mode", CAPTURE_MODES,
        "(is_unknown AND mode_id IS NULL AND label = 'unknown') "
        "OR (NOT is_unknown AND label <> 'unknown')")


def downgrade() -> None:
    op.drop_table(CAPTURE_MODES)
    op.drop_table(MODES)
