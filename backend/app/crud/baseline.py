from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.measurement import (
    BaselinePlotResult,
    MeasurementUploadData,
    SensorBaseline,
)


def save_upload_data(
    db: Session,
    *,
    upload_id: UUID,
    sensor_id: UUID,
    original_filename: str,
    file_format: str,
    file_content: bytes,
    parsed_data: dict,
    channel_count: int,
    sample_count: int,
) -> MeasurementUploadData:
    row = MeasurementUploadData(
        upload_id=upload_id,
        sensor_id=sensor_id,
        original_filename=original_filename,
        file_format=file_format,
        file_content=file_content,
        parsed_data=parsed_data,
        channel_count=channel_count,
        sample_count=sample_count,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_upload_data_by_upload_id(db: Session, upload_id: UUID) -> Optional[MeasurementUploadData]:
    return (
        db.query(MeasurementUploadData)
        .filter(MeasurementUploadData.upload_id == upload_id)
        .first()
    )


def create_baseline(
    db: Session,
    *,
    sensor_id: UUID,
    source_upload_id: Optional[UUID],
    name: str,
    description: Optional[str],
    labels: List[str],
    original_filename: str,
    file_format: str,
    file_content: bytes,
    parsed_data: dict,
    channel_count: int,
    sample_count: int,
    sampling_rate_hz: float,
    set_as_primary: bool = False,
    captured_at: Optional[datetime] = None,
) -> SensorBaseline:
    if set_as_primary:
        db.query(SensorBaseline).filter(
            SensorBaseline.sensor_id == sensor_id,
            SensorBaseline.is_primary.is_(True),
        ).update({"is_primary": False})

    baseline = SensorBaseline(
        sensor_id=sensor_id,
        source_upload_id=source_upload_id,
        name=name,
        description=description,
        labels=labels or [],
        original_filename=original_filename,
        file_format=file_format,
        file_content=file_content,
        parsed_data=parsed_data,
        channel_count=channel_count,
        sample_count=sample_count,
        sampling_rate_hz=sampling_rate_hz,
        is_primary=set_as_primary,
        captured_at=captured_at or datetime.utcnow(),
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return baseline


def get_baseline_by_id(db: Session, baseline_id: UUID) -> Optional[SensorBaseline]:
    return db.query(SensorBaseline).filter(SensorBaseline.id == baseline_id).first()


def list_baselines_by_sensor(db: Session, sensor_id: UUID) -> List[SensorBaseline]:
    return (
        db.query(SensorBaseline)
        .filter(SensorBaseline.sensor_id == sensor_id)
        .order_by(SensorBaseline.created_at.desc())
        .all()
    )


def get_primary_baseline(db: Session, sensor_id: UUID) -> Optional[SensorBaseline]:
    return (
        db.query(SensorBaseline)
        .filter(SensorBaseline.sensor_id == sensor_id, SensorBaseline.is_primary.is_(True))
        .order_by(SensorBaseline.created_at.desc())
        .first()
    )


def set_baseline_primary(db: Session, baseline_id: UUID, is_primary: bool = True) -> Optional[SensorBaseline]:
    baseline = get_baseline_by_id(db, baseline_id)
    if not baseline:
        return None
    if is_primary:
        db.query(SensorBaseline).filter(
            SensorBaseline.sensor_id == baseline.sensor_id,
            SensorBaseline.is_primary.is_(True),
        ).update({"is_primary": False})
    baseline.is_primary = is_primary
    db.commit()
    db.refresh(baseline)
    return baseline


def delete_baseline_plot_results(
    db: Session,
    baseline_id: UUID,
    config_fingerprint: str | None = None,
) -> int:
    query = db.query(BaselinePlotResult).filter(BaselinePlotResult.baseline_id == baseline_id)
    if config_fingerprint is not None:
        query = query.filter(BaselinePlotResult.config_fingerprint == config_fingerprint)
    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    return count


def count_baseline_plot_results(db: Session, baseline_id: UUID) -> int:
    return (
        db.query(BaselinePlotResult)
        .filter(BaselinePlotResult.baseline_id == baseline_id, BaselinePlotResult.status == "ready")
        .count()
    )


def get_baseline_plot_results(
    db: Session,
    baseline_id: UUID,
    config_fingerprint: str,
    channel: int | None = None,
) -> List[BaselinePlotResult]:
    query = db.query(BaselinePlotResult).filter(
        BaselinePlotResult.baseline_id == baseline_id,
        BaselinePlotResult.config_fingerprint == config_fingerprint,
        BaselinePlotResult.status == "ready",
    )
    if channel is not None:
        query = query.filter(BaselinePlotResult.channel == channel)
    return query.order_by(BaselinePlotResult.channel, BaselinePlotResult.plot_type).all()
