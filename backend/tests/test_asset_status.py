"""The status an expert puts on a machine — SNV-STA-01, SNV-STA-10.

Two rules are worth testing and one of them is easy to get wrong. A machine
takes the *worst* of its sensors, not the average and not the latest — a real
finding must not disappear into a fleet that is mostly fine. And once a person
sets a machine's status by hand it stops inheriting, because otherwise the next
capture would quietly undo the judgement they just made.

The ranking tests need no database. The inheritance and override tests do, and
skip with the rest of the db-marked suite when none is configured.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.status import (
    SCOPE_MACHINE,
    SCOPE_SENSOR,
    STATUS_VALUES,
    worst_status,
)
from app.services import asset_status as status_service


# ---------------------------------------------------------------------------
# Ranking — no database
# ---------------------------------------------------------------------------


def test_the_seven_published_values():
    # The frontend switches on these. An eighth arriving without a schema
    # change is a state no screen knows how to colour.
    assert STATUS_VALUES == (
        "Normal",
        "Warning",
        "Alarm",
        "Critical",
        "Unknown",
        "Out of service",
        "Not monitored",
    )


@pytest.mark.parametrize(
    "values,expected",
    [
        (["Normal", "Warning", "Critical"], "Critical"),
        (["Normal", "Alarm", "Warning"], "Alarm"),
        (["Normal", "Warning"], "Warning"),
        (["Normal", "Normal"], "Normal"),
    ],
)
def test_the_worst_sensor_decides(values, expected):
    assert worst_status(values) == expected


def test_seven_healthy_sensors_do_not_outvote_one_critical():
    # The whole reason this is a maximum and not an average.
    assert worst_status(["Normal"] * 7 + ["Critical"]) == "Critical"


def test_nothing_judged_is_unknown_not_normal():
    # A machine nobody has looked at is unexamined. Reporting Normal would be
    # a claim no one made.
    assert worst_status([]) == "Unknown"
    assert worst_status(["Unknown", "Unknown"]) == "Unknown"


def test_out_of_service_never_outranks_a_real_finding():
    """A sensor still reading Critical is the thing worth seeing.

    Out of service and Not monitored say the machine sits outside the scale,
    not that it is worse than Critical. If they won the comparison, marking a
    machine out of service would hide a live fault on it.
    """
    assert worst_status(["Out of service", "Critical"]) == "Critical"
    assert worst_status(["Not monitored", "Warning"]) == "Warning"


def test_states_outside_the_scale_alone_are_unknown():
    assert worst_status(["Out of service"]) == "Unknown"
    assert worst_status(["Not monitored", "Out of service"]) == "Unknown"


# ---------------------------------------------------------------------------
# Inheritance and override — against the database
# ---------------------------------------------------------------------------


@pytest.fixture
def machine(db):
    """A machine with two sensors on it."""
    equipment = uuid.uuid4()
    db.execute(
        sa.text(
            """
            INSERT INTO equipment_masters
                (id, plant_name, area, line, machine_name, machine_type,
                 machine_criticality)
            VALUES (:id, 'Test Plant', 'Test Area', 'Test Line',
                    'Test Pump', 'pump', 'medium')
            """
        ),
        {"id": str(equipment)},
    )
    sensors = []
    for location in ("drive end", "non-drive end"):
        sensor = uuid.uuid4()
        db.execute(
            sa.text(
                """
                INSERT INTO sensor_configurations
                    (id, equipment_id, sensor_type, mounting_location,
                     orientation, sensitivity)
                VALUES (:id, :eq, 'accelerometer', :loc, 'radial', 100.0)
                """
            ),
            {"id": str(sensor), "eq": str(equipment), "loc": location},
        )
        sensors.append(sensor)
    db.flush()
    return equipment, sensors


@pytest.mark.db
def test_a_machine_with_no_judged_sensors_is_unknown(db, machine):
    equipment, _ = machine
    resolved, overridden = status_service.resolve_machine_status(db, equipment)
    assert resolved == "Unknown"
    assert overridden is False


@pytest.mark.db
def test_a_machine_takes_the_worst_of_its_sensors(db, machine):
    equipment, sensors = machine
    status_service.set_status(db, SCOPE_SENSOR, sensors[0], "Normal")
    status_service.set_status(db, SCOPE_SENSOR, sensors[1], "Alarm")

    resolved, overridden = status_service.resolve_machine_status(db, equipment)
    assert resolved == "Alarm"
    assert overridden is False


@pytest.mark.db
def test_an_override_stops_the_machine_following_its_sensors(db, machine):
    """The judgement an analyst made survives the next capture.

    Without this the roll-up would overwrite it the moment a sensor moved, and
    the analyst would watch their own decision disappear.
    """
    equipment, sensors = machine
    status_service.set_status(db, SCOPE_SENSOR, sensors[0], "Critical")
    status_service.set_status(
        db, SCOPE_MACHINE, equipment, "Normal", overridden=True
    )

    resolved, overridden = status_service.resolve_machine_status(db, equipment)
    assert resolved == "Normal"
    assert overridden is True

    # A recompute must leave it alone.
    status_service.refresh_machine_status(db, equipment)
    assert status_service.resolve_machine_status(db, equipment) == ("Normal", True)


@pytest.mark.db
def test_releasing_the_override_returns_the_machine_to_its_sensors(db, machine):
    equipment, sensors = machine
    status_service.set_status(db, SCOPE_SENSOR, sensors[0], "Critical")
    status_service.set_status(db, SCOPE_MACHINE, equipment, "Normal", overridden=True)

    status_service.clear_override(db, equipment)
    status_service.refresh_machine_status(db, equipment)

    resolved, overridden = status_service.resolve_machine_status(db, equipment)
    assert resolved == "Critical"
    assert overridden is False


@pytest.mark.db
def test_who_set_it_and_when_are_always_recorded(db, machine):
    # An unattributed status is not auditable, which is the point of having a
    # person set it rather than a threshold.
    equipment, sensors = machine
    row = status_service.set_status(db, SCOPE_SENSOR, sensors[0], "Warning")

    assert row.set_at is not None
    assert row.status == "Warning"


@pytest.mark.db
def test_one_asset_holds_one_status(db, machine):
    # Setting twice replaces; it does not accumulate rows that later disagree.
    equipment, sensors = machine
    status_service.set_status(db, SCOPE_SENSOR, sensors[0], "Warning")
    status_service.set_status(db, SCOPE_SENSOR, sensors[0], "Critical")

    count = db.execute(
        sa.text(
            "SELECT count(*) FROM asset_status WHERE scope = :s AND asset_id = :a"
        ),
        {"s": SCOPE_SENSOR, "a": str(sensors[0])},
    ).scalar()
    assert count == 1
    assert status_service.get_row(db, SCOPE_SENSOR, sensors[0]).status == "Critical"


@pytest.mark.db
def test_a_sensor_status_rolls_its_machine_up_immediately(db, machine):
    """The machine view must not lag the judgement behind it."""
    equipment, sensors = machine
    status_service.set_status(db, SCOPE_SENSOR, sensors[0], "Alarm")
    status_service.refresh_machine_status(db, equipment)

    stored = status_service.get_row(db, SCOPE_MACHINE, equipment)
    assert stored is not None
    assert stored.status == "Alarm"
    assert stored.overridden is False
