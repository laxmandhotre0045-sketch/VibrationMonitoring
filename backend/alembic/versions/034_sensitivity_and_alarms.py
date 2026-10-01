"""Sensitivity settings, and alarms that survive a restart — VIK-044/046.

Revision ID: 034
Revises: 033

Two tables.

`ai_sensitivity_settings` is where a machine's sensitivity profile lives.
The requirement has asked for four modes since the first draft and they have
been a label on a settings page; this is what makes choosing one change
anything. One row per machine, because sensitivity is a judgement about how
much that machine matters -- a spare pump and the one feeding the furnace
deserve different answers, and a platform-wide setting cannot express that.

The expert overrides are a jsonb column rather than four nullable columns.
The requirement lists six things Expert mode should let somebody configure
and this release honours four of them; the remaining two are mode-separation
logic and frequency-band rules, which are not numbers and are not settled.
A column each would mean a migration per idea.

`feature_alarm_state` is one row per feature per channel per sensor: whether
it is ringing now, how long the run is, and when it started.

**Why the state is stored rather than derived.** The run could be recomputed
from the score history on every read, and for the ringing decision it is --
this table does not decide anything. What it holds is the part that cannot
be recomputed: `first_alarmed_at`, the moment a fault started. Recomputing
that from scores gives the moment of the *current* run, so a fault that
briefly dipped below the line and came back would have its history reset,
and "this has been getting worse since Tuesday" would quietly become "since
this morning" -- which is the single most useful sentence the platform can
say to a maintenance engineer.

`acknowledged_at` is here for the same reason. An alarm somebody has already
seen and an alarm nobody has seen are different states, and the difference
lives with the alarm rather than in a notification log.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None

SETTINGS = "ai_sensitivity_settings"
ALARMS = "feature_alarm_state"

PROFILES = ("conservative", "balanced", "early_warning", "expert")


def upgrade() -> None:
    op.create_table(
        SETTINGS,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("equipment_id", postgresql.UUID(as_uuid=True),
                  nullable=False),
        sa.Column("profile", sa.String(20), nullable=False,
                  server_default="balanced"),
        # Only read when profile = 'expert'. Kept when the profile is
        # switched away and back, so somebody who tries Balanced for a week
        # does not lose the numbers they tuned.
        sa.Column("expert_overrides", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        f"uq_{SETTINGS}_equipment", SETTINGS, ["equipment_id"])
    op.create_check_constraint(
        f"ck_{SETTINGS}_profile", SETTINGS,
        "profile IN (" + ", ".join(f"'{p}'" for p in PROFILES) + ")")

    op.create_table(
        ALARMS,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("feature_code", sa.String(64), nullable=False),

        sa.Column("alarming", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("run_length", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("required", sa.Integer(), nullable=False,
                  server_default="0"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("band", sa.String(16), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        # 'not_persistent' or 'low_confidence' when past the line but held
        # back. Null when it is either ringing or simply not past the line --
        # those two are told apart by `alarming`.
        sa.Column("held_back", sa.String(24), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),

        # When this feature *first* started ringing, kept across a dip. The
        # one fact that cannot be recomputed from the scores.
        sa.Column("first_alarmed_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("last_alarmed_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True),
                  nullable=True),
        sa.Column("acknowledged_by", sa.String(120), nullable=True),

        sa.Column("last_upload_id", postgresql.UUID(as_uuid=True),
                  nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        f"uq_{ALARMS}_scope", ALARMS, ["sensor_id", "channel", "feature_code"])
    # The query that matters: what is ringing on this machine right now.
    op.create_index(f"ix_{ALARMS}_active", ALARMS, ["sensor_id", "score"],
                    postgresql_where=sa.text("alarming"))
    op.create_check_constraint(
        f"ck_{ALARMS}_held_back", ALARMS,
        "held_back IS NULL OR held_back IN ('not_persistent', 'low_confidence')")
    # Ringing and held back are opposite states; a row claiming both is one
    # a reader would resolve differently each time.
    op.create_check_constraint(
        f"ck_{ALARMS}_not_both", ALARMS,
        "NOT (alarming AND held_back IS NOT NULL)")
    # A ringing alarm knows when it started. Without this, "how long has
    # this been going on" has no answer on exactly the rows it is asked of.
    op.create_check_constraint(
        f"ck_{ALARMS}_alarming_has_start", ALARMS,
        "(NOT alarming) OR (first_alarmed_at IS NOT NULL)")


def downgrade() -> None:
    op.drop_table(ALARMS)
    op.drop_table(SETTINGS)
