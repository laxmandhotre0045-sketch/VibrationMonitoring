from datetime import date, datetime, time
from typing import List, Optional, Set, Tuple
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.measurement import MeasurementUploadData, PlotConfiguration, PlotResult, SensorDataUpload
from app.schemas.measurement import PlotConfigCreate, PlotConfigUpdate, PLOT_TYPES


def get_plot_config_by_sensor(db: Session, sensor_id: UUID) -> Optional[PlotConfiguration]:
    return db.query(PlotConfiguration).filter(PlotConfiguration.sensor_id == sensor_id).first()


def create_plot_config(db: Session, data: PlotConfigCreate) -> PlotConfiguration:
    existing = get_plot_config_by_sensor(db, data.sensor_id)
    if existing:
        raise ValueError("Plot configuration already exists for this sensor. Use PUT to update.")
    payload = data.model_dump()
    if not payload.get("enabled_plots"):
        payload["enabled_plots"] = list(PLOT_TYPES)
    db_config = PlotConfiguration(**payload)
    db.add(db_config)
    db.commit()
    db.refresh(db_config)
    return db_config


def update_plot_config(
    db: Session, sensor_id: UUID, data: PlotConfigUpdate
) -> Optional[PlotConfiguration]:
    db_config = get_plot_config_by_sensor(db, sensor_id)
    if not db_config:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_config, field, value)
    db_config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_config)
    return db_config


def upsert_plot_config(db: Session, data: PlotConfigCreate) -> PlotConfiguration:
    existing = get_plot_config_by_sensor(db, data.sensor_id)
    if existing:
        update = PlotConfigUpdate(**data.model_dump(exclude={"sensor_id"}))
        return update_plot_config(db, data.sensor_id, update)  # type: ignore
    return create_plot_config(db, data)


def create_upload_record(
    db: Session,
    sensor_id: UUID,
    channel_count: int,
    pdf_path: str,
    upload_id: UUID | None = None,
    original_filename: str | None = None,
    source: str = "manual",
    measured_at: datetime | None = None,
    rotation_speed_rpm: float | None = None,
    api_key_id: UUID | None = None,
) -> SensorDataUpload:
    kwargs: dict = {
        "sensor_id": sensor_id,
        "channel_count": channel_count,
        "pdf_path": pdf_path,
        "parse_status": "pending",
        "source": source,
    }
    if original_filename is not None:
        kwargs["original_filename"] = original_filename
    if upload_id is not None:
        kwargs["id"] = upload_id
    # A manual upload has no capture clock of its own, so it keeps the receipt
    # time that created_at already records rather than claiming a measured_at.
    if measured_at is not None:
        kwargs["measured_at"] = measured_at
    if rotation_speed_rpm is not None:
        kwargs["rotation_speed_rpm"] = rotation_speed_rpm
    if api_key_id is not None:
        kwargs["api_key_id"] = api_key_id
    upload = SensorDataUpload(**kwargs)
    db.add(upload)
    db.commit()
    db.refresh(upload)
    return upload


def mark_upload_parsed(
    db: Session,
    upload_id: UUID,
    parsed_data_path: str,
    sample_count: int,
) -> Optional[SensorDataUpload]:
    upload = get_upload_by_id(db, upload_id)
    if not upload:
        return None
    upload.parsed_data_path = parsed_data_path
    upload.sample_count = sample_count
    upload.parse_status = "parsed"
    upload.parse_error = None
    upload.parsed_at = datetime.utcnow()
    db.commit()
    db.refresh(upload)
    return upload


def mark_upload_failed(db: Session, upload_id: UUID, error: str) -> Optional[SensorDataUpload]:
    upload = get_upload_by_id(db, upload_id)
    if not upload:
        return None
    upload.parse_status = "failed"
    upload.parse_error = error
    db.commit()
    db.refresh(upload)
    return upload


def get_upload_by_id(db: Session, upload_id: UUID) -> Optional[SensorDataUpload]:
    return db.query(SensorDataUpload).filter(SensorDataUpload.id == upload_id).first()


