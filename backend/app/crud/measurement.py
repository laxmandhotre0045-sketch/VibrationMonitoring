from datetime import datetime
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.measurement import PlotConfiguration, SensorDataUpload
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
) -> SensorDataUpload:
    kwargs: dict = {
        "sensor_id": sensor_id,
        "channel_count": channel_count,
        "pdf_path": pdf_path,
        "parse_status": "pending",
    }
    if upload_id is not None:
        kwargs["id"] = upload_id
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


def list_uploads_by_sensor(db: Session, sensor_id: UUID) -> List[SensorDataUpload]:
    return (
        db.query(SensorDataUpload)
        .filter(SensorDataUpload.sensor_id == sensor_id)
        .order_by(SensorDataUpload.created_at.desc())
        .all()
    )


def config_to_dict(config: PlotConfiguration) -> dict:
    return {
        "channel_count": config.channel_count,
        "active_channel": config.active_channel,
        "sampling_rate_hz": float(config.sampling_rate_hz),
        "fft_lines": config.fft_lines,
        "frequency_max_hz": float(config.frequency_max_hz) if config.frequency_max_hz else None,
        "data_type": config.data_type,
        "enabled_plots": config.enabled_plots or list(PLOT_TYPES),
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
    }
