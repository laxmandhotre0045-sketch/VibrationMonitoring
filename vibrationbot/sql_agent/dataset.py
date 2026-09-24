"""Collect everything the platform knows about one sensor and flatten it to CSV.

The platform stores a sensor's history across several endpoints - the machine it
is mounted on, its captures, and the ten health features computed per channel
per capture. Answering "give me this sensor's data" means walking all of them
and joining the result back together on sensor_id.

The output is deliberately *long* format - one row per
(capture x channel x feature) - rather than a wide sheet with a column per
feature. Long format survives new feature codes without changing the header,
sorts and filters in any spreadsheet, and loads into pandas or a database
without reshaping. A wide layout looks tidier on screen and is worse at all
three.

Machine identity is repeated on every row. That is redundant in the file and
correct for the reader: a CSV that arrives detached from this conversation still
says which machine, plant and channel each number came from.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sql_agent.config import PLATFORM_MAX_UPLOADS
from sql_agent.client import PlatformClient, PlatformError

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

#: Preferred column order -- NOT a whitelist.
#:
#: The exporter derives its columns from the data it actually received; this
#: list only fixes the order of the columns that existed when it was written,
#: so a human scanning left to right still reads "which sensor, which capture,
#: what value". Any field the platform adds later is discovered at runtime and
#: appended after these. Nothing is dropped for being absent from this list.
#:
#: The previous design was the opposite -- a fixed list, with
#: ``extrasaction="ignore"`` silently discarding anything not on it. That cost
#: us the shaft speed for weeks: the platform had computed it and stored it in
#: a field this list did not mention, so it was thrown away in transit and the
#: machine's speed appeared to be unknown.
PREFERRED_COLUMN_ORDER = [
    "sensor_id",
    "device_id",
    "machine_id",
    "machine_name",
    "machine_type",
    "plant_name",
    "area",
    "line",
    "mounting_location",
    "orientation",
    "sensor_type",
    "upload_id",
    "source",
    "original_filename",
    "observed_at",
    "measured_at",
    "created_at",
    "rotation_speed_rpm",
    "sample_count",
    "channel_count",
    "channel",
    "feature_code",
    "feature_name",
    "value",
    "unit",
    "status",
    "computed_at",
]

#: Retained under the old name so existing callers keep working. It is now the
#: preferred *order*, not the set of columns that will be written.
CSV_COLUMNS = PREFERRED_COLUMN_ORDER

#: Fields renamed on the way out, because the API's own name is ambiguous once
#: four objects are flattened into one row: every one of them has an ``id``.
#: This is a naming decision, not a schema listing -- a field absent from here
#: is still exported, under its own name.
#: Timestamps are renamed at their source rather than left to collide. Every
#: one of these four objects has a ``created_at``, and relying on merge order to
#: decide the winner makes the meaning of the column depend on the order of the
#: code. A row describes one feature reading taken in one capture, so the
#: capture owns the unqualified ``created_at`` -- which is also what this export
#: has always meant by it.
_RENAME = {
    "sensor": {
        "id": "sensor_id",
        "created_at": "sensor_created_at",
        "updated_at": "sensor_updated_at",
    },
    "equipment": {
        "id": "equipment_id",
        "created_at": "equipment_created_at",
        "updated_at": "equipment_updated_at",
    },
    "upload": {"id": "upload_id"},
    "feature": {"id": "feature_row_id"},
}

#: Dropped deliberately, with a reason. Large binary payloads and parsed sample
#: arrays would each turn one CSV cell into megabytes.
#: Deliberately dropped, and only these: payloads whose single cell would run
#: to megabytes. Paths and identifiers are kept -- they are small, and a rule
#: that drops anything merely because it looks uninteresting is the habit this
#: change exists to break.
_SKIP = {
    "sensor": set(),
    # "sensors" is the equipment's list of its own children. Carrying it would
    # repeat every sibling sensor's record inside every row of this sensor's
    # export -- large, and not a fact about the row.
    "equipment": {"sensors"},
    "upload": {"parsed_data", "file_content"},
    "feature": set(),
}

#: Where a name collides across two sources, the later one is qualified with
#: this prefix rather than overwriting. ``created_at`` exists on the equipment,
#: the capture and the feature; without this, two of the three would be lost.
_ORIGIN_PREFIX = {
    "sensor": "sensor",
    "equipment": "equipment",
    "upload": "upload",
    "feature": "feature",
}


@dataclass
class SensorDataset:
    """Everything gathered for one sensor, before flattening."""

    sensor: dict[str, Any]
    equipment: dict[str, Any]
    uploads: list[dict[str, Any]] = field(default_factory=list)
    features_by_upload: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    plot_config: dict[str, Any] | None = None
    baselines: list[dict[str, Any]] = field(default_factory=list)
    total_uploads: int = 0
    truncated: bool = False

    @property
    def sensor_id(self) -> str:
        return str(self.sensor.get("id", ""))

    @property
    def label(self) -> str:
        machine = self.equipment.get("machine_name") or "unknown machine"
        where = self.sensor.get("mounting_location") or "unknown location"
        orient = self.sensor.get("orientation") or ""
        return f"{machine} - {where}{f' ({orient})' if orient else ''}"

    def row_count(self) -> int:
        return sum(len(v) for v in self.features_by_upload.values())


# --------------------------------------------------------------------------
# Resolving a sensor from whatever the user typed
# --------------------------------------------------------------------------


def build_sensor_index(client: PlatformClient) -> list[dict[str, Any]]:
    """Flat sensor inventory: every sensor with the machine it belongs to.

    The platform has no global sensor list endpoint - sensors hang off
    equipment - so this walks the equipment list once and fans out. Cheap at
    plant scale and it is what makes "the pump's horizontal sensor" resolvable.
    """
    index: list[dict[str, Any]] = []
    for eq in client.list_equipment():
        eq_id = str(eq.get("id"))
        try:
            sensors = client.list_sensors(eq_id)
        except PlatformError as exc:
            logger.warning("Could not list sensors for equipment %s: %s", eq_id, exc)
            continue
        for s in sensors:
            index.append(
                {
                    "sensor_id": str(s.get("id")),
                    "device_id": s.get("device_id"),
                    "mounting_location": s.get("mounting_location"),
                    "orientation": s.get("orientation"),
                    "sensor_type": s.get("sensor_type"),
                    "is_active": s.get("is_active", True),
                    "equipment_id": eq_id,
                    "machine_name": eq.get("machine_name"),
                    "machine_id": eq.get("machine_id"),
                    "machine_type": eq.get("machine_type"),
                    "plant_name": eq.get("plant_name"),
                    "area": eq.get("area"),
                    "line": eq.get("line"),
                }
            )
    return index


def resolve_sensor(client: PlatformClient, query: str) -> dict[str, Any]:
    """Find one sensor from a UUID, a device id, or free text.

    Raises when the text matches several sensors rather than picking one. An
    export silently taken from the wrong bearing is worse than a question.
    """
    q = (query or "").strip()
    if not q:
        raise LookupError("No sensor was named. Say which sensor you want.")

    index = build_sensor_index(client)
    if not index:
        raise LookupError(
            "The platform has no sensors registered yet, so there is nothing to export."
        )

    if _UUID_RE.match(q):
        for entry in index:
            if entry["sensor_id"].lower() == q.lower():
                return entry
        raise LookupError(f"No sensor has the id {q}.")

    lowered = q.lower()

    for entry in index:
        if (entry.get("device_id") or "").lower() == lowered:
            return entry

    # Every word must appear somewhere in the sensor's description, so
    # "pump horizontal" narrows rather than matching either word alone.
    terms = [t for t in re.split(r"\s+", lowered) if t]
    matches = []
    for entry in index:
        haystack = " ".join(
            str(entry.get(k) or "")
            for k in (
                "machine_name",
                "machine_id",
                "machine_type",
                "mounting_location",
                "orientation",
                "plant_name",
                "area",
                "line",
            )
        ).lower()
        if all(t in haystack for t in terms):
            matches.append(entry)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        available = ", ".join(
            f"{e['machine_name']} / {e['mounting_location']}" for e in index[:8]
        )
        raise LookupError(
            f"No sensor matches {q!r}. Sensors available: {available}"
            + (" ..." if len(index) > 8 else "")
        )

    options = "; ".join(
        f"{m['machine_name']} / {m['mounting_location']} ({m['orientation']}) "
        f"id={m['sensor_id']}"
        for m in matches[:8]
    )
    raise LookupError(
        f"{q!r} matches {len(matches)} sensors - say which one: {options}"
    )


# --------------------------------------------------------------------------
# Collecting
# --------------------------------------------------------------------------


def collect_sensor_dataset(
    client: PlatformClient,
    sensor_entry: dict[str, Any],
    *,
    max_uploads: int = PLATFORM_MAX_UPLOADS,
    from_date: str | None = None,
    to_date: str | None = None,
) -> SensorDataset:
    """Walk every endpoint that holds data for this sensor."""
    equipment = client.get_equipment(sensor_entry["equipment_id"])
    sensor = next(
        (
            s
            for s in (equipment.get("sensors") or [])
            if str(s.get("id")) == sensor_entry["sensor_id"]
        ),
        None,
    )
    if sensor is None:
        raise LookupError(
            f"Sensor {sensor_entry['sensor_id']} is no longer on "
            f"{equipment.get('machine_name')!r}."
        )

    uploads, total = client.list_uploads(
        sensor_entry["sensor_id"],
        limit=max_uploads,
        from_date=from_date,
        to_date=to_date,
    )

    features_by_upload: dict[str, list[dict[str, Any]]] = {}
    for upload in uploads:
        upload_id = str(upload.get("id"))
        # A capture whose feature extraction failed still belongs in the export
        # as a row of the upload with no measurements, rather than vanishing.
        if upload.get("features_status") != "ready":
            features_by_upload[upload_id] = []
            continue
        try:
            features_by_upload[upload_id] = client.get_upload_features(upload_id)
        except PlatformError as exc:
            logger.warning("Features unavailable for upload %s: %s", upload_id, exc)
            features_by_upload[upload_id] = []

    return SensorDataset(
        sensor=sensor,
        equipment=equipment,
        uploads=uploads,
        features_by_upload=features_by_upload,
        plot_config=client.get_plot_config(sensor_entry["sensor_id"]),
        baselines=client.get_baselines(sensor_entry["sensor_id"]),
        total_uploads=total,
        truncated=total > len(uploads),
    )


# --------------------------------------------------------------------------
# Flattening
# --------------------------------------------------------------------------


def _observed_at(upload: dict[str, Any]) -> str:
    """The capture clock when the device supplied one, else server receipt.

    measured_at is the only field that orders a trend correctly - devices buffer
    across dropped links, so created_at reflects when the network recovered, not
    when the machine was measured.
    """
    return upload.get("measured_at") or upload.get("created_at") or ""


def _merge(target: dict[str, Any], source: dict[str, Any], origin: str) -> None:
    """Copy every field of one API object into a row, losing nothing.

    This is the heart of the dynamic export. It does not consult a list of
    fields it expects; it walks whatever the platform actually returned. A
    column the platform adds next month arrives here on its own.

    Collisions are qualified rather than overwritten. ``created_at`` exists on
    the equipment, the capture and the feature, so a plain merge would keep one
    and silently drop two.
    """
    rename = _RENAME.get(origin, {})
    skip = _SKIP.get(origin, set())
    for key, value in source.items():
        if key in skip:
            continue
        name = rename.get(key, key)
        if name in target:
            name = f"{_ORIGIN_PREFIX[origin]}_{name}"
        # None becomes "", as it always has. The old exporter wrote
        # `.get(field) or ""` on every column, and in-process consumers were
        # built against that: they may call .strip() on a machine name that
        # happens to be unset. Nested values are left alone, because metadata
        # has to stay a dict for the report agent to read the shaft speed.
        target[name] = "" if value is None else value


def dataset_to_rows(dataset: SensorDataset) -> list[dict[str, Any]]:
    """Flatten one sensor's data to long format, carrying every field through.

    Order of merge sets precedence for the unqualified names: sensor, then
    equipment, then capture, then the feature reading. That reproduces the
    column names the export has always had, while anything unrecognised still
    reaches the caller instead of being dropped.
    """
    identity: dict[str, Any] = {}
    _merge(identity, dataset.sensor, "sensor")
    _merge(identity, dataset.equipment, "equipment")

    rows: list[dict[str, Any]] = []
    for upload in sorted(dataset.uploads, key=_observed_at):
        upload_id = str(upload.get("id"))
        capture = dict(identity)
        _merge(capture, upload, "upload")
        # Derived rather than copied: the platform offers several time fields
        # and only this one orders a trend correctly.
        capture["observed_at"] = _observed_at(upload)

        features = dataset.features_by_upload.get(upload_id) or []
        if not features:
            row = dict(capture)
            row.update(
                {
                    "channel": "",
                    "feature_code": "",
                    "feature_name": "",
                    "value": "",
                    "unit": "",
                    "status": upload.get("features_status") or "no_features",
                    "computed_at": "",
                }
            )
            rows.append(row)
            continue

        for f in sorted(
            features, key=lambda x: (x.get("channel", 0), x.get("feature_code", ""))
        ):
            row = dict(capture)
            # The feature is the subject of the row and takes the unqualified
            # names for its own fields -- "value", "unit", "status". No renaming
            # is needed here: the collisions that would have forced it are
            # resolved at their source in _RENAME, where the meaning of each
            # column is decided once instead of by the order of these calls.
            _merge(row, f, "feature")
            rows.append(row)
    return rows


def discover_columns(rows: list[dict[str, Any]]) -> list[str]:
    """The columns this export actually has, derived from the rows themselves.

    Preferred names first, in their long-standing order, so a file opened by a
    human or a script reads the way it always has. Everything else follows,
    sorted, so a newly added platform field lands in a stable position rather
    than wherever the first row happened to mention it.
    """
    seen: dict[str, None] = {}
    for row in rows:
        for key in row:
            seen.setdefault(key, None)
    if not seen:
        # A sensor with no captures still owes the reader a valid file with a
        # header, not a blank line. Deriving from the data is right when there
        # is data; with none, the preferred order is the only honest answer.
        return list(PREFERRED_COLUMN_ORDER)
    known = [c for c in PREFERRED_COLUMN_ORDER if c in seen]
    extra = sorted(k for k in seen if k not in set(PREFERRED_COLUMN_ORDER))
    return known + extra


def schema_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What changed between the expected shape and what the platform sent.

    Reported rather than silently absorbed: an export that quietly gains or
    loses a column is how the shaft speed went missing in the first place.
    """
    columns = discover_columns(rows)
    preferred = set(PREFERRED_COLUMN_ORDER)
    present = set(columns)
    return {
        "columns": columns,
        "column_count": len(columns),
        "discovered": [c for c in columns if c not in preferred],
        "missing": [c for c in PREFERRED_COLUMN_ORDER if c not in present],
    }


