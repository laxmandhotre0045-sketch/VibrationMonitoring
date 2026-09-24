"""A baseline belongs to the acquisition shape it was built from — VIK-025 fix.

Revision ID: 027
Revises: 026

Half the features this platform measures depend on how the capture was
taken, not only on what the machine was doing. Measured on one identical
synthetic signal, sampled the two ways this gateway has actually been
configured -- 0.278 s at 50 kSPS, and 0.8 s at 25 kSPS:

    zero_crossing_rate   3939 -> 2020   (-49%)
    spectral_centroid    1962 -> 1047   (-47%)
    spectral_spread      5181 -> 2619   (-49%)
    bpfo_band_energy     52.4 -> 37.5   (-29%)
    envelope_kurtosis     229 -> 171    (-25%)

Fourteen of forty-two features move more than a quarter. The bandwidth
halved, so anything measured across the whole spectrum halved with it, and
anything counted over the record moved with the record length.

Against the baseline learned from the old shape, the new shape's
zero-crossing rate reads seven sigma out -- a clear anomaly caused entirely
by somebody changing a setting on the sensor.

So a baseline records the shape it was built from, and a capture taken under
a different one is not compared against it. The same idea as the operating
mode in VIK-040, one layer down: a machine at two loads has two normals, and
a sensor at two configurations has two again.

`sample_count` already means "how many captures went into this baseline" and
keeps that meaning -- a CHECK constraint and the engine both rely on it. The
new columns are named for what they describe so the two cannot be confused.
"""

from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None

TABLE = "feature_baseline_stats"


def upgrade() -> None:
    # Nullable, because rows written before this migration were built from a
    # single shape but nothing recorded which one. Inventing a value would be
    # worse than admitting it is unknown, and an unknown shape compares
    # against nothing -- which is the safe reading.
    op.add_column(TABLE, sa.Column(
        "acquisition_sample_rate_hz", sa.Float(), nullable=True))
    op.add_column(TABLE, sa.Column(
        "acquisition_sample_count", sa.Integer(), nullable=True))

    op.create_index(
        f"ix_{TABLE}_shape", TABLE,
        ["sensor_id", "acquisition_sample_rate_hz", "acquisition_sample_count"])


def downgrade() -> None:
    op.drop_index(f"ix_{TABLE}_shape", table_name=TABLE)
    op.drop_column(TABLE, "acquisition_sample_count")
    op.drop_column(TABLE, "acquisition_sample_rate_hz")
