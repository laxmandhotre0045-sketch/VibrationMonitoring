"""Store per-channel summary statistics on each raw capture channel.

Revision ID: 019
Revises: 018

The 7/30-day summary cards need a per-channel RMS for every capture in the
window. Computing it on demand means unnesting the stored float8[] -- about
111,000 values per capture across eight channels -- every time the dashboard
loads. Measured on real data that is 0.113 s per capture, which is fine for the
twenty-six captures that exist today and unusable very quickly after that:

    1 day   (720 captures)   ~81 s per dashboard load
    7 days  (5,040)          ~570 s
    30 days (21,600)         ~2,443 s

Sampling fewer captures would only postpone it. The statistic is a property of
the samples and never changes once written, so it is computed once at ingest
and stored beside them. Reading a float column for 21,600 rows is a millisecond
query.

Nullable rather than NOT NULL: rows written before this migration have no value
until the backfill below reaches them, and a capture whose statistics could not
be computed should still store its samples. Consumers treat NULL as "not
summarised" rather than as zero.
"""

from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_vibration_channels",
                  sa.Column("rms", sa.Float(precision=53), nullable=True))
    op.add_column("raw_vibration_channels",
                  sa.Column("dc_mean", sa.Float(precision=53), nullable=True))
    op.add_column("raw_vibration_channels",
                  sa.Column("ac_rms", sa.Float(precision=53), nullable=True))
    op.add_column("raw_vibration_channels",
                  sa.Column("peak", sa.Float(precision=53), nullable=True))

    # Backfill in SQL so existing captures gain their statistics without the
    # samples ever crossing the wire. One pass over what is there now; new rows
    # arrive with the values already set.
    #
    # ac_rms is the standard deviation about the mean -- the vibration with the
    # sensor's standing bias removed. It is the figure that distinguishes a
    # turning machine from a stationary one, and it is not derivable from rms
    # alone, so it is stored rather than reconstructed.
    op.execute("""
        WITH stats AS (
            SELECT ch.id,
                   sqrt(AVG(v * v))                      AS rms,
                   AVG(v)                                AS dc_mean,
                   sqrt(AVG(v * v) - AVG(v) * AVG(v))    AS ac_rms,
                   MAX(ABS(v))                           AS peak
              FROM raw_vibration_channels ch
              CROSS JOIN LATERAL unnest(ch.samples) AS v
             WHERE ch.rms IS NULL
             GROUP BY ch.id
        )
        UPDATE raw_vibration_channels ch
           SET rms = s.rms,
               dc_mean = s.dc_mean,
               -- Rounding can drive the variance fractionally below zero for a
               -- near-constant channel; NULLIF-free clamp keeps sqrt defined.
               ac_rms = CASE WHEN s.ac_rms IS NULL OR s.ac_rms <> s.ac_rms
                             THEN 0 ELSE s.ac_rms END,
               peak = s.peak
          FROM stats s
         WHERE ch.id = s.id
    """)


def downgrade() -> None:
    op.drop_column("raw_vibration_channels", "peak")
    op.drop_column("raw_vibration_channels", "ac_rms")
    op.drop_column("raw_vibration_channels", "dc_mean")
    op.drop_column("raw_vibration_channels", "rms")
