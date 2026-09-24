"""Sensor resolution, flattening and the agent envelope, against a stub platform.

No network: a FakePlatformClient stands in for the REST API, so these run
offline like the rest of the default suite.
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from sql_agent.agent import SensorDataAgent, _preview
from sql_agent.dataset import (
    CSV_COLUMNS,
    build_sensor_index,
    collect_sensor_dataset,
    dataset_to_csv,
    schema_report,
    rows_to_csv,
    dataset_to_rows,
    resolve_sensor,
    summarize,
)

PUMP_SENSOR = "1fbf407a-093d-4ed0-b0cc-c61c83fdcbb9"
FAN_SENSOR = "2abc407a-093d-4ed0-b0cc-c61c83fdcbb9"


class FakePlatformClient:
    """Two machines, one sensor each; the pump has two captures, the fan none."""

    def __init__(self) -> None:
        self.equipment = {
            "eq-pump": {
                "id": "eq-pump",
                "machine_name": "Cooling Water Pump 1",
                "machine_id": "CWP-001",
                "machine_type": "Pump",
                "plant_name": "Pune",
                "area": "Utilities",
                "line": "Cooling Water",
                "sensors": [
                    {
                        "id": PUMP_SENSOR,
                        "device_id": "AA:BB:CC:00:11:22",
                        "mounting_location": "Pump Casing",
                        "orientation": "Horizontal",
                        "sensor_type": "IEPE Accelerometer",
                        "is_active": True,
                    }
                ],
            },
            "eq-fan": {
                "id": "eq-fan",
                "machine_name": "ID Fan 2",
                "machine_id": "IDF-002",
                "machine_type": "Fan",
                "plant_name": "Pune",
                "area": "Boiler",
                "line": "Draft",
                "sensors": [
                    {
                        "id": FAN_SENSOR,
                        "device_id": None,
                        "mounting_location": "Bearing Housing DE",
                        "orientation": "Vertical",
                        "sensor_type": "IEPE Accelerometer",
                        "is_active": True,
                    }
                ],
            },
        }
        self.uploads = {
            PUMP_SENSOR: [
                {
                    "id": "up-2",
                    "sensor_id": PUMP_SENSOR,
                    "original_filename": "b.csv",
                    "source": "device",
                    "channel_count": 2,
                    "sample_count": 8192,
                    "features_status": "ready",
                    "created_at": "2026-09-02T10:00:00Z",
                    "measured_at": "2026-09-02T09:30:00Z",
                    "rotation_speed_rpm": 1480,
                },
                {
                    "id": "up-1",
                    "sensor_id": PUMP_SENSOR,
                    "original_filename": "a.csv",
                    "source": "manual",
                    "channel_count": 2,
                    "sample_count": 8192,
                    "features_status": "failed",
                    "created_at": "2026-09-01T10:00:00Z",
                    "measured_at": None,
                    "rotation_speed_rpm": None,
                },
            ],
            FAN_SENSOR: [],
        }
        self.features = {
            "up-2": [
                {
                    "channel": 0,
                    "feature_code": "rms",
                    "feature_name": "RMS",
                    "value": 0.0349,
                    "unit": "scaled_eng",
                    "status": "critical",
                    "computed_at": "2026-09-02T10:00:05Z",
                    "metadata": {"estimated_shaft_hz": 25.0},
                },
                {
                    "channel": 1,
                    "feature_code": "rms",
                    "feature_name": "RMS",
                    "value": 0.0121,
                    "unit": "scaled_eng",
                    "status": "normal",
                    "computed_at": "2026-09-02T10:00:05Z",
                    "metadata": {"estimated_shaft_hz": 25.0},
                },
            ]
        }

    def list_equipment(self, page_size: int = 100):
        return list(self.equipment.values())

    def get_equipment(self, equipment_id: str):
        return self.equipment[equipment_id]

    def list_sensors(self, equipment_id: str):
        return self.equipment[equipment_id]["sensors"]

    def list_uploads(self, sensor_id: str, *, limit: int, from_date=None, to_date=None):
        rows = self.uploads.get(sensor_id, [])
        return rows[:limit], len(rows)

    def get_upload_features(self, upload_id: str):
        return self.features.get(upload_id, [])

    def get_plot_config(self, sensor_id: str):
        return {"sampling_rate_hz": 25600.0}

    def get_baselines(self, sensor_id: str):
        return []


@pytest.fixture
def client():
    return FakePlatformClient()


# ------------------------------------------------------------- resolution --


def test_index_lists_every_sensor(client):
    index = build_sensor_index(client)
    assert {e["sensor_id"] for e in index} == {PUMP_SENSOR, FAN_SENSOR}
    assert index[0]["machine_name"]


def test_resolve_by_uuid(client):
    assert resolve_sensor(client, PUMP_SENSOR)["sensor_id"] == PUMP_SENSOR


def test_resolve_by_device_id(client):
    assert resolve_sensor(client, "AA:BB:CC:00:11:22")["sensor_id"] == PUMP_SENSOR


def test_resolve_by_free_text(client):
    assert resolve_sensor(client, "cooling water pump")["sensor_id"] == PUMP_SENSOR


def test_resolve_all_terms_must_match(client):
    """'pune vertical' must reach the fan, not the pump that also sits in Pune."""
    assert resolve_sensor(client, "pune vertical")["sensor_id"] == FAN_SENSOR


def test_ambiguous_query_raises_and_names_options(client):
    with pytest.raises(LookupError) as exc:
        resolve_sensor(client, "pune")
    assert "matches 2 sensors" in str(exc.value)
    assert PUMP_SENSOR in str(exc.value)


def test_unknown_sensor_raises(client):
    with pytest.raises(LookupError):
        resolve_sensor(client, "turbine 9")


def test_empty_query_raises(client):
    with pytest.raises(LookupError):
        resolve_sensor(client, "   ")


# ------------------------------------------------------------------- csv ---


def test_csv_header_starts_with_the_preferred_columns(client):
    """The preferred columns keep their names and order; extras follow them.

    The export is derived from the data now rather than from a fixed list, so
    the header is not equal to CSV_COLUMNS -- it starts with it. Anything the
    platform returns beyond that appears after, instead of being discarded.
    """
    entry = resolve_sensor(client, PUMP_SENSOR)
    text = dataset_to_csv(collect_sensor_dataset(client, entry))
    header = next(csv.reader(io.StringIO(text)))
    assert header[: len(CSV_COLUMNS)] == CSV_COLUMNS
    assert len(header) >= len(CSV_COLUMNS)


def test_new_platform_field_reaches_the_csv_without_a_code_change(client):
    """The whole point: a field nobody declared must not be dropped.

    This is the regression the old exporter could not have passed. It carried a
    fixed list and DictWriter(extrasaction="ignore"), so a value the platform
    added -- as it had, with the shaft speed -- vanished in transit.
    """
    entry = resolve_sensor(client, PUMP_SENSOR)
    dataset = collect_sensor_dataset(client, entry)
    for features in dataset.features_by_upload.values():
        for f in features:
            f["a_brand_new_field"] = "kept"

    rows = dataset_to_rows(dataset)
    assert any(r.get("a_brand_new_field") == "kept" for r in rows)

    reader = csv.DictReader(io.StringIO(rows_to_csv(rows)))
    assert "a_brand_new_field" in (reader.fieldnames or [])
    assert any(r["a_brand_new_field"] == "kept" for r in reader)


def test_schema_report_names_what_it_discovered(client):
    entry = resolve_sensor(client, PUMP_SENSOR)
    rows = dataset_to_rows(collect_sensor_dataset(client, entry))
    report = schema_report(rows)
    assert report["column_count"] == len(report["columns"])
    assert not report["missing"], "a preferred column disappeared from the export"
    # metadata carries the platform's shaft-speed estimate and is exactly the
    # kind of field the old fixed list dropped.
    assert "metadata" in report["discovered"]


def test_nested_values_survive_as_json(client):
    """metadata is a dict; it must round-trip, not arrive as a Python repr."""
    entry = resolve_sensor(client, PUMP_SENSOR)
    rows = dataset_to_rows(collect_sensor_dataset(client, entry))
    text = rows_to_csv(rows)
    row = next(r for r in csv.DictReader(io.StringIO(text)) if r.get("metadata"))
    assert isinstance(json.loads(row["metadata"]), dict)


def test_every_row_carries_the_sensor_id(client):
    """The point of the export: detached from chat, each row still identifies itself."""
    entry = resolve_sensor(client, PUMP_SENSOR)
    rows = dataset_to_rows(collect_sensor_dataset(client, entry))
    assert rows and all(r["sensor_id"] == PUMP_SENSOR for r in rows)
    assert all(r["machine_name"] == "Cooling Water Pump 1" for r in rows)


def test_rows_are_ordered_by_observed_at(client):
    entry = resolve_sensor(client, PUMP_SENSOR)
    rows = dataset_to_rows(collect_sensor_dataset(client, entry))
    observed = [r["observed_at"] for r in rows]
    assert observed == sorted(observed)


def test_capture_without_features_still_appears(client):
    """up-1 failed extraction - it must be visible as a row, not silently dropped."""
    entry = resolve_sensor(client, PUMP_SENSOR)
    rows = dataset_to_rows(collect_sensor_dataset(client, entry))
    failed = [r for r in rows if r["upload_id"] == "up-1"]
    assert len(failed) == 1
    assert failed[0]["status"] == "failed"
    assert failed[0]["feature_code"] == ""


def test_measured_at_wins_over_created_at(client):
    entry = resolve_sensor(client, PUMP_SENSOR)
    rows = dataset_to_rows(collect_sensor_dataset(client, entry))
    up2 = next(r for r in rows if r["upload_id"] == "up-2")
    assert up2["observed_at"] == "2026-09-02T09:30:00Z"
    up1 = next(r for r in rows if r["upload_id"] == "up-1")
    assert up1["observed_at"] == "2026-09-01T10:00:00Z"  # falls back to created_at


def test_sensor_with_no_captures_exports_empty_but_valid(client):
    entry = resolve_sensor(client, FAN_SENSOR)
    dataset = collect_sensor_dataset(client, entry)
    rows = dataset_to_rows(dataset)
    assert rows == []
    assert next(csv.reader(io.StringIO(dataset_to_csv(dataset)))) == CSV_COLUMNS


# --------------------------------------------------------------- summary ---


def test_summary_counts_and_statuses(client):
    entry = resolve_sensor(client, PUMP_SENSOR)
    dataset = collect_sensor_dataset(client, entry)
    s = summarize(dataset, dataset_to_rows(dataset))
    assert s["sensor_id"] == PUMP_SENSOR
    assert s["captures_exported"] == 2
    assert s["csv_rows"] == 3           # 2 features + 1 failed-capture row
    assert s["status_counts"]["critical"] == 1
    assert s["status_counts"]["normal"] == 1
    assert s["channels"] == [0, 1]
    assert s["truncated"] is False


def test_truncation_is_reported(client):
    entry = resolve_sensor(client, PUMP_SENSOR)
    dataset = collect_sensor_dataset(client, entry, max_uploads=1)
    assert dataset.truncated is True
    assert summarize(dataset, dataset_to_rows(dataset))["captures_available"] == 2


# --------------------------------------------------------------- preview ---


def test_preview_is_bounded_and_says_how_much_it_hid():
    text = "h1,h2\n" + "\n".join(f"a{i},b{i}" for i in range(100))
    out = _preview(text, 5)
    assert len(out.splitlines()) == 7          # header + 5 rows + the note
    assert "95 more rows" in out


def test_preview_returns_short_files_whole():
    text = "h1,h2\na,b\n"
    assert _preview(text, 15) == "h1,h2\na,b"


# ---------------------------------------------------------------- export ---


def test_agent_returns_rows_csv_and_caveats(client, tmp_path, monkeypatch):
    monkeypatch.setattr("sql_agent.agent.EXPORTS_DIR", tmp_path)
    result = SensorDataAgent(client).get_sensor_data("cooling water pump", write_csv=True)

    assert result.ok is True
    assert result.kind == "sensor_data"
    assert len(result.data) == 3
    assert result.meta["csv_rows"] == 3
    assert result.meta["columns"] == CSV_COLUMNS
    assert result.meta["caveats"], "callers must always receive the caveats"

    # newline="" so the file's RFC 4180 line endings survive the read instead of
    # being normalised - otherwise this compares a translation, not the bytes.
    with open(result.meta["csv_path"], encoding="utf-8", newline="") as fh:
        assert fh.read() == result.meta["csv"]


def test_agent_reports_failure_as_a_value_not_an_exception(client):
    """A calling agent must not have to wrap every call in try/except."""
    result = SensorDataAgent(client).get_sensor_data("pune")   # ambiguous
    assert result.ok is False
    assert result.data == []
    assert "matches 2 sensors" in (result.error or "")


def test_agent_lists_sensors(client):
    result = SensorDataAgent(client).list_sensors()
    assert result.ok is True
    assert result.meta["count"] == 2


def test_latest_reading_pulls_one_capture(client):
    result = SensorDataAgent(client).get_latest_reading("cooling water pump")
    assert result.ok is True
    assert result.kind == "sensor_latest"
    assert result.meta["captures_exported"] == 1
    assert result.meta["truncated"] is True


def test_result_serialises_to_json(client):
    result = SensorDataAgent(client).list_sensors()
    assert json.loads(result.to_json())["ok"] is True
