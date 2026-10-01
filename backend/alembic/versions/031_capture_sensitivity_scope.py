"""A baseline belongs to the converter setting it was learned at.

Revision ID: 031
Revises: 030

Migration 027 scoped a baseline to its sample rate and record length,
because half the features move when those change. The converter's
sensitivity is the third setting in that group and was missed, which did
not matter while it was the same on every channel of every capture. It is
about to stop being the same: the point of making it configurable is that a
quiet machine can be switched from 100 mV/g to 500 so its vibration is
measured in forty-seven steps of the converter instead of one and a half.

What changes when it does. At 100 mV/g the converter covers +/-50 g in
steps of 0.0015 g; at 500 it covers +/-10 g in steps of 0.0003 g. Anything
counting distinct values, measuring how spiky a signal is, or comparing
against the noise floor moves -- kurtosis and crest factor most of all,
because a signal resolved in one and a half steps has its shape defined by
rounding, and the same signal in forty-seven steps does not.

So a capture records the step it was actually measured at, and a baseline
records the step its captures shared. A capture taken at a different one is
not compared against it. Without this, switching a channel to 500 mV/g
would silently make every baseline on it wrong, and the system would go on
comparing as though nothing had happened -- reporting the settings change
as a fault.

The step rather than the declared sensitivity, deliberately: the step is
measured from the samples and is therefore what the device really did,
while the declaration is what someone typed. Those disagree on this gateway
today.

Nullable on both tables. Rows written before this migration were measured
at some step but nothing recorded which, and an unknown step compares
against nothing -- which is the safe reading, and the same choice 027 made.
"""

from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None

ASSESSMENTS = "data_quality_assessments"
BASELINES = "feature_baseline_stats"


def upgrade() -> None:
    # What this capture's channel was actually quantised in, in g.
    op.add_column(ASSESSMENTS, sa.Column(
        "quantisation_step_g", sa.Float(), nullable=True))

    # What every capture behind this baseline was quantised in.
    op.add_column(BASELINES, sa.Column(
        "acquisition_step_g", sa.Float(), nullable=True))
    # Captures dropped from the window because they were taken at a
    # different one, so the count is visible rather than inferred.
    op.add_column(BASELINES, sa.Column(
        "other_step_count", sa.Integer(), nullable=False, server_default="0"))

    op.create_index(f"ix_{BASELINES}_step", BASELINES,
                    ["sensor_id", "acquisition_step_g"])


def downgrade() -> None:
    op.drop_index(f"ix_{BASELINES}_step", table_name=BASELINES)
    op.drop_column(BASELINES, "other_step_count")
    op.drop_column(BASELINES, "acquisition_step_g")
    op.drop_column(ASSESSMENTS, "quantisation_step_g")
