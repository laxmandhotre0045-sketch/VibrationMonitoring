"""Persist and evaluate channel features + segment trends."""
from __future__ import annotations

import logging

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.crud import baseline as baseline_crud
from app.crud import feature as feature_crud
from app.models.measurement import (
    BaselineChannelFeature,
    MeasurementChannelFeature,
    MeasurementChannelFeatureTrend,
    SensorBaseline,
    SensorDataUpload,
)
from app.services.feature_extraction import (
    FEATURE_CODES,
    extract_all_channel_trends,
    extract_all_channels,
)
from app.services.plot_generator import load_parsed_data
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
    """Compute features on demand for legacy uploads that are still pending."""
    if upload.features_status == "ready":
        existing = feature_crud.get_measurement_features(db, upload.id)
        if existing:
            return upload

    if upload.parse_status != "parsed":
        raise ValueError(f"Upload not parsed: {upload.parse_status}")

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


def persist_upload_features_and_trends(
    db: Session,
    upload: SensorDataUpload,
    parsed_data: dict[str, Any],
    sampling_rate_hz: float,
) -> tuple[int, int]:
    """Extract scalars + segment trends for all channels. Returns (feature_rows, trend_rows)."""
    rules = feature_crud.get_active_threshold_rules(db)
    rules_map = {r.feature_code: r for r in rules}
    baseline_refs = _baseline_ref_map(db, upload.sensor_id)

    scalars = extract_all_channels(parsed_data, upload.channel_count, sampling_rate_hz)
    trends = extract_all_channel_trends(parsed_data, upload.channel_count, sampling_rate_hz)

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
            rule = rules_map.get(code)
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
    summary = {"normal": 0, "warning": 0, "critical": 0, "no_baseline": 0}
    for r in rows:
        key = r.status if r.status in summary else "normal"
        summary[key] = summary.get(key, 0) + 1
    summary["total"] = len(rows)
    return summary
