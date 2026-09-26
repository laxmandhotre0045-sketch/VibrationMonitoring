"""Which threshold rule wins — VIK-029.

Sensor, then equipment, then machine type, then global; and inside any one of
those, a rule that names a channel beats one that does not.

Two things are tested here. The ladder itself, against a real database because
the query that gathers the candidates is half the logic. And the bug the ladder
was useless without: the feature pipeline called `get_resolved_rule_map(db)`
with no context, which did not merely fail to prefer a scoped rule — it
filtered every scoped rule out of the map, so no configuration could make one
fire and every status in the system came from the global rule.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.crud.feature import _precedence, get_resolved_rule_map, resolve_rule

TABLE = "feature_threshold_rules"
CODE = "rms"


pytestmark = pytest.mark.db


def make_machine(db, machine_type="pump"):
    """A machine and one accelerometer on it, to hang scoped rules from.

    Created for real rather than with invented UUIDs: both new columns carry a
    foreign key, so a rule pointed at a machine that does not exist is rejected
    by the database — which is the point of the constraint.
    """
    equipment = uuid.uuid4()
    sensor = uuid.uuid4()
    db.execute(
        sa.text(
            """
            INSERT INTO equipment_masters
                (id, plant_name, area, line, machine_name, machine_type,
                 machine_criticality)
            VALUES (:id, 'Test Plant', 'Test Area', 'Test Line',
                    'Test Pump', :mt, 'medium')
            """
        ),
        {"id": str(equipment), "mt": machine_type},
    )
    db.execute(
        sa.text(
            """
            INSERT INTO sensor_configurations
                (id, equipment_id, sensor_type, mounting_location, orientation,
                 sensitivity)
            VALUES (:id, :eq, 'accelerometer', 'drive end', 'radial', 100.0)
            """
        ),
        {"id": str(sensor), "eq": str(equipment)},
    )
    # The catalogue seeds a global rule for every feature, and
    # `uq_threshold_rule_global` is unique per feature code, so these tests
    # take ownership of this one code and write the whole ladder themselves.
    # The session is rolled back afterwards, so the seed is untouched.
    db.flush()
    return equipment, sensor


@pytest.fixture
def equipment_and_sensor(db):
    """The machine under test, with this feature's seeded rule cleared.

    The catalogue seeds a global rule for every feature and
    `uq_threshold_rule_global` is unique per feature code, so these tests take
    ownership of one code and write the whole ladder themselves. The session is
    rolled back afterwards, so the seed is untouched.
    """
    db.execute(sa.text(f"DELETE FROM {TABLE} WHERE feature_code = :c"), {"c": CODE})
    db.flush()
    return make_machine(db)


def add_rule(db, *, normal_max, machine_type=None, channel=None,
             sensor_id=None, equipment_id=None):
    """One rule at one scope. `normal_max` doubles as its fingerprint."""
    rule_id = uuid.uuid4()
    db.execute(
        sa.text(
            f"""
            INSERT INTO {TABLE}
                (id, feature_code, rule_type, machine_type, channel,
                 sensor_id, equipment_id, normal_max, warning_max,
                 metadata, is_active)
            VALUES (:id, :code, 'absolute_max', :mt, :ch, :sid, :eid,
                    :nmax, :wmax, '{{}}'::jsonb, true)
            """
        ),
        {
            "id": str(rule_id), "code": CODE, "mt": machine_type, "ch": channel,
            "sid": str(sensor_id) if sensor_id else None,
            "eid": str(equipment_id) if equipment_id else None,
            "nmax": normal_max, "wmax": normal_max * 2,
        },
    )
    db.flush()
    return rule_id


def winner(db, channel=None, **context):
    """The normal_max of whichever rule wins for `channel`."""
    rule_map = get_resolved_rule_map(db, context.pop("machine_type", None), **context)
    rule = resolve_rule(rule_map, channel, CODE)
    return None if rule is None else float(rule.normal_max)


# ---------------------------------------------------------------------------
# The ladder
# ---------------------------------------------------------------------------


def test_a_sensor_rule_beats_every_broader_one(db, equipment_and_sensor):
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)                                # global
    add_rule(db, normal_max=0.02, machine_type="pump")           # machine type
    add_rule(db, normal_max=0.03, equipment_id=equipment)        # equipment
    add_rule(db, normal_max=0.04, sensor_id=sensor)              # sensor

    assert winner(db, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.04


def test_equipment_beats_machine_type_and_global(db, equipment_and_sensor):
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.02, machine_type="pump")
    add_rule(db, normal_max=0.03, equipment_id=equipment)

    assert winner(db, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.03


def test_machine_type_beats_global(db, equipment_and_sensor):
    """The live bug, stated as the behaviour it broke.

    A pump rule exists and the reading is from a pump, so the pump rule is the
    answer. Before the fix the caller passed no machine type and this returned
    the global 0.01.
    """
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.02, machine_type="pump")

    assert winner(db, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.02


def test_a_machine_type_matches_whatever_case_either_side_used(db, equipment_and_sensor):
    """Nothing canonicalises machine type, so the comparison must not care.

    The equipment records on this platform say "Pump"; a rule is free text a
    person types. An exact comparison would leave a rule written for "pump"
    silently never firing — the same failure this function was fixed for, just
    moved from the caller to the collation.
    """
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.02, machine_type="  PuMp  ")

    for typed_as in ("pump", "Pump", "PUMP", " pump "):
        assert winner(db, machine_type=typed_as, sensor_id=sensor,
                      equipment_id=equipment) == 0.02, typed_as


def test_a_different_machine_type_still_does_not_match(db, equipment_and_sensor):
    # Ignoring case must not turn into ignoring the value.
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.02, machine_type="pump")

    assert winner(db, machine_type="motor", sensor_id=sensor,
                  equipment_id=equipment) == 0.01


def test_the_global_rule_answers_when_nothing_narrower_exists(db, equipment_and_sensor):
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)

    assert winner(db, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.01


def test_another_machines_rule_does_not_apply_to_this_one(db, equipment_and_sensor):
    """Scoping has to exclude as well as include, or it is just a global rule."""
    equipment, sensor = equipment_and_sensor
    other_equipment, other_sensor = make_machine(db, machine_type="compressor")

    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.09, machine_type="compressor")
    add_rule(db, normal_max=0.08, sensor_id=other_sensor)
    add_rule(db, normal_max=0.07, equipment_id=other_equipment)

    assert winner(db, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.01


# ---------------------------------------------------------------------------
# Channel against scope
# ---------------------------------------------------------------------------


def test_a_named_channel_wins_inside_one_scope(db, equipment_and_sensor):
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.04, sensor_id=sensor)
    add_rule(db, normal_max=0.05, sensor_id=sensor, channel=3)

    assert winner(db, channel=3, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.05
    # Channel 0 has no rule of its own and falls back to the sensor's.
    assert winner(db, channel=0, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.04


def test_scope_outranks_channel_across_scopes(db, equipment_and_sensor):
    """The case that cannot be keyed on channel alone.

    A global rule names channel 3; a sensor rule names no channel. The sensor
    rule is about *this machine* and the global one is about every machine on
    the platform, so the sensor rule is the more specific answer for channel 3
    even though the other one names that channel.
    """
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.02, channel=3)
    add_rule(db, normal_max=0.04, sensor_id=sensor)

    assert winner(db, channel=3, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.04


def test_a_channel_rule_still_wins_where_no_scoped_rule_covers_it(db, equipment_and_sensor):
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.02, channel=3)

    assert winner(db, channel=3, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.02
    assert winner(db, channel=1, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.01


# ---------------------------------------------------------------------------
# The live bug
# ---------------------------------------------------------------------------


def test_calling_without_context_hides_scoped_rules_entirely(db, equipment_and_sensor):
    """What the pipeline used to do, kept as the reason the fix matters.

    Omitting the context does not fall back to the scoped rule — it removes it
    from the map. Worth an explicit test because the failure is silent: the
    call succeeds, a rule comes back, and it is the wrong one.
    """
    equipment, sensor = equipment_and_sensor
    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.02, machine_type="pump")
    add_rule(db, normal_max=0.04, sensor_id=sensor)

    assert winner(db) == 0.01

    assert winner(db, machine_type="pump", sensor_id=sensor,
                  equipment_id=equipment) == 0.04


def test_an_unknown_machine_type_gets_the_global_rule_not_a_guess(db, equipment_and_sensor):
    # A sensor whose equipment cannot be read narrows to untyped rules rather
    # than borrowing another fleet's limits.
    add_rule(db, normal_max=0.01)
    add_rule(db, normal_max=0.02, machine_type="pump")

    assert winner(db, machine_type=None) == 0.01


# ---------------------------------------------------------------------------
# Ranking, without a database
# ---------------------------------------------------------------------------


class Rule:
    def __init__(self, sensor_id=None, equipment_id=None, machine_type=None, channel=None):
        self.sensor_id = sensor_id
        self.equipment_id = equipment_id
        self.machine_type = machine_type
        self.channel = channel


@pytest.mark.parametrize(
    "narrower,broader",
    [
        (Rule(sensor_id=1), Rule(equipment_id=1)),
        (Rule(equipment_id=1), Rule(machine_type="pump")),
        (Rule(machine_type="pump"), Rule()),
        (Rule(sensor_id=1), Rule()),
        # Channel breaks ties inside a scope...
        (Rule(sensor_id=1, channel=3), Rule(sensor_id=1)),
        (Rule(channel=3), Rule()),
        # ...but never outranks the scope itself.
        (Rule(sensor_id=1), Rule(channel=3)),
        (Rule(machine_type="pump"), Rule(channel=3)),
    ],
)
def test_the_narrower_rule_ranks_higher(narrower, broader):
    assert _precedence(narrower) > _precedence(broader)


def test_a_rule_carrying_a_sensor_ranks_by_the_sensor():
    # Both columns set should not happen — there is a CHECK against it — but
    # ranking by the narrower of the two is the safe reading if it ever does.
    assert _precedence(Rule(sensor_id=1, machine_type="pump")) == _precedence(Rule(sensor_id=1))


# ---------------------------------------------------------------------------
# End to end, through the pipeline that had the bug
# ---------------------------------------------------------------------------


def test_a_pump_rule_decides_a_pump_reading_through_the_real_pipeline(db):
    """The ticket's claim, checked where it was actually wrong.

    Everything above tests the resolver. This runs the function that calls it —
    the one that passed no context — and asserts on the status it stored. A
    reading of about 0.05 g is critical under the seeded global rule
    (warning_max 0.02) and comfortably normal under the pump rule written here.
    Before the fix the pump rule was filtered out of the map and this stored
    "critical".
    """
    import numpy as np

    from app.services.feature_storage import persist_upload_features_and_trends

    equipment, sensor = make_machine(db, machine_type="Pump")

    # Note the case: the equipment says "Pump", the rule says "pump".
    add_rule(db, normal_max=1.0, machine_type="pump")

    upload_id = uuid.uuid4()
    db.execute(
        sa.text(
            """
            INSERT INTO sensor_data_uploads (id, sensor_id, channel_count, pdf_path)
            VALUES (:id, :s, 1, '')
            """
        ),
        {"id": str(upload_id), "s": str(sensor)},
    )
    db.flush()

    upload = db.query(
        __import__("app.models.measurement", fromlist=["SensorDataUpload"]).SensorDataUpload
    ).filter_by(id=upload_id).one()

    # Sine plus a little noise. A mathematically pure tone makes some of the
    # ratio features degenerate (a zero denominator sends one of them past
    # what numeric(18,8) can hold), which is a property of the test signal
    # rather than of anything under test here.
    rate = 2048.0
    t = np.arange(4096) / rate
    rng = np.random.default_rng(20260924)
    samples = (
        0.06 * np.sin(2 * np.pi * 50.0 * t) + rng.normal(0.0, 0.02, t.size)
    ).tolist()
    parsed = {"channels": {"ch0": samples}, "channel_count": 1, "sample_count": len(samples)}

    persist_upload_features_and_trends(db, upload, parsed, rate, with_trends=False)
    db.flush()

    row = db.execute(
        sa.text(
            """
            SELECT value, status FROM measurement_channel_features
             WHERE upload_id = :u AND feature_code = 'rms' AND channel = 0
            """
        ),
        {"u": str(upload_id)},
    ).one()

    assert 0.04 < float(row.value) < 0.06, f"test signal is not ~0.05 g: {row.value}"
    assert row.status == "normal", (
        f"rms {row.value} stored as {row.status!r}: the pump rule did not win. "
        "The global rule's warning_max is 0.02, so this is the old bug."
    )
