"""The scope a threshold rule is written at, over the API — VIK-029.

The columns landed with the migration and the resolver reads them, but until
the API carried them no screen could show which sensors have a limit of their
own and which fall back. These tests cover that surface: the scope on the way
out, the sensor roster the coverage view needs, and creating a rule at a
narrower scope than global.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.db

RULES = "/api/v1/thresholds/rules"


@pytest.fixture
def feature_code(db):
    """A feature that exists, taken from the catalogue rather than invented."""
    return db.execute(
        sa.text("SELECT code FROM feature_definitions ORDER BY sort_order LIMIT 1")
    ).scalar()


def test_a_rule_carries_the_scope_it_was_written_at(client, admin_headers, sensor_id):
    response = client.get(RULES, headers=admin_headers)
    assert response.status_code == 200, response.text

    items = response.json()["items"]
    assert items, "no rules seeded"
    for key in ("sensor_id", "equipment_id", "machine_type", "channel"):
        assert key in items[0], f"{key} is missing from the rule payload"

    # The seeded rules are global, and say so rather than omitting the fields.
    assert items[0]["sensor_id"] is None
    assert items[0]["equipment_id"] is None


def test_the_response_lists_every_sensor_not_only_the_scoped_ones(
    client, admin_headers, sensor_id
):
    """The half a coverage view cannot compute for itself.

    A view built from the rules alone can show which sensors have their own
    limit but never which ones fall back, because a sensor that falls back has
    no row to be listed by. The roster is what makes the second half sayable.
    """
    payload = client.get(RULES, headers=admin_headers).json()

    assert "sensors" in payload
    ids = {entry["id"] for entry in payload["sensors"]}
    assert str(sensor_id) in ids, "a sensor with no rule of its own is missing"

    entry = next(e for e in payload["sensors"] if e["id"] == str(sensor_id))
    assert entry["label"], "a sensor with no label cannot be chosen from a list"
    assert entry["machine_name"] == "Test Pump"
    assert entry["machine_type"] == "pump"


def test_a_sensor_can_be_given_its_own_limit(client, admin_headers, sensor_id, feature_code):
    response = client.post(
        RULES,
        headers=admin_headers,
        json={"feature_code": feature_code, "sensor_id": str(sensor_id), "normal_max": 1.5},
    )
    assert response.status_code == 201, response.text

    created = response.json()
    assert created["sensor_id"] == str(sensor_id)
    assert created["equipment_id"] is None
    assert created["channel"] is None


def test_a_sensor_rule_is_not_refused_as_a_duplicate_of_the_global_one(
    client, admin_headers, sensor_id, feature_code
):
    """The check that used to compare feature and channel only.

    A global rule for this feature already exists — every feature has one. It
    and a sensor rule are different rows at different scopes, so matching on
    feature and channel alone reported the global rule as a duplicate and
    refused to create the sensor rule at all.
    """
    first = client.post(
        RULES,
        headers=admin_headers,
        json={"feature_code": feature_code, "sensor_id": str(sensor_id), "normal_max": 1.5},
    )
    assert first.status_code == 201, first.text

    # The same scope twice is a genuine duplicate and is still refused.
    again = client.post(
        RULES,
        headers=admin_headers,
        json={"feature_code": feature_code, "sensor_id": str(sensor_id), "normal_max": 2.5},
    )
    assert again.status_code == 409, again.text


def test_a_rule_cannot_name_a_sensor_and_a_machine_at_once(
    client, admin_headers, sensor_id, feature_code
):
    # A sensor already belongs to one machine, so a rule naming both would
    # either repeat itself or contradict itself. The database has a CHECK; the
    # API should not need it to fire.
    response = client.post(
        RULES,
        headers=admin_headers,
        json={
            "feature_code": feature_code,
            "sensor_id": str(sensor_id),
            "equipment_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 422, response.text


def test_a_rule_cannot_be_written_for_a_sensor_that_does_not_exist(
    client, admin_headers, feature_code
):
    # Otherwise the rule is written for a machine nobody can find, and silently
    # never fires — the failure this whole ticket is about.
    response = client.post(
        RULES,
        headers=admin_headers,
        json={"feature_code": feature_code, "sensor_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422, response.text


def test_the_list_can_be_narrowed_to_one_sensor(
    client, admin_headers, sensor_id, feature_code
):
    client.post(
        RULES,
        headers=admin_headers,
        json={"feature_code": feature_code, "sensor_id": str(sensor_id), "normal_max": 1.5},
    )

    response = client.get(RULES, headers=admin_headers, params={"sensor_id": str(sensor_id)})
    assert response.status_code == 200, response.text

    items = response.json()["items"]
    assert items, "the sensor's own rule was not returned"
    assert all(item["sensor_id"] == str(sensor_id) for item in items)


def test_a_sensors_own_limit_can_be_removed_again(
    client, admin_headers, sensor_id, feature_code
):
    """A limit that cannot be undone is a trap.

    "Global" used to be decided on channel and machine type alone, and a sensor
    rule has both of those null — so deleting one came back 409 "Global rules
    cannot be deleted". The sensor could be given its own limit and then never
    returned to the broader one.
    """
    created = client.post(
        RULES,
        headers=admin_headers,
        json={"feature_code": feature_code, "sensor_id": str(sensor_id), "normal_max": 1.5},
    )
    assert created.status_code == 201, created.text

    removed = client.delete(f"{RULES}/{created.json()['id']}", headers=admin_headers)
    assert removed.status_code in (200, 204), removed.text


def test_the_global_rule_is_still_protected(client, admin_headers, feature_code):
    # Removing it would leave the feature with no limits at all, which reads as
    # "healthy" rather than "unmonitored".
    rules = client.get(RULES, headers=admin_headers).json()["items"]
    global_rule = next(
        r
        for r in rules
        if r["feature_code"] == feature_code
        and r["channel"] is None
        and r["sensor_id"] is None
        and r["equipment_id"] is None
        and not r["machine_type"]
    )

    response = client.delete(f"{RULES}/{global_rule['id']}", headers=admin_headers)
    assert response.status_code == 409, response.text
