"""Store per-channel summary statistics on each raw capture channel.

Revision ID: 021a
Revises: 021

Renumbered from 019 after a collision: Laxman's bearing-catalogue migration
took 019 and 020 on the same base while this one was already applied locally.
Alembic reported "Revision 019 is present more than once" and refused to
resolve a single head. This now sits after his chain.

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

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # IF NOT EXISTS because this migration was applied under its old number
    # before the renumbering, so the columns are already present on any
    # database that ran it as 019. A plain add_column would fail there and
    # block the whole upgrade.
    for column in ("rms", "dc_mean", "ac_rms", "peak"):
        op.execute(
            f"ALTER TABLE raw_vibration_channels "
            f"ADD COLUMN IF NOT EXISTS {column} double precision"
        )

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
    for column in ("peak", "ac_rms", "dc_mean", "rms"):
        op.execute(
            f"ALTER TABLE raw_vibration_channels DROP COLUMN IF EXISTS {column}"
        )
