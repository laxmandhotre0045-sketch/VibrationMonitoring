"""Migration 023 — sensor and equipment scoping on threshold rules.

These run against the real schema the migrations build, which is the only place
the answer lives: the columns, their nullability, the foreign keys, and the
partial unique indexes that decide whether a scoped rule can be inserted at all.

The last of those is the point. `015` left an index that is unique on
`feature_code` wherever machine type and channel are NULL — the exact shape a
sensor-scoped rule has. Adding two columns without narrowing it would leave a
table with the right columns and no way to use them, and nothing about the
column list would show it.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.db

TABLE = "feature_threshold_rules"


# ---------------------------------------------------------------------------
# Fixtures: a real sensor and a real machine to point rules at
# ---------------------------------------------------------------------------


@pytest.fixture
def feature_code(db) -> str:
    """Any seeded feature definition — the rules table has an FK onto it."""
    code = db.execute(
        sa.text("SELECT code FROM feature_definitions ORDER BY sort_order LIMIT 1")
    ).scalar()
    assert code, "migration 010 seeds these; without one there is nothing to scope"
    return code


@pytest.fixture
def equipment_id(db) -> uuid.UUID:
    from app.models.equipment import Equipment

    machine = Equipment(
        plant_name="Test Plant",
        area="Utilities",
        line="Cooling",
        machine_name="Scope Test Pump",
        machine_id=f"SCOPE-{uuid.uuid4().hex[:8].upper()}",
        machine_type="Pump",
        machine_criticality="High",
    )
    db.add(machine)
    db.flush()
    return machine.id


@pytest.fixture
def sensor_ids(db, equipment_id) -> tuple[uuid.UUID, uuid.UUID]:
    """Two sensors on one machine — enough to collide, if the indexes are wrong."""
    from app.models.sensor import SensorConfiguration

    made = []
    for location in ("Bearing Housing DE", "Bearing Housing NDE"):
        sensor = SensorConfiguration(
            equipment_id=equipment_id,
            sensor_type="IEPE Accelerometer",
            mounting_location=location,
            orientation="Horizontal",
        )
        db.add(sensor)
        made.append(sensor)
    db.flush()
    return made[0].id, made[1].id


def insert_rule(db, feature_code: str, **scope) -> uuid.UUID:
    """One rule row, scoped however the test asks."""
    rule_id = uuid.uuid4()
    columns = ["id", "feature_code", "rule_type", "metadata"]
    values = [":id", ":code", "'absolute_max'", "'{}'::jsonb"]
    params: dict = {"id": str(rule_id), "code": feature_code}

    for name, value in scope.items():
        columns.append(name)
        values.append(f":{name}")
        params[name] = str(value) if isinstance(value, uuid.UUID) else value

    db.execute(
        sa.text(
            f"INSERT INTO {TABLE} ({', '.join(columns)}) VALUES ({', '.join(values)})"
        ),
        params,
    )
    return rule_id


# ---------------------------------------------------------------------------
# The columns
# ---------------------------------------------------------------------------


def test_the_columns_exist_and_are_nullable(db):
    columns = {
        row.column_name: row
        for row in db.execute(
            sa.text(
                "SELECT column_name, is_nullable, data_type FROM information_schema.columns "
                "WHERE table_name = :table"
            ),
            {"table": TABLE},
        )
    }

    for name in ("sensor_id", "equipment_id"):
        assert name in columns, f"{name} was not added"
        assert columns[name].is_nullable == "YES", f"{name} must be nullable"
        assert columns[name].data_type == "uuid"


def test_the_columns_point_at_the_tables_they_name(db):
    """A scope column that is not a foreign key is a free-text field with a
    UUID-shaped habit: rules would outlive the sensors they describe."""
    references = {
        row.column_name: (row.foreign_table, row.delete_rule)
        for row in db.execute(
            sa.text(
                """
                SELECT kcu.column_name,
                       ccu.table_name AS foreign_table,
                       rc.delete_rule
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                JOIN information_schema.referential_constraints rc
                  ON tc.constraint_name = rc.constraint_name
                WHERE tc.table_name = :table AND tc.constraint_type = 'FOREIGN KEY'
                """
            ),
            {"table": TABLE},
        )
    }

    assert references.get("sensor_id") == ("sensor_configurations", "CASCADE")
    assert references.get("equipment_id") == ("equipment_masters", "CASCADE")


def test_the_model_and_the_table_agree(db):
    """The ORM must know about the columns, or nothing can ever read them."""
    from app.models.measurement import FeatureThresholdRule

    mapped = set(FeatureThresholdRule.__table__.columns.keys())
    assert {"sensor_id", "equipment_id"} <= mapped


# ---------------------------------------------------------------------------
# Existing rows are untouched
# ---------------------------------------------------------------------------


def test_every_rule_that_predates_the_migration_is_still_global(db):
    """The seeded rules from 010 must still apply to everything.

    They are the only rules on a fresh database, so if 023 had scoped, rewritten
    or dropped any of them, this is where it shows.
    """
    rows = db.execute(
        sa.text(f"SELECT sensor_id, equipment_id FROM {TABLE}")
    ).fetchall()

    assert rows, "the seeded rules are missing entirely"
    assert all(row.sensor_id is None and row.equipment_id is None for row in rows)


def test_the_seeded_rules_are_all_still_there(db):
    """One row per seeded default, no more and no fewer.

    Counted against the feature catalogue rather than
    `THRESHOLD_RULE_DEFAULTS`. That dict was the whole seed when this test was
    written; 023 and 024 made it the absolute-limit special case and gave every
    other definition a baseline-relative or informational default, so it now
    names ten of the catalogue's rules rather than all of them.
    """
    from app.services.feature_catalog import all_default_rules

    seeded = db.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TABLE} "
            "WHERE sensor_id IS NULL AND equipment_id IS NULL "
            "AND machine_type IS NULL AND channel IS NULL"
        )
    ).scalar()

    assert seeded == len(all_default_rules())


# ---------------------------------------------------------------------------
# What the new columns are for
# ---------------------------------------------------------------------------


def test_two_sensors_can_hold_their_own_limit_for_one_feature(db, feature_code, sensor_ids):
    """The whole ticket, in one assertion.

    Before the indexes were narrowed this raised a unique violation on
    `uq_threshold_rule_global`: both rows have machine_type and channel NULL,
    which that index read as two global rules for one feature.
    """
    first, second = sensor_ids
    insert_rule(db, feature_code, sensor_id=first)
    insert_rule(db, feature_code, sensor_id=second)

    scoped = db.execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE sensor_id IS NOT NULL"),
    ).scalar()
    assert scoped == 2


def test_a_machine_can_hold_its_own_limit_alongside_the_global_one(
    db, feature_code, equipment_id
):
    insert_rule(db, feature_code, equipment_id=equipment_id)

    assert db.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {TABLE} "
            "WHERE equipment_id = :id OR (sensor_id IS NULL AND equipment_id IS NULL)"
        ),
        {"id": str(equipment_id)},
    ).scalar() >= 2


def test_one_sensor_cannot_hold_two_limits_for_the_same_feature(db, feature_code, sensor_ids):
    """Two rules for one sensor and one feature is an unresolvable tie."""
    sensor, _ = sensor_ids
    insert_rule(db, feature_code, sensor_id=sensor)

    with pytest.raises(IntegrityError):
        insert_rule(db, feature_code, sensor_id=sensor)


def test_one_sensor_can_hold_a_limit_per_channel(db, feature_code, sensor_ids):
    sensor, _ = sensor_ids
    insert_rule(db, feature_code, sensor_id=sensor, channel=0)
    insert_rule(db, feature_code, sensor_id=sensor, channel=1)

    assert db.execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE sensor_id = :id"),
        {"id": str(sensor)},
    ).scalar() == 2


def test_the_global_rules_are_still_unique(db, feature_code):
    """Narrowing the predicate must not have loosened what it guarded."""
    with pytest.raises(IntegrityError):
        insert_rule(db, feature_code)


def test_a_rule_is_scoped_at_one_level_only(db, feature_code, equipment_id, sensor_ids):
    """A sensor already belongs to a machine, so a row naming both is either
    redundant or a contradiction — and nothing could resolve the second case."""
    sensor, _ = sensor_ids

    with pytest.raises(IntegrityError):
        insert_rule(db, feature_code, sensor_id=sensor, equipment_id=equipment_id)


def test_deleting_a_sensor_takes_its_rules_with_it(db, feature_code, sensor_ids):
    from app.models.sensor import SensorConfiguration

    sensor, _ = sensor_ids
    insert_rule(db, feature_code, sensor_id=sensor)

    db.query(SensorConfiguration).filter_by(id=sensor).delete()
    db.flush()

    assert db.execute(
        sa.text(f"SELECT COUNT(*) FROM {TABLE} WHERE sensor_id = :id"),
        {"id": str(sensor)},
    ).scalar() == 0
