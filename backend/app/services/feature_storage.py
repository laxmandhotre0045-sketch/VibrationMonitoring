"""Persist and evaluate channel features + segment trends."""
from __future__ import annotations

import logging

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import crud
from app.ai.shaft_speed import ShaftSpeed, resolve_shaft_speed
from app.crud import baseline as baseline_crud
from app.crud import feature as feature_crud
from app.crud import job as job_crud
from app.models.measurement import (
    BaselineChannelFeature,
    MeasurementChannelFeature,
    MeasurementChannelFeatureTrend,
    SensorBaseline,
    SensorDataUpload,
)
from app.services.feature_extraction import (
    _compute_fft_magnitudes,
    _to_array,
    FEATURE_CODES,
    extract_all_channel_trends,
    extract_all_channels,
)
from app.services.plot_generator import load_parsed_data
from app.services.quality_storage import persist_quality
from app.services.threshold_evaluator import ThresholdRule, evaluate_feature
from app.services.webhook_service import build_alert_payload, dispatch_alert

logger = logging.getLogger(__name__)


def _load_parsed_for_upload(db: Session, upload: SensorDataUpload) -> dict[str, Any]:
    upload_data = baseline_crud.get_upload_data_by_upload_id(db, upload.id)
    if upload_data and upload_data.parsed_data:
        return upload_data.parsed_data
    if upload.parsed_data_path:
        try:
            return load_parsed_data(upload.parsed_data_path)
        except (FileNotFoundError, OSError, ValueError):
            pass
    raise ValueError("No parsed data available for this upload")


def ensure_upload_features_ready(
    db: Session,
    upload: SensorDataUpload,
    sampling_rate_hz: float,
) -> SensorDataUpload:
    """Compute features on demand for uploads that have nobody else to do it.

    Uploads made before the worker existed have no job row, and nothing will
    ever compute their features unless a read does — that is what this is for.

    A *queued or running* job is the opposite case: the worker owns this
    upload, and computing here as well would have two processes writing the
    same feature rows from two connections. The upload is returned untouched so
    the endpoint answers with its recorded ``pending`` status, which is the
    signal the UI is already polling on.
    """
    if upload.features_status == "ready":
        existing = feature_crud.get_measurement_features(db, upload.id)
        if existing:
            return upload

    if upload.parse_status != "parsed":
        raise ValueError(f"Upload not parsed: {upload.parse_status}")

    if job_crud.has_active_job(db, upload.id):
        return upload

    if upload.features_status == "failed":
        upload.features_status = "pending"
        upload.features_error = None
        db.commit()
        db.refresh(upload)

    parsed = _load_parsed_for_upload(db, upload)
    persist_upload_features_and_trends(db, upload, parsed, sampling_rate_hz)
    updated = feature_crud.mark_upload_features_ready(db, upload.id)
    if not updated:
        raise ValueError("Upload not found after feature compute")
    return updated


def _baseline_ref_map(db: Session, sensor_id: UUID) -> dict[tuple[int, str], float]:
    primary = baseline_crud.get_primary_baseline(db, sensor_id)
    if not primary:
        return {}
    rows = feature_crud.get_baseline_features(db, primary.id)
    return {(r.channel, r.feature_code): float(r.value) for r in rows}


def machine_shaft_speed(db: Session, upload: SensorDataUpload,
                        parsed_data: dict[str, Any],
                        sampling_rate_hz: float) -> ShaftSpeed:
    """The shaft speed for this capture, from the machine record.

    This is the only layer that knows which machine a sensor is bolted to, so
    it is where the nameplate enters the calculation. Without it every order
    in the platform is computed against the tallest line in the spectrum,
    which on the test pump is 2x or 4x the true speed on all eight channels.

    The spectrum of channel 0 is used as the cross-check on the nameplate --
    one channel, not eight, because the answer is a property of the shaft
    rather than of any transducer, and computing eight transforms to agree
    with each other would cost eight times as much for the same number.
    """
    measured = getattr(upload, "rotation_speed_rpm", None)

    nameplate = operating_min = operating_max = None
    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    if sensor is not None and getattr(sensor, "equipment_id", None):
        equipment = db.execute(text("""
            SELECT rated_rpm, operating_speed_min, operating_speed_max
              FROM equipment_masters WHERE id = :eid
        """), {"eid": str(sensor.equipment_id)}).fetchone()
        if equipment is not None:
            nameplate = equipment.rated_rpm
            operating_min = equipment.operating_speed_min
            operating_max = equipment.operating_speed_max

    freqs = spectrum = None
    samples = (parsed_data.get("channels") or {}).get("ch0")
    if samples and len(samples) >= 4:
        freqs, spectrum = _compute_fft_magnitudes(_to_array(samples), sampling_rate_hz)

    return resolve_shaft_speed(
        freqs, spectrum,
        measured_rpm=float(measured) if measured else None,
        nameplate_rpm=float(nameplate) if nameplate else None,
        operating_rpm_min=float(operating_min) if operating_min else None,
        operating_rpm_max=float(operating_max) if operating_max else None,
    )


