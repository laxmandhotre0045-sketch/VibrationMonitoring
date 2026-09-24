"""What normal looks like for one feature on one channel — VIK-024.

Revision ID: 026
Revises: 025

The ticket numbers this 022; that was taken by signal_unit before this
branch caught up, so it is 026 here. Its content is unchanged.

**Robust statistics, not mean and standard deviation.** A baseline is built
from captures nobody has inspected, so it will contain bad ones -- a capture
taken during a speed change, one with a loose cable, one where somebody was
hammering nearby. A mean moves with every one of those; a median does not.
The columns are chosen so that the engine cannot quietly fall back to the
fragile pair: there is nowhere to put a mean.

`mad` is the median absolute deviation and `robust_sigma` is that scaled by
1.4826, which makes it comparable to a standard deviation for data that
happens to be normal -- so a threshold expressed in sigma keeps its usual
meaning without inheriting a standard deviation's sensitivity to outliers.

`mode_id` stays nullable until VIK-040 teaches the platform that a machine
running at two loads has two normals. Until then every row is the
all-conditions baseline, and a null says so rather than pretending there is
only one mode.

Additive: `sensor_baselines` keeps its own job as the known-good reference
capture. This is the learned normal beside it, not a replacement.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None

TABLE = "feature_baseline_stats"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),

        # --- what this row is the normal for -------------------------------
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("feature_code", sa.String(64), nullable=False),
        # Null until VIK-040. A machine running at two loads has two normals,
        # and a null says "all conditions" rather than implying there is only
        # one.
        sa.Column("mode_id", postgresql.UUID(as_uuid=True), nullable=True),

        # --- the robust statistics ----------------------------------------
        sa.Column("median", sa.Float(), nullable=False),
        sa.Column("mad", sa.Float(), nullable=False),
        # MAD x 1.4826: comparable to a standard deviation on normal data,
        # without a standard deviation's sensitivity to one bad capture.
        sa.Column("robust_sigma", sa.Float(), nullable=False),
        sa.Column("p05", sa.Float(), nullable=False),
        sa.Column("p50", sa.Float(), nullable=False),
        sa.Column("p95", sa.Float(), nullable=False),
        # Exponentially weighted, so a slow drift is visible next to the
        # median without the median chasing it.
        sa.Column("ewma", sa.Float(), nullable=True),

        # --- what it was built from ---------------------------------------
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        # A finding has to be traceable to the baseline that produced it, and
        # a reset starts a new version rather than editing the old one
        # (VIK-026). Without this, a changed baseline silently rewrites the
        # meaning of every finding that came before it.
        sa.Column("baseline_version", sa.Integer(), nullable=False,
                  server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.text("true")),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_index(f"ix_{TABLE}_lookup", TABLE,
                    ["sensor_id", "channel", "feature_code", "is_active"])
    op.create_index(f"ix_{TABLE}_version", TABLE, ["sensor_id", "baseline_version"])

    # One active row per feature per mode per version. Two active baselines
    # for the same thing is not a richer answer, it is an ambiguous one.
    op.create_unique_constraint(
        f"uq_{TABLE}_scope", TABLE,
        ["sensor_id", "channel", "feature_code", "mode_id", "baseline_version"])

    op.create_check_constraint(
        f"ck_{TABLE}_spread_not_negative", TABLE,
        "mad >= 0 AND robust_sigma >= 0")
    # A baseline built from one capture is not a baseline. The engine refuses
    # well above this; the constraint is the floor below which a row is
    # meaningless whatever wrote it.
    op.create_check_constraint(
        f"ck_{TABLE}_has_samples", TABLE, "sample_count >= 2")
    op.create_check_constraint(
        f"ck_{TABLE}_window_ordered", TABLE, "window_end >= window_start")


def downgrade() -> None:
    op.drop_table(TABLE)
