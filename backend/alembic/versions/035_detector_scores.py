"""What the joint detectors made of each channel — VIK-043.

Revision ID: 035
Revises: 034

`feature_anomaly_scores` holds one row per feature, because that is the
shape of the question VIK-042 asks: how unusual is this reading against its
own normal. The two detectors in VIK-043 ask a different question -- how
unusual is this *combination* -- and its answer belongs to the channel, not
to any feature on it.

Storing them in the feature table under a reserved feature code was the
cheaper option and the wrong one. Every query that groups by feature, every
band distribution, every "worst feature on this machine" would have to learn
to exclude two codes that are not features, and one that forgot would report
a detector as though it were a measurement.

`drivers` holds the features that contributed most to a PCA residual. It is
jsonb because Isolation Forest has none -- it does not decompose -- and a
column structure that assumed every method could name its drivers would be
a structure only one method fits.

Unscored rows are written, as everywhere else here: a detector that had too
little history to run is a fact worth keeping, and its absence would be
indistinguishable from never having been tried.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None

TABLE = "capture_detector_scores"
METHODS = ("isolation_forest", "pca_residual")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),

        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("is_scored", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        # The detector's own output. The 0-100 mapping is a presentation
        # choice; this is the evidence behind it.
        sa.Column("raw", sa.Float(), nullable=True),
        sa.Column("drivers", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("reason", sa.Text(), nullable=True),

        sa.Column("training_samples", sa.Integer(), nullable=True),
        sa.Column("mode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("engine_version", sa.String(8), nullable=False,
                  server_default="1"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    op.create_unique_constraint(
        f"uq_{TABLE}_scope", TABLE, ["upload_id", "channel", "method"])
    op.create_index(f"ix_{TABLE}_lookup", TABLE,
                    ["sensor_id", "channel", "method"])
    op.create_check_constraint(
        f"ck_{TABLE}_method", TABLE,
        "method IN (" + ", ".join(f"'{m}'" for m in METHODS) + ")")
    op.create_check_constraint(
        f"ck_{TABLE}_score_range", TABLE,
        "score IS NULL OR (score >= 0 AND score <= 100)")
    # Scored means there is a score; unscored means there is not. A row
    # carrying a zero while claiming to be unscored is the state this whole
    # platform is built to refuse.
    op.create_check_constraint(
        f"ck_{TABLE}_scored_is_complete", TABLE,
        "(is_scored AND score IS NOT NULL) OR (NOT is_scored AND score IS NULL)")


def downgrade() -> None:
    op.drop_table(TABLE)