def machine_bearing_orders(db: Session, upload: SensorDataUpload) -> dict | None:
    """FTF/BSF/BPFO/BPFI for the bearing this sensor is watching.

    From the catalogue via VIK-010, which resolved the plant's spelling
    ("6312-C3") onto a real row. The drive end is used: it carries the load
    and is where defects appear first, and a sensor on the casing sees both
    anyway.

    None when no bearing is resolved, which the envelope features report as
    "not looked for" rather than as nothing found. Those are different
    answers and only one of them is reassuring.
    """
    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    if sensor is None or not getattr(sensor, "equipment_id", None):
        return None

    row = db.execute(text("""
        SELECT b.ftf, b.bsf, b.bpfo, b.bpfi, b.designation
          FROM equipment_masters e
          JOIN bearing_fault_frequencies b
            ON b.source_bearing_id = e.bearing_de_catalog_id
         WHERE e.id = :eid
    """), {"eid": str(sensor.equipment_id)}).fetchone()
    if row is None:
        return None

    orders = {name: (float(getattr(row, name)) if getattr(row, name) is not None else None)
              for name in ("ftf", "bsf", "bpfo", "bpfi")}
    if not any(orders.values()):
        return None
    orders["designation"] = row.designation
    return orders


def persist_upload_features_and_trends(
    db: Session,
    upload: SensorDataUpload,
    parsed_data: dict[str, Any],
    sampling_rate_hz: float,
    with_trends: bool = True,
) -> tuple[int, int]:
    """Extract scalars + segment trends for all channels. Returns (feature_rows, trend_rows).

    `with_trends` exists for backfilling captures that older code never
    analysed. The trend rows are 32 segments x 8 channels x 36 features --
    9,216 per capture, about 3 MB -- and for a historical capture nobody has
    looked at, the features are what baselines and grading read. They can be
    produced later from the same stored samples. The live path leaves this
    on, so nothing about normal ingestion changes.
    """
    # Keyed by (channel, code): a channel with its own override uses it, every
    # other channel falls back to the global rule. See crud.feature.resolve_rule.
    rules_map = feature_crud.get_resolved_rule_map(db)
    baseline_refs = _baseline_ref_map(db, upload.sensor_id)

    machine = machine_shaft_speed(db, upload, parsed_data, sampling_rate_hz)
    bearing_orders = machine_bearing_orders(db, upload)

    # VIK-022, before the features rather than after. The requirement makes
    # "confidence reduced due to poor signal quality" a hard rule, and a rule
    # that runs after the numbers have been produced is an afterthought --
    # every engine downstream reads the level, so the level has to exist by
    # the time the numbers do.
    #
    # It never raises: a capture whose quality could not be judged is still
    # worth keeping, and losing it to the thing that grades it would be the
    # worst outcome available.
    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    quality = persist_quality(
        db,
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        channels=(parsed_data.get("channels") or {}),
        sampling_rate_hz=sampling_rate_hz,
        expected_samples=parsed_data.get("sample_count"),
        sensitivity_mv_per_g=(float(sensor.sensitivity)
                              if sensor is not None and sensor.sensitivity
                              else None),
        shaft_hz=machine.hz if machine.usable else None,
    )
    if quality["level"] != "high":
        logger.info(
            "Data quality for upload %s: %s (x%.2f) -- failing %s%s",
            upload.id, quality["level"], quality["confidence_factor"],
            ", ".join(quality["failed_checks"]) or "nothing",
            (", not assessed: " + ", ".join(quality.get("not_assessed", [])))
            if quality.get("not_assessed") else "",
        )
    logger.info(
        "Shaft speed for upload %s: %s (%s, confidence %.2f)",
        upload.id,
        f"{machine.hz:.3f} Hz" if machine.hz else "unknown",
        machine.source, machine.confidence,
    )

    scalars = extract_all_channels(parsed_data, upload.channel_count,
                                   sampling_rate_hz, machine, bearing_orders)
    trends = (extract_all_channel_trends(parsed_data, upload.channel_count,
                                         sampling_rate_hz, machine, bearing_orders)
              if with_trends else {})

    feature_crud.delete_measurement_features(db, upload.id)
    feature_crud.delete_measurement_feature_trends(db, upload.id)

    now = datetime.utcnow()
    feature_rows: list[MeasurementChannelFeature] = []
    trend_rows: list[MeasurementChannelFeatureTrend] = []
    # Anything that evaluates to warning/critical here is what an alert webhook
    # subscriber is waiting to hear about.
    breached: list[dict] = []

    for channel, features in scalars.items():
        channel_rms = float(features.get("rms", {}).get("value", 0.0))
        channel_trends = trends.get(channel, {})

        for code in FEATURE_CODES:
            payload = features.get(code)
            if not payload:
                continue
            rule = feature_crud.resolve_rule(rules_map, channel, code)
            baseline_val = baseline_refs.get((channel, code))
            status = "normal"
            if rule:
                status = evaluate_feature(
                    code,
                    float(payload["value"]),
                    ThresholdRule.from_row(rule),
                    channel_rms=channel_rms,
                    baseline_value=baseline_val,
                )

            if status in ("warning", "critical"):
                breached.append({
                    "channel": channel,
                    "feature_code": code,
                    "value": float(payload["value"]),
                    "unit": payload["unit"],
                    "status": status,
                })

            feature_rows.append(
                MeasurementChannelFeature(
                    upload_id=upload.id,
                    sensor_id=upload.sensor_id,
                    channel=channel,
                    feature_code=code,
                    value=payload["value"],
                    unit=payload["unit"],
                    status=status,
                    metadata_=payload.get("metadata") or {},
                    computed_at=now,
                )
            )

            trend_payload = channel_trends.get(code)
            if trend_payload:
                for seg_idx, (time_s, val) in enumerate(
                    zip(trend_payload["trend_x"], trend_payload["trend_y"])
                ):
                    trend_rows.append(
                        MeasurementChannelFeatureTrend(
                            upload_id=upload.id,
                            sensor_id=upload.sensor_id,
                            channel=channel,
                            feature_code=code,
                            segment_index=seg_idx,
                            time_s=time_s,
                            value=val,
                            computed_at=now,
                        )
                    )

    if feature_rows:
        db.bulk_save_objects(feature_rows)
    if trend_rows:
        db.bulk_save_objects(trend_rows)
    db.commit()

    # Fired only after the commit, so a webhook can never describe an alert that
    # was rolled back. Dispatch is backgrounded and never raises into ingestion.
    if breached:
        _notify_alert_webhooks(db, upload, breached)

    return len(feature_rows), len(trend_rows)