def _date_start(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _date_end(d: date) -> datetime:
    return datetime.combine(d, time.max)


def get_stored_upload_ids(db: Session, upload_ids: List[UUID]) -> Set[UUID]:
    if not upload_ids:
        return set()
    rows = (
        db.query(MeasurementUploadData.upload_id)
        .filter(MeasurementUploadData.upload_id.in_(upload_ids))
        .all()
    )
    return {row[0] for row in rows}


def list_uploads_by_sensor(
    db: Session,
    sensor_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    parse_status: str | None = None,
    plots_status: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[SensorDataUpload], int]:
    query = db.query(SensorDataUpload).filter(SensorDataUpload.sensor_id == sensor_id)

    if from_date is not None:
        query = query.filter(SensorDataUpload.created_at >= _date_start(from_date))
    if to_date is not None:
        query = query.filter(SensorDataUpload.created_at <= _date_end(to_date))
    if parse_status is not None:
        query = query.filter(SensorDataUpload.parse_status == parse_status)
    if plots_status is not None:
        query = query.filter(SensorDataUpload.plots_status == plots_status)

    total = query.count()
    items = (
        query.order_by(SensorDataUpload.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def config_to_dict(config: PlotConfiguration) -> dict:
    return {
        "channel_count": config.channel_count,
        "active_channel": config.active_channel,
        "sampling_rate_hz": float(config.sampling_rate_hz),
        "fft_lines": config.fft_lines,
        "frequency_max_hz": float(config.frequency_max_hz) if config.frequency_max_hz else None,
        "data_type": config.data_type,
        "enabled_plots": config.enabled_plots or list(PLOT_TYPES),
        "window_type": getattr(config, "window_type", None) or "HANNING",
        "averaging": getattr(config, "averaging", None) or 1,
        "overlap_percent": getattr(config, "overlap_percent", None) or 0,
        "collection_interval_minutes": getattr(config, "collection_interval_minutes", None) or 2,
        "channel_map": getattr(config, "channel_map", None) or [],
        "mqtt_broker": getattr(config, "mqtt_broker", None),
        "mqtt_port": getattr(config, "mqtt_port", None) or 1883,
        "mqtt_topic": getattr(config, "mqtt_topic", None) or "Vibration_Data",
    }


def default_config_dict(channel_count: int = 1) -> dict:
    return {
        "channel_count": channel_count,
        "active_channel": 0,
        "sampling_rate_hz": 25600.0,
        "fft_lines": 1600,
        "frequency_max_hz": None,
        "data_type": "acceleration",
        "enabled_plots": list(PLOT_TYPES),
        "window_type": "HANNING",
        "averaging": 1,
        "overlap_percent": 0,
        "collection_interval_minutes": 2,
        "channel_map": [],
        "mqtt_broker": None,
        "mqtt_port": 1883,
        "mqtt_topic": "Vibration_Data",
    }


def delete_plot_results(
    db: Session,
    upload_id: UUID,
    config_fingerprint: str | None = None,
) -> int:
    query = db.query(PlotResult).filter(PlotResult.upload_id == upload_id)
    if config_fingerprint is not None:
        query = query.filter(PlotResult.config_fingerprint == config_fingerprint)
    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    return count


def get_plot_results(
    db: Session,
    upload_id: UUID,
    config_fingerprint: str,
    channel: int | None = None,
    plot_type: str | None = None,
) -> List[PlotResult]:
    query = db.query(PlotResult).filter(
        PlotResult.upload_id == upload_id,
        PlotResult.config_fingerprint == config_fingerprint,
        PlotResult.status == "ready",
    )
    if channel is not None:
        query = query.filter(PlotResult.channel == channel)
    if plot_type is not None:
        query = query.filter(PlotResult.plot_type == plot_type)
    return query.order_by(PlotResult.channel, PlotResult.plot_type).all()


def mark_upload_plots_ready(db: Session, upload_id: UUID) -> Optional[SensorDataUpload]:
    upload = get_upload_by_id(db, upload_id)
    if not upload:
        return None
    upload.plots_status = "ready"
    upload.plots_error = None
    upload.plots_computed_at = datetime.utcnow()
    db.commit()
    db.refresh(upload)
    return upload


def mark_upload_plots_failed(
    db: Session, upload_id: UUID, error: str
) -> Optional[SensorDataUpload]:
    upload = get_upload_by_id(db, upload_id)
    if not upload:
        return None
    upload.plots_status = "failed"
    upload.plots_error = error
    db.commit()
    db.refresh(upload)
    return upload


def get_latest_plot_config(db: Session) -> Optional[PlotConfiguration]:
    """Most recently saved acquisition configuration.

    Fallback for callers that pass neither device_id nor sensor_id — a
    single-machine edge deployment can then poll the config endpoint with no
    parameters at all.
    """
    return (
        db.query(PlotConfiguration)
        .order_by(PlotConfiguration.updated_at.desc().nullslast())
        .first()
    )


def latest_upload_timestamps(
    db: Session, sensor_id: UUID
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """(newest raw/device message time, newest acquisition time) for a sensor.

    The first is restricted to device-pushed raw snapshots, so the settings page
    can distinguish "MQTT is delivering" from "somebody uploaded a file".
    """
    raw_row = (
        db.query(SensorDataUpload.created_at)
        .filter(
            SensorDataUpload.sensor_id == sensor_id,
            SensorDataUpload.source == "device_raw",
        )
        .order_by(SensorDataUpload.created_at.desc())
        .first()
    )
    any_row = (
        db.query(SensorDataUpload.measured_at, SensorDataUpload.created_at)
        .filter(SensorDataUpload.sensor_id == sensor_id)
        .order_by(SensorDataUpload.created_at.desc())
        .first()
    )
    last_message = raw_row[0] if raw_row else None
    last_acquisition = (any_row[0] or any_row[1]) if any_row else None
    return last_message, last_acquisition
