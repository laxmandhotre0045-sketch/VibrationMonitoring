"""threshold rules gain a sensor and an equipment scope

Until now a rule could be narrowed by `machine_type` and `channel` and nothing
else, so a single RMS limit judged every pump on the platform. Two machines of
the same type, one on a soft foundation and one bolted to a plinth, do not share
a warning level — and a single asset that has just been rebuilt does not share
one with the rest of its fleet.

`sensor_id` and `equipment_id` are both nullable and both mean the same thing
when NULL as before: this rule is not narrowed that way. Every existing row is
left exactly as it was — no UPDATE runs here — so the seeded global rules keep
applying to everything that has no more specific row, and a site overrides only
what it cares about.

Scope, most specific first: sensor, then equipment, then machine type, then
channel, then global. A row carries at most one of `sensor_id` and
`equipment_id`; a sensor already belongs to one piece of equipment, so a row
with both would either be redundant or contradict itself, and there is a CHECK
here that says so.

## The part that is not just two columns

`015` left three partial unique indexes behind, and all three assume machine
type and channel are the only way to narrow a rule. `uq_threshold_rule_global`
is unique on `feature_code` alone wherever machine_type and channel are NULL —
which is exactly the shape a sensor-scoped rule has. Adding the columns without
touching that index would have made the second sensor-scoped rule for any
feature fail on a unique violation, and the columns would have been unusable.

So the three existing predicates are narrowed to mean "and not scoped to a
sensor or a piece of equipment either", and four more cover uniqueness at the
new scopes. Rewriting a predicate rewrites an index, not a row.

Revision ID: 029
Revises: 028
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "029"
# Originally written as 023 chained to 021, when 021 was the only head in this
# repository. 022 onwards then landed from another branch and did exactly what
# the note here warned about: two revisions numbered 023, two numbered 021, and
# two heads, so `alembic upgrade head` could no longer pick one and everything
# from 024 up was stranded. Re-chained onto 028, the real head.
#
# Safe to re-run where the old 023 already applied it: every step below is
# guarded by an existence check, so on those databases this is a no-op.
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "feature_threshold_rules"

#: Existing indexes whose predicates no longer describe "global".
NARROWED = (
    (
        "uq_threshold_rule_scope",
        ["feature_code", "machine_type", "channel"],
        "machine_type IS NOT NULL AND channel IS NOT NULL",
    ),
    (
        "uq_threshold_rule_global",
        ["feature_code"],
        "machine_type IS NULL AND channel IS NULL",
    ),
    (
        "uq_threshold_rule_channel",
        ["feature_code", "channel"],
        "machine_type IS NULL AND channel IS NOT NULL",
    ),
)

UNSCOPED = "sensor_id IS NULL AND equipment_id IS NULL"

#: Uniqueness at the new scopes. Split by whether `channel` is set, because
#: Postgres treats NULLs as distinct in a unique index — one index over a
#: nullable channel would let two rows with no channel through.
ADDED = (
    (
        "uq_threshold_rule_sensor",
        ["feature_code", "sensor_id"],
        "sensor_id IS NOT NULL AND channel IS NULL",
    ),
    (
        "uq_threshold_rule_sensor_channel",
        ["feature_code", "sensor_id", "channel"],
        "sensor_id IS NOT NULL AND channel IS NOT NULL",
    ),
    (
        "uq_threshold_rule_equipment",
        ["feature_code", "equipment_id"],
        "equipment_id IS NOT NULL AND sensor_id IS NULL AND channel IS NULL",
    ),
    (
        "uq_threshold_rule_equipment_channel",
        ["feature_code", "equipment_id", "channel"],
        "equipment_id IS NOT NULL AND sensor_id IS NULL AND channel IS NOT NULL",
    ),
)


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    return column in {c["name"] for c in sa.inspect(bind).get_columns(table)}


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    return name in {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    checks = sa.inspect(bind).get_check_constraints(table)
    return name in {c["name"] for c in checks}


def upgrade() -> None:
    if not _column_exists(TABLE, "sensor_id"):
        op.add_column(
            TABLE,
            sa.Column(
                "sensor_id",
                UUID(as_uuid=True),
                # A rule written for one accelerometer means nothing once that
                # accelerometer is gone.
                sa.ForeignKey("sensor_configurations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )

    if not _column_exists(TABLE, "equipment_id"):
        op.add_column(
            TABLE,
            sa.Column(
                "equipment_id",
                UUID(as_uuid=True),
                sa.ForeignKey("equipment_masters.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )

    # Lookup indexes. Partial, because the overwhelming majority of rows are
    # global and indexing their NULLs buys nothing.
    for column in ("sensor_id", "equipment_id"):
        name = f"ix_feature_threshold_rules_{column}"
        if not _index_exists(TABLE, name):
            op.create_index(
                name,
                TABLE,
                [column],
                postgresql_where=sa.text(f"{column} IS NOT NULL"),
            )

    # Narrow the three predicates that used to define "global".
    for name, columns, predicate in NARROWED:
        if _index_exists(TABLE, name):
            op.drop_index(name, table_name=TABLE)
        op.create_index(
            name,
            TABLE,
            columns,
            unique=True,
            postgresql_where=sa.text(f"{predicate} AND {UNSCOPED}"),
        )

    for name, columns, predicate in ADDED:
        if not _index_exists(TABLE, name):
            op.create_index(
                name, TABLE, columns, unique=True, postgresql_where=sa.text(predicate)
            )

    # One scope per row. Every existing row has both columns NULL, so nothing
    # already stored can violate this.
    if not _constraint_exists(TABLE, "ck_threshold_rule_one_scope"):
        op.create_check_constraint(
            "ck_threshold_rule_one_scope",
            TABLE,
            "sensor_id IS NULL OR equipment_id IS NULL",
        )


def downgrade() -> None:
    if _constraint_exists(TABLE, "ck_threshold_rule_one_scope"):
        op.drop_constraint("ck_threshold_rule_one_scope", TABLE, type_="check")

    for name, _columns, _predicate in ADDED:
        if _index_exists(TABLE, name):
            op.drop_index(name, table_name=TABLE)

    # Put the three predicates back the way 015 wrote them.
    for name, columns, predicate in NARROWED:
        if _index_exists(TABLE, name):
            op.drop_index(name, table_name=TABLE)
        op.create_index(
            name, TABLE, columns, unique=True, postgresql_where=sa.text(predicate)
        )

    for column in ("sensor_id", "equipment_id"):
        name = f"ix_feature_threshold_rules_{column}"
        if _index_exists(TABLE, name):
            op.drop_index(name, table_name=TABLE)
        if _column_exists(TABLE, column):
            op.drop_column(TABLE, column)
