from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.equipment import Equipment
from app.models.sensor import SensorConfiguration
from app.models.measurement import (
    SensorDataUpload,
    MeasurementChannelFeature,
    FeatureDefinition,
)
from app.services.threshold_evaluator import (
    STATUS_CRITICAL,
    STATUS_WARNING,
    STATUS_NORMAL,
)

_HEALTH_SCORE = {STATUS_NORMAL: 100.0, STATUS_WARNING: 60.0, STATUS_CRITICAL: 20.0}
_ALERT_STATUSES = (STATUS_WARNING, STATUS_CRITICAL)
_STATUS_RANK = {STATUS_CRITICAL: 3, STATUS_WARNING: 2, STATUS_NORMAL: 1, "no_baseline": 0}


def _latest_upload_per_sensor(db: Session) -> Dict[UUID, SensorDataUpload]:
    """Latest SensorDataUpload row per sensor_id."""
    rows = db.query(SensorDataUpload).order_by(SensorDataUpload.created_at.desc()).all()
    latest: Dict[UUID, SensorDataUpload] = {}
    for row in rows:
        if row.sensor_id not in latest:
            latest[row.sensor_id] = row
    return latest


def get_dashboard_summary(db: Session, alert_limit: int = 20, activity_limit: int = 10):
    equipment_list = db.query(Equipment).order_by(Equipment.machine_name.asc()).all()
    sensors = db.query(SensorConfiguration).all()
    sensors_by_equipment: Dict[UUID, List[SensorConfiguration]] = {}
    for sensor in sensors:
        sensors_by_equipment.setdefault(sensor.equipment_id, []).append(sensor)

    latest_upload_by_sensor = _latest_upload_per_sensor(db)

    feature_names = {d.code: d.name for d in db.query(FeatureDefinition).all()}

    equipment_health = []
    counts = {"critical": 0, "warning": 0, "normal": 0, "no_data": 0}
    health_scores: List[float] = []
    alerts = []

    for equipment in equipment_list:
        eq_sensors = sensors_by_equipment.get(equipment.id, [])
        best_upload: Optional[SensorDataUpload] = None
        for sensor in eq_sensors:
            upload = latest_upload_by_sensor.get(sensor.id)
            if upload and (best_upload is None or upload.created_at > best_upload.created_at):
                best_upload = upload

        if best_upload is None:
            counts["no_data"] += 1
            equipment_health.append({
                "equipment_id": equipment.id,
                "machine_name": equipment.machine_name,
                "machine_id": equipment.machine_id,
                "plant_name": equipment.plant_name,
                "area": equipment.area,
                "line": equipment.line,
                "machine_type": equipment.machine_type,
                "status": "no_data",
                "health_score": None,
                "last_upload_at": None,
                "worst_feature_name": None,
            })
            continue

        feature_rows = (
            db.query(MeasurementChannelFeature)
            .filter(MeasurementChannelFeature.upload_id == best_upload.id)
            .all()
        )

        worst_status = "no_baseline"
        worst_row = None
        for row in feature_rows:
            if _STATUS_RANK.get(row.status, 0) > _STATUS_RANK.get(worst_status, 0):
                worst_status = row.status
                worst_row = row

        if worst_status in (STATUS_CRITICAL, STATUS_WARNING, STATUS_NORMAL):
            counts[worst_status] += 1
            health_scores.append(_HEALTH_SCORE[worst_status])
        else:
            counts["no_data"] += 1

        equipment_health.append({
            "equipment_id": equipment.id,
            "machine_name": equipment.machine_name,
            "machine_id": equipment.machine_id,
            "plant_name": equipment.plant_name,
            "area": equipment.area,
            "line": equipment.line,
            "machine_type": equipment.machine_type,
            "status": worst_status,
            "health_score": _HEALTH_SCORE.get(worst_status),
            "last_upload_at": best_upload.created_at,
            "worst_feature_name": feature_names.get(worst_row.feature_code) if worst_row else None,
        })

        for row in feature_rows:
            if row.status in _ALERT_STATUSES:
                alerts.append({
                    "equipment_id": equipment.id,
                    "machine_name": equipment.machine_name,
                    "sensor_id": row.sensor_id,
                    "channel": row.channel,
                    "feature_code": row.feature_code,
                    "feature_name": feature_names.get(row.feature_code),
                    "status": row.status,
                    "value": float(row.value),
                    "unit": row.unit,
                    "computed_at": row.computed_at,
                })

    alerts.sort(key=lambda a: (_STATUS_RANK.get(a["status"], 0), a["computed_at"]), reverse=True)
    alerts = alerts[:alert_limit]

    total = len(equipment_list)
    avg_health = round(sum(health_scores) / len(health_scores), 1) if health_scores else None

    fleet_counts = {
        "total": total,
        "critical": counts["critical"],
        "warning": counts["warning"],
        "normal": counts["normal"],
        "no_data": counts["no_data"],
        "average_health_score": avg_health,
    }

    equipment_by_id = {e.id: e for e in equipment_list}
    sensor_by_id = {s.id: s for s in sensors}

    recent_uploads = (
        db.query(SensorDataUpload)
        .order_by(SensorDataUpload.created_at.desc())
        .limit(activity_limit)
        .all()
    )
    recent_activity = []
    for upload in recent_uploads:
        sensor = sensor_by_id.get(upload.sensor_id)
        equipment = equipment_by_id.get(sensor.equipment_id) if sensor else None
        recent_activity.append({
            "upload_id": upload.id,
            "equipment_id": equipment.id if equipment else None,
            "machine_name": equipment.machine_name if equipment else "Unknown",
            "mounting_location": sensor.mounting_location if sensor else "Unknown",
            "original_filename": upload.original_filename,
            "parse_status": upload.parse_status,
            "features_status": upload.features_status,
            "created_at": upload.created_at,
        })

    return {
        "counts": fleet_counts,
        "equipment_health": equipment_health,
        "alerts": alerts,
        "recent_activity": recent_activity,
    }
