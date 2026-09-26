"""Equipment CRUD, end to end through the API.

Covers the path an operator actually walks — create, read, list, update,
delete, and the sensors hanging off a machine — plus the rules that are easy to
break and quiet when broken: that writes need write access, that `machine_id`
stays unique, and that a delete takes the machine's sensors with it.
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.db

BASE = "/api/v1/equipment"


def _payload(**overrides) -> dict:
    """A valid machine. Overridable per test so intent stays in the test."""
    body = {
        "plant_name": "Test Plant",
        "area": "Utilities",
        "line": "Cooling",
        "machine_name": "Cooling Water Pump P-204",
        "machine_id": f"PUMP-{uuid.uuid4().hex[:8].upper()}",
        "machine_type": "Pump",
        "machine_criticality": "High",
        "manufacturer": "KSB",
        "model": "Etanorm SYT 100-250",
        "rated_power_kw": "55.0",
        "rated_rpm": 1480,
        "operating_environment": ["Indoor", "Humid"],
        "sensors": [],
    }
    body.update(overrides)
    return body


def _create(client, headers, **overrides) -> dict:
    response = client.post(BASE + "/", json=_payload(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_create_returns_the_stored_machine(client, admin_headers):
    created = _create(client, admin_headers, machine_name="Boiler Feed Pump")
    assert created["id"]
    assert created["machine_name"] == "Boiler Feed Pump"
    assert created["machine_type"] == "Pump"
    # An ARRAY column round-tripping is worth asserting: it is the one column
    # type here that a non-Postgres database could not carry.
    assert created["operating_environment"] == ["Indoor", "Humid"]


def test_get_returns_what_create_stored(client, admin_headers):
    created = _create(client, admin_headers)
    response = client.get(f"{BASE}/{created['id']}", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["machine_id"] == created["machine_id"]


def test_list_includes_the_new_machine(client, admin_headers):
    created = _create(client, admin_headers)
    response = client.get(BASE + "/", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] >= 1
    assert any(item["id"] == created["id"] for item in body["items"])


def test_update_changes_only_what_it_names(client, admin_headers):
    created = _create(client, admin_headers)
    response = client.patch(
        f"{BASE}/{created['id']}",
        json={"machine_criticality": "Critical"},
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["machine_criticality"] == "Critical"
    assert updated["machine_name"] == created["machine_name"], "an untouched field moved"
    assert updated["machine_id"] == created["machine_id"]


def test_delete_removes_the_machine(client, admin_headers):
    created = _create(client, admin_headers)
    assert client.delete(f"{BASE}/{created['id']}", headers=admin_headers).status_code in (200, 204)
    assert client.get(f"{BASE}/{created['id']}", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------


def test_sensors_can_be_added_listed_and_removed(client, admin_headers):
    machine = _create(client, admin_headers)
    sensor_body = {
        "sensor_type": "IEPE Accelerometer",
        "mounting_location": "Bearing Housing DE",
        "orientation": "Horizontal",
    }

    added = client.post(
        f"{BASE}/{machine['id']}/sensors", json=sensor_body, headers=admin_headers
    )
    assert added.status_code == 201, added.text
    sensor_id = added.json()["id"]

    listed = client.get(f"{BASE}/{machine['id']}/sensors", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert [s["id"] for s in listed.json()] == [sensor_id]

    removed = client.delete(
        f"{BASE}/{machine['id']}/sensors/{sensor_id}", headers=admin_headers
    )
    assert removed.status_code in (200, 204), removed.text
    assert client.get(f"{BASE}/{machine['id']}/sensors", headers=admin_headers).json() == []


def test_sensors_created_with_the_machine_are_stored(client, admin_headers):
    machine = _create(
        client,
        admin_headers,
        sensors=[
            {
                "sensor_type": "IEPE Accelerometer",
                "mounting_location": "Bearing Housing DE",
                "orientation": "Vertical",
            }
        ],
    )
    listed = client.get(f"{BASE}/{machine['id']}/sensors", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["orientation"] == "Vertical"


def test_deleting_a_machine_takes_its_sensors_with_it(client, admin_headers, db):
    """The cascade is declared on the foreign key; this is what proves it runs."""
    from app.models.sensor import SensorConfiguration

    machine = _create(
        client,
        admin_headers,
        sensors=[
            {
                "sensor_type": "IEPE Accelerometer",
                "mounting_location": "Bearing Housing NDE",
                "orientation": "Axial",
            }
        ],
    )
    machine_id = uuid.UUID(machine["id"])
    assert db.query(SensorConfiguration).filter_by(equipment_id=machine_id).count() == 1

    client.delete(f"{BASE}/{machine['id']}", headers=admin_headers)
    db.expire_all()
    assert db.query(SensorConfiguration).filter_by(equipment_id=machine_id).count() == 0


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def test_machine_id_is_unique(client, admin_headers):
    first = _create(client, admin_headers)
    duplicate = client.post(
        BASE + "/", json=_payload(machine_id=first["machine_id"]), headers=admin_headers
    )
    assert duplicate.status_code in (400, 409, 422), duplicate.text


def test_an_unknown_machine_is_a_404_not_a_500(client, admin_headers):
    response = client.get(f"{BASE}/{uuid.uuid4()}", headers=admin_headers)
    assert response.status_code == 404


def test_a_malformed_id_is_rejected_cleanly(client, admin_headers):
    response = client.get(f"{BASE}/not-a-uuid", headers=admin_headers)
    assert response.status_code == 422


def test_reading_requires_authentication(client):
    assert client.get(BASE + "/").status_code == 401


def test_writing_requires_authentication(client):
    assert client.post(BASE + "/", json=_payload()).status_code == 401


def test_a_viewer_can_read(client, viewer_headers):
    assert client.get(BASE + "/", headers=viewer_headers).status_code == 200


def test_a_viewer_cannot_write(client, viewer_headers):
    """Read-only means read-only.

    The role check lives in a dependency, which makes it easy to leave off a
    new endpoint — and nothing about the response would look wrong if it were.
    """
    created = client.post(BASE + "/", json=_payload(), headers=viewer_headers)
    assert created.status_code == 403, created.text


def test_a_viewer_cannot_delete(client, admin_headers, viewer_headers):
    machine = _create(client, admin_headers)
    response = client.delete(f"{BASE}/{machine['id']}", headers=viewer_headers)
    assert response.status_code == 403, response.text


def test_ai_readiness_scores_the_machine(client, admin_headers):
    machine = _create(client, admin_headers)
    response = client.get(f"{BASE}/{machine['id']}/ai-readiness", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert 0 <= body["score_percent"] <= 100
