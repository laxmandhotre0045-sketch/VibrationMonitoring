"""A baseline has a life, and it is recorded — VIK-026, VIK-027.

Revision ID: 028
Revises: 027

VIK-025 learns what normal looks like. It does not say when that normal
starts applying, when it stops moving, or which one a finding was judged
against. Those are four different questions and the ticket names them:
start, roll, freeze, reset.

**Why freeze is the one that matters.** A rolling baseline learns from the
captures that arrive. A machine degrading over months produces captures that
get worse slowly, the baseline follows them down, and every capture stays
within a sigma of a normal that is itself sliding. The fault never becomes
anomalous because "normal" moved with it. Freezing pins the normal to a
period somebody is willing to vouch for, and that is the only way a slow
degradation shows up as one.

**Why the state lives here and not on the statistic rows.** One version of
this sensor's baseline is 348 rows. A state kept on each of them is 348
copies of one fact, and 348 copies disagree eventually -- half a version
frozen and half rolling is not a state anybody can reason about. The version
is the unit that has a lifecycle, so the version is where the lifecycle is
recorded, and `feature_baseline_stats.is_active` goes away rather than
becoming a second answer to the same question.

Nothing outside `baseline_engine` read that column.

**The five columns added to the statistics.** `confidence`,
`excluded_count`, `distinct_count`, `mixed_population` and
`other_shape_count` are all computed today and all thrown away at the point
of storage. VIK-027 has to report how healthy a baseline is, and confidence
is the first thing it asks for -- recomputing it would mean rebuilding every
baseline from history to answer a read. They are stored because they were
already known.

`mixed_population` is the one worth keeping for its own sake: it marks a
baseline whose median and spread are usable but whose percentiles are not,
because the window holds more than one population. A reader that takes p95
from such a row without knowing that gets the other population's value.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None

STATS = "feature_baseline_stats"
VERSIONS = "baseline_versions"

#: building   -- being assembled; nothing is judged against it yet.
#: active     -- in force, and still rolling as captures arrive.
#: frozen     -- in force, and deliberately no longer rolling.
#: superseded -- replaced by a newer version. Kept, because a finding
#:               recorded against it has to stay explainable.
STATES = ("building", "active", "frozen", "superseded")


def upgrade() -> None:
    op.create_table(
        VERSIONS,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False,
                  server_default="building"),

        # Why this version exists, in the words of whoever started it. A
        # reset without a reason is a baseline change nobody can account for
        # six months later, which is the situation this table exists to end.
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(120), nullable=True),

        # One timestamp per transition rather than a single updated_at: the
        # question asked later is "how long was this in force", and that
        # needs both ends.
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.Integer(), nullable=True),
    )

    op.create_unique_constraint(
        f"uq_{VERSIONS}_sensor_version", VERSIONS, ["sensor_id", "version"])
    op.create_index(f"ix_{VERSIONS}_state", VERSIONS, ["sensor_id", "state"])

    op.create_check_constraint(
        f"ck_{VERSIONS}_state", VERSIONS,
        "state IN ('building', 'active', 'frozen', 'superseded')")
    op.create_check_constraint(
        f"ck_{VERSIONS}_version_positive", VERSIONS, "version >= 1")
    # A state carries its timestamp or it is not that state. Without this a
    # row can claim to be frozen with nothing saying when, and "how long has
    # this normal been pinned" has no answer.
    op.create_check_constraint(
        f"ck_{VERSIONS}_frozen_has_time", VERSIONS,
        "(state <> 'frozen') OR (frozen_at IS NOT NULL)")
    op.create_check_constraint(
        f"ck_{VERSIONS}_superseded_has_time", VERSIONS,
        "(state <> 'superseded') OR (superseded_at IS NOT NULL)")

    # At most one version in force per sensor. Two is not a richer answer,
    # it is an ambiguous one -- and the ambiguity would be resolved
    # differently by every reader.
    op.execute(
        f"CREATE UNIQUE INDEX uq_{VERSIONS}_one_in_force "
        f"ON {VERSIONS} (sensor_id) "
        f"WHERE state IN ('active', 'frozen')"
    )

    # --- adopt the versions that already exist ---------------------------
    #
    # This platform has baselines on disk from before the lifecycle existed.
    # The newest version of each sensor is the one that was in force, so it
    # becomes active; the rest were already replaced, so they become
    # superseded. Their timestamps are the row's own computed_at, which is
    # when that version was in fact built -- not now(), which would claim
    # every historical baseline was activated the day this migration ran.
    op.execute(f"""
        INSERT INTO {VERSIONS}
            (sensor_id, version, state, reason, created_at, activated_at,
             superseded_at, superseded_by)
        SELECT s.sensor_id, s.baseline_version,
               CASE WHEN s.baseline_version = s.newest THEN 'active'
                    ELSE 'superseded' END,
               'Adopted by migration 028; predates the lifecycle.',
               s.built_at,
               s.built_at,
               CASE WHEN s.baseline_version = s.newest THEN NULL
                    ELSE s.built_at END,
               CASE WHEN s.baseline_version = s.newest THEN NULL
                    ELSE s.newest END
          FROM (SELECT sensor_id, baseline_version,
                       MIN(computed_at) AS built_at,
                       MAX(baseline_version) OVER (PARTITION BY sensor_id)
                           AS newest
                  FROM {STATS}
                 GROUP BY sensor_id, baseline_version) s
    """)

    # --- the statistics gain what the engine already knew ----------------
    op.add_column(STATS, sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column(STATS, sa.Column("excluded_count", sa.Integer(),
                                   nullable=False, server_default="0"))
    op.add_column(STATS, sa.Column("distinct_count", sa.Integer(),
                                   nullable=False, server_default="0"))
    op.add_column(STATS, sa.Column("mixed_population", sa.Boolean(),
                                   nullable=False,
                                   server_default=sa.text("false")))
    op.add_column(STATS, sa.Column("other_shape_count", sa.Integer(),
                                   nullable=False, server_default="0"))
    op.create_check_constraint(
        f"ck_{STATS}_confidence_range", STATS,
        "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)")

    # --- one answer to "is this in force" --------------------------------
    op.drop_index(f"ix_{STATS}_lookup", table_name=STATS)
    op.drop_column(STATS, "is_active")
    op.create_index(f"ix_{STATS}_lookup", STATS,
                    ["sensor_id", "baseline_version", "channel",
                     "feature_code"])


def downgrade() -> None:
    op.drop_index(f"ix_{STATS}_lookup", table_name=STATS)
    op.add_column(STATS, sa.Column("is_active", sa.Boolean(), nullable=False,
                                   server_default=sa.text("true")))
    # Restore the old meaning from the new authority before it is dropped.
    op.execute(f"""
        UPDATE {STATS} s SET is_active = (v.state IN ('active', 'frozen'))
          FROM {VERSIONS} v
         WHERE v.sensor_id = s.sensor_id AND v.version = s.baseline_version
    """)
    op.create_index(f"ix_{STATS}_lookup", STATS,
                    ["sensor_id", "channel", "feature_code", "is_active"])

    op.drop_constraint(f"ck_{STATS}_confidence_range", STATS)
    for column in ("other_shape_count", "mixed_population", "distinct_count",
                   "excluded_count", "confidence"):
        op.drop_column(STATS, column)

    op.drop_table(VERSIONS)