def _notify_alert_webhooks(
    db: Session, upload: SensorDataUpload, breached: list[dict]
) -> None:
    try:
        severity = "critical" if any(b["status"] == "critical" for b in breached) else "warning"
        payload = build_alert_payload(
            sensor_id=upload.sensor_id,
            upload_id=upload.id,
            equipment=_equipment_context(db, upload),
            triggered=breached,
        )
        dispatch_alert(db, severity, payload)
    except Exception:  # notification must never fail an ingest
        logger.exception("Alert webhook dispatch failed for upload %s", upload.id)


def _equipment_context(db: Session, upload: SensorDataUpload) -> dict:
    """Enough identity for a receiver to route the alert without calling back."""
    from app.models.equipment import Equipment
    from app.models.sensor import SensorConfiguration

    sensor = (
        db.query(SensorConfiguration)
        .filter(SensorConfiguration.id == upload.sensor_id)
        .first()
    )
    if sensor is None:
        return {}
    equipment = (
        db.query(Equipment).filter(Equipment.id == sensor.equipment_id).first()
        if sensor.equipment_id
        else None
    )
    context = {
        "sensor_type": sensor.sensor_type,
        "sensor_location": sensor.mounting_location,
        "sensor_orientation": sensor.orientation,
        "device_id": sensor.device_id,
    }
    if equipment is not None:
        context.update({
            "equipment_id": str(equipment.id),
            "machine_name": equipment.machine_name,
            "plant": equipment.plant_name,
            "area": equipment.area,
            "line": equipment.line,
            "criticality": equipment.machine_criticality,
        })
    return context


def copy_upload_features_to_baseline(
    db: Session,
    upload_id: UUID,
    baseline: SensorBaseline,
) -> int:
    source = feature_crud.get_measurement_features(db, upload_id)
    if not source:
        return 0

    feature_crud.delete_baseline_features(db, baseline.id)
    now = datetime.utcnow()
    rows = [
        BaselineChannelFeature(
            baseline_id=baseline.id,
            sensor_id=baseline.sensor_id,
            channel=r.channel,
            feature_code=r.feature_code,
            value=r.value,
            unit=r.unit,
            status="normal",
            metadata_=r.metadata_ or {},
            computed_at=now,
        )
        for r in source
    ]
    if rows:
        db.bulk_save_objects(rows)
    db.commit()
    return len(rows)


def features_summary_from_rows(rows: list[MeasurementChannelFeature]) -> dict[str, int]:
    summary = {"normal": 0, "warning": 0, "critical": 0,
               "no_baseline": 0, "not_assessed": 0}
    for r in rows:
        # An unrecognised status counts as not assessed, not as normal.
        # Counting it normal is how twenty-six ungraded features come to
        # read as twenty-six healthy ones on the summary cards.
        key = r.status if r.status in summary else "not_assessed"
        summary[key] += 1
    summary["total"] = len(rows)
    return summary
