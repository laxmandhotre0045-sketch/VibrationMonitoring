"""How unusual each reading was, and against what — VIK-041.

Revision ID: 033
Revises: 032

One row per feature per channel per capture: the 0-100 score, the band it
falls in, and enough of the working to defend it later.

**Why the score is stored rather than computed on demand.** It is a function
of the baseline, and baselines change -- they roll, they are reset, they
gain a mode. A score recomputed next month against a different normal is a
different score, and a finding that pointed at 84 would quietly become 31
with nothing recording that it ever said 84. `baseline_version` and
`mode_id` travel with the row for the same reason.

**`is_scored` exists because "no baseline" is not "normal".** A feature the
platform has never learned a normal for cannot be scored, and the only
honest output is nothing. Writing 0 would say "this reading is perfectly
ordinary" about a reading nothing has ever been compared to -- which is the
mistake the whole platform is built to avoid, and the one that makes an
unmonitored machine look healthiest of all. A null score with `is_scored`
false says what is true.

**`contributions` is jsonb, not columns.** VIK-042 scores from a robust
z-score; VIK-043 adds an Isolation Forest and a PCA residual. Those are
different methods with different outputs, and the requirement asks for the
score to be explainable -- which means recording what each method said, not
just what they averaged to. A column per method would need a migration
every time one is added or dropped.

Nothing existing is altered.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None

TABLE = "feature_anomaly_scores"

#: The bands the requirement names, by their lower bound.
#: 0-20 normal, 21-40 slight, 41-60 watch, 61-75 abnormal,
#: 76-90 high priority, 91-100 critical.
BANDS = ("normal", "slight", "watch", "abnormal", "high", "critical")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("feature_code", sa.String(64), nullable=False),

        # --- the answer ---------------------------------------------------
        # Null when nothing could be scored. `is_scored` carries the meaning
        # so no reader has to interpret a null, and none of them can mistake
        # it for zero.
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("band", sa.String(16), nullable=True),
        sa.Column("is_scored", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),

        # How far out the reading was, in robust sigmas. Signed: a bearing
        # feature that collapses is as interesting as one that climbs, and
        # the direction is lost the moment it is folded into the score.
        sa.Column("z_score", sa.Float(), nullable=True),

        # --- what it was judged against -----------------------------------
        sa.Column("baseline_version", sa.Integer(), nullable=True),
        sa.Column("mode_id", postgresql.UUID(as_uuid=True), nullable=True),
        # The baseline's own worth, folded in: a score from a normal built
        # on thirteen captures is not the same claim as one from a hundred.
        sa.Column("confidence", sa.Float(), nullable=False,
                  server_default="0"),
        sa.Column("contributions", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("reason", sa.Text(), nullable=True),

        sa.Column("engine_version", sa.String(8), nullable=False,
                  server_default="1"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # One score per feature per channel per capture. Re-scoring is a
    # corrected opinion, not a second one -- the same rule the quality
    # engine and the mode detector follow.
    op.create_unique_constraint(
        f"uq_{TABLE}_scope", TABLE,
        ["upload_id", "channel", "feature_code"])
    op.create_index(f"ix_{TABLE}_lookup", TABLE,
                    ["sensor_id", "channel", "feature_code"])
    # The queries that matter are "what is worst on this machine" and "what
    # has this feature been doing", and both filter to scored rows.
    op.create_index(f"ix_{TABLE}_worst", TABLE,
                    ["sensor_id", "score"],
                    postgresql_where=sa.text("is_scored"))

    op.create_check_constraint(
        f"ck_{TABLE}_score_range", TABLE,
        "score IS NULL OR (score >= 0 AND score <= 100)")
    op.create_check_constraint(
        f"ck_{TABLE}_confidence_range", TABLE,
        "confidence >= 0 AND confidence <= 1")
    op.create_check_constraint(
        f"ck_{TABLE}_band", TABLE,
        "band IS NULL OR band IN ("
        + ", ".join(f"'{b}'" for b in BANDS) + ")")
    # A scored row has a score and a band; an unscored row has neither.
    # Anything else is a state a reader would resolve differently each time,
    # and the one that matters is an unscored row carrying a zero.
    op.create_check_constraint(
        f"ck_{TABLE}_scored_is_complete", TABLE,
        "(is_scored AND score IS NOT NULL AND band IS NOT NULL) "
        "OR (NOT is_scored AND score IS NULL AND band IS NULL)")


def downgrade() -> None:
    op.drop_table(TABLE)
