"""Flatten everything the platform knows about one sensor into CSV.

A sensor's history is spread across three tables — the machine it is mounted on,
its captures, and the ten features computed per channel per capture. Answering
"give me this sensor's data" means joining all three and keying the result on
sensor_id.

The output is deliberately *long* format — one row per
(capture x channel x feature) — rather than a wide sheet with a column per
feature. Long format survives new feature codes without a header change, sorts
and filters in any spreadsheet, and loads into pandas or a database without
reshaping.

Machine identity is repeated on every row. Redundant in the file, correct for
the reader: a CSV that arrives detached from the app still says which machine,
plant and channel each number came from.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.equipment import Equipment
from app.models.measurement import (
    FeatureDefinition,
    MeasurementChannelFeature,
    SensorDataUpload,
)
from app.models.sensor import SensorConfiguration

#: Identity first, then the capture, then the measurement — so a human scanning
#: left to right reads "which sensor, which capture, what value".
CSV_COLUMNS = [
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

#: Cap on captures pulled per export, newest first. A sensor capturing hourly
#: produces ~720 a month; the response reports when it truncates rather than
#: implying the export is complete.
DEFAULT_MAX_CAPTURES = 500


def list_sensors(db: Session, filter_text: str = "") -> list[dict[str, Any]]:
    """Every sensor with the machine it belongs to — the picker's data source."""
    rows = (
        db.query(SensorConfiguration, Equipment)
        .join(Equipment, Equipment.id == SensorConfiguration.equipment_id)
        .order_by(Equipment.machine_name.asc(), SensorConfiguration.mounting_location.asc())
        .all()
    )
    items = [
        {
            "sensor_id": str(s.id),
            "device_id": s.device_id,
            "mounting_location": s.mounting_location,
            "orientation": s.orientation,
            "sensor_type": s.sensor_type,
            "is_active": bool(s.is_active),
            "equipment_id": str(e.id),
            "machine_name": e.machine_name,
            "machine_id": e.machine_id,
            "machine_type": e.machine_type,
            "plant_name": e.plant_name,
            "area": e.area,
            "line": e.line,
        }
        for s, e in rows
    ]

    terms = [t for t in (filter_text or "").lower().split() if t]
    if not terms:
        return items
    return [
        it
        for it in items
        if all(
            t in " ".join(str(v or "") for v in it.values()).lower() for t in terms
        )
    ]