def _cell(value: Any) -> Any:
    """Render one value for CSV.

    Nested objects are written as JSON rather than Python's repr, so the column
    round-trips through any reader. ``metadata`` is the one that matters: it
    carries the platform's own shaft-speed estimate.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), default=str)
    return value


def rows_to_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    """Write rows to CSV using the columns the data actually has."""
    fieldnames = columns or discover_columns(rows)
    buf = io.StringIO(newline="")
    # restval covers a row that lacks a column another row has -- which happens
    # the moment the platform starts returning a new field partway through a
    # window. extrasaction is no longer needed: the fieldnames came from the
    # rows, so there is nothing extra to ignore.
    writer = csv.DictWriter(buf, fieldnames=fieldnames, restval="")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(v) for k, v in row.items() if k in fieldnames})
    return buf.getvalue()


def dataset_to_csv(dataset: SensorDataset) -> str:
    return rows_to_csv(dataset_to_rows(dataset))


def summarize(dataset: SensorDataset, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts and status tallies - what the model is allowed to say about the file."""
    statuses: dict[str, int] = {}
    for r in rows:
        s = r.get("status") or ""
        if s:
            statuses[s] = statuses.get(s, 0) + 1

    observed = [r["observed_at"] for r in rows if r.get("observed_at")]
    channels = sorted({r["channel"] for r in rows if r.get("channel") != ""})
    features = sorted({r["feature_code"] for r in rows if r.get("feature_code")})

    return {
        "sensor_id": dataset.sensor_id,
        "sensor": dataset.label,
        # Also exposed individually, not just inside the label, so a consumer
        # can group or filter on them without parsing a display string.
        "mounting_location": dataset.sensor.get("mounting_location"),
        "orientation": dataset.sensor.get("orientation"),
        "device_id": dataset.sensor.get("device_id"),
        "machine_name": dataset.equipment.get("machine_name"),
        "machine_id": dataset.equipment.get("machine_id"),
        "plant_name": dataset.equipment.get("plant_name"),
        "area": dataset.equipment.get("area"),
        "line": dataset.equipment.get("line"),
        "captures_exported": len(dataset.uploads),
        "captures_available": dataset.total_uploads,
        "truncated": dataset.truncated,
        "csv_rows": len(rows),
        "channels": channels,
        "feature_codes": features,
        "status_counts": statuses,
        "first_observed_at": min(observed) if observed else None,
        "last_observed_at": max(observed) if observed else None,
        "baseline_count": len(dataset.baselines),
        "sampling_rate_hz": (dataset.plot_config or {}).get("sampling_rate_hz"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def export_filename(dataset: SensorDataset) -> str:
    machine = re.sub(r"[^A-Za-z0-9]+", "-", dataset.equipment.get("machine_name") or "sensor")
    where = re.sub(r"[^A-Za-z0-9]+", "-", dataset.sensor.get("mounting_location") or "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parts = [p.strip("-") for p in (machine, where) if p.strip("-")]
    return f"{'-'.join(parts) or 'sensor'}-{stamp}.csv".lower()