def _observed_at(upload: SensorDataUpload) -> str:
    """Device capture clock where one was supplied, else server receipt.

    measured_at is the only field that orders a trend correctly — devices buffer
    across dropped links, so created_at records when the network recovered, not
    when the machine was measured.
    """
    stamp = upload.measured_at or upload.created_at
    return stamp.isoformat() if stamp else ""


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def build_sensor_rows(
    db: Session,
    sensor_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    max_captures: int = DEFAULT_MAX_CAPTURES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gather one sensor's full history as flat rows, plus a summary of them.

    Raises LookupError when the sensor does not exist, so the router can turn
    that into a 404 without needing to know about the ORM.
    """
    pair = (
        db.query(SensorConfiguration, Equipment)
        .join(Equipment, Equipment.id == SensorConfiguration.equipment_id)
        .filter(SensorConfiguration.id == sensor_id)
        .first()
    )
    if pair is None:
        raise LookupError(f"No sensor with id {sensor_id}")
    sensor, equipment = pair

    uploads_q = db.query(SensorDataUpload).filter(
        SensorDataUpload.sensor_id == sensor_id
    )
    if from_date is not None:
        uploads_q = uploads_q.filter(SensorDataUpload.created_at >= from_date)
    if to_date is not None:
        uploads_q = uploads_q.filter(SensorDataUpload.created_at <= to_date)

    total_captures = uploads_q.count()
    uploads = (
        uploads_q.order_by(SensorDataUpload.created_at.desc())
        .limit(max_captures)
        .all()
    )

    feature_names = {d.code: d.name for d in db.query(FeatureDefinition).all()}

    upload_ids = [u.id for u in uploads]
    features_by_upload: dict[Any, list[MeasurementChannelFeature]] = {
        uid: [] for uid in upload_ids
    }
    if upload_ids:
        # One query for every capture's features rather than one per capture —
        # an export of 500 captures would otherwise be 500 round trips.
        for f in (
            db.query(MeasurementChannelFeature)
            .filter(MeasurementChannelFeature.upload_id.in_(upload_ids))
            .order_by(
                MeasurementChannelFeature.channel.asc(),
                MeasurementChannelFeature.feature_code.asc(),
            )
            .all()
        ):
            features_by_upload.setdefault(f.upload_id, []).append(f)

    identity = {
        "sensor_id": str(sensor.id),
        "device_id": sensor.device_id or "",
        "machine_id": equipment.machine_id or "",
        "machine_name": equipment.machine_name or "",
        "machine_type": equipment.machine_type or "",
        "plant_name": equipment.plant_name or "",
        "area": equipment.area or "",
        "line": equipment.line or "",
        "mounting_location": sensor.mounting_location or "",
        "orientation": sensor.orientation or "",
        "sensor_type": sensor.sensor_type or "",
    }

    rows: list[dict[str, Any]] = []
    for upload in sorted(uploads, key=_observed_at):
        capture = {
            "upload_id": str(upload.id),
            "source": upload.source or "",
            "original_filename": upload.original_filename or "",
            "observed_at": _observed_at(upload),
            "measured_at": _iso(upload.measured_at),
            "created_at": _iso(upload.created_at),
            "rotation_speed_rpm": (
                float(upload.rotation_speed_rpm)
                if upload.rotation_speed_rpm is not None
                else ""
            ),
            "sample_count": upload.sample_count if upload.sample_count else "",
            "channel_count": upload.channel_count,
        }
        features = features_by_upload.get(upload.id) or []
        if not features:
            # A capture whose feature extraction failed belongs in the export as
            # a row carrying that status, rather than vanishing from the file.
            rows.append(
                {
                    **identity,
                    **capture,
                    "channel": "",
                    "feature_code": "",
                    "feature_name": "",
                    "value": "",
                    "unit": "",
                    "status": upload.features_status or "no_features",
                    "computed_at": "",
                }
            )
            continue
        for f in features:
            rows.append(
                {
                    **identity,
                    **capture,
                    "channel": f.channel,
                    "feature_code": f.feature_code,
                    "feature_name": feature_names.get(f.feature_code, f.feature_code),
                    "value": float(f.value),
                    "unit": f.unit or "",
                    "status": f.status or "",
                    "computed_at": _iso(f.computed_at),
                }
            )

    summary = _summarize(
        rows,
        sensor=sensor,
        equipment=equipment,
        captures_exported=len(uploads),
        captures_available=total_captures,
    )
    return rows, summary


def _summarize(
    rows: list[dict[str, Any]],
    *,
    sensor: SensorConfiguration,
    equipment: Equipment,
    captures_exported: int,
    captures_available: int,
) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    for r in rows:
        s = r.get("status") or ""
        if s:
            statuses[s] = statuses.get(s, 0) + 1

    observed = [r["observed_at"] for r in rows if r.get("observed_at")]
    return {
        "sensor_id": str(sensor.id),
        "machine_name": equipment.machine_name,
        "machine_id": equipment.machine_id,
        "mounting_location": sensor.mounting_location,
        "orientation": sensor.orientation,
        "plant_name": equipment.plant_name,
        "area": equipment.area,
        "line": equipment.line,
        "captures_exported": captures_exported,
        "captures_available": captures_available,
        "truncated": captures_available > captures_exported,
        "csv_rows": len(rows),
        "channels": sorted({r["channel"] for r in rows if r.get("channel") != ""}),
        "feature_codes": sorted({r["feature_code"] for r in rows if r.get("feature_code")}),
        "status_counts": statuses,
        "first_observed_at": min(observed) if observed else None,
        "last_observed_at": max(observed) if observed else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def export_filename(summary: dict[str, Any]) -> str:
    machine = re.sub(r"[^A-Za-z0-9]+", "-", summary.get("machine_name") or "sensor")
    where = re.sub(r"[^A-Za-z0-9]+", "-", summary.get("mounting_location") or "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parts = [p.strip("-") for p in (machine, where) if p.strip("-")]
    return f"{'-'.join(parts) or 'sensor'}-{stamp}.csv".lower()
