import os
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import crud
from app.crud import measurement as measurement_crud
from app.schemas.measurement import (
    PLOT_TYPES,
    AllPlotsOut,
    PlotConfigCreate,
    PlotConfigOut,
    PlotConfigUpdate,
    PlotSeriesOut,
    SensorDataUploadOut,
)
from app.schemas.acquisition import EdgeAcquisitionConfigOut
from app.services.acquisition_config import build_edge_acquisition_config
from app.services.pdf_parser import parse_sensor_file
from app.services.plot_generator import generate_all_plots, generate_plot, save_parsed_data

router = APIRouter(prefix="/api/v1/measurements", tags=["Measurements"])

ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "text/csv",
    "application/csv",
    "text/plain",
}


# ── Plot configuration (configure API) ───────────────────────────────────────

@router.post("/configure", response_model=PlotConfigOut)
def configure_plots(data: PlotConfigCreate, db: Session = Depends(get_db)):
    """Create or update plot configuration (upsert) for a sensor."""
    sensor = crud.get_sensor_by_id(db, data.sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return measurement_crud.upsert_plot_config(db, data)


@router.get("/configure/{sensor_id}", response_model=PlotConfigOut)
def get_plot_config(sensor_id: UUID, db: Session = Depends(get_db)):
    config = measurement_crud.get_plot_config_by_sensor(db, sensor_id)
    if not config:
        raise HTTPException(status_code=404, detail="Plot configuration not found for this sensor")
    return config


@router.put("/configure/{sensor_id}", response_model=PlotConfigOut)
def update_plot_config(sensor_id: UUID, data: PlotConfigUpdate, db: Session = Depends(get_db)):
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    config = measurement_crud.update_plot_config(db, sensor_id, data)
    if not config:
        raise HTTPException(status_code=404, detail="Plot configuration not found for this sensor")
    return config


# ── Edge acquisition config (for UDP / acquisition scripts) ─────────────────

def _edge_acquisition_response(db: Session, device_id: str) -> EdgeAcquisitionConfigOut:
    sensor = crud.get_sensor_by_device_id(db, device_id)
    if not sensor:
        raise HTTPException(
            status_code=404,
            detail=f"No sensor found with device_id '{device_id}'. "
            "Set device_id on the sensor via equipment API, then save plot config.",
        )
    plot_config = measurement_crud.get_plot_config_by_sensor(db, sensor.id)
    payload = build_edge_acquisition_config(sensor, plot_config)
    return EdgeAcquisitionConfigOut(**payload)


@router.get(
    "/acquisition",
    response_model=EdgeAcquisitionConfigOut,
    summary="Edge config by device_id query (recommended for MAC addresses)",
)
def get_edge_acquisition_query(
    device_id: str = Query(..., description="Edge device ID / MAC, e.g. 11:AA:BB:CC:DD:EE"),
    db: Session = Depends(get_db),
):
    """
    **Edge script URL (recommended):**
    `GET /api/v1/measurements/acquisition?device_id=11:AA:BB:CC:DD:EE`

    Returns Sensovibe-compatible acquisition JSON for UDP acquisition scripts.
    """
    return _edge_acquisition_response(db, device_id)


@router.get(
    "/acquisition/by-sensor/{sensor_id}",
    response_model=EdgeAcquisitionConfigOut,
    summary="Edge config by platform sensor UUID (testing)",
)
def get_edge_acquisition_by_sensor(sensor_id: UUID, db: Session = Depends(get_db)):
    """Build edge JSON from sensor UUID — useful before device_id is assigned."""
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    plot_config = measurement_crud.get_plot_config_by_sensor(db, sensor.id)
    payload = build_edge_acquisition_config(sensor, plot_config)
    return EdgeAcquisitionConfigOut(**payload)


@router.get(
    "/acquisition/{device_id}",
    response_model=EdgeAcquisitionConfigOut,
    summary="Edge config by device_id path",
)
def get_edge_acquisition_path(device_id: str, db: Session = Depends(get_db)):
    """
    **Edge script URL:**
    `GET /api/v1/measurements/acquisition/{device_id}`

    Note: if device_id contains `:`, prefer the query version above.
    """
    return _edge_acquisition_response(db, device_id)


# ── Sensor data upload (CSV or PDF) ───────────────────────────────────────────

def _allowed_upload(filename: str, content_type: str) -> bool:
    lower = (filename or "").lower()
    if lower.endswith(".pdf") or lower.endswith(".csv"):
        return True
    return content_type in ALLOWED_UPLOAD_TYPES


@router.post("/upload", response_model=SensorDataUploadOut, status_code=201)
async def upload_sensor_data(
    sensor_id: UUID = Form(...),
    channel_count: int = Form(..., ge=1, le=32),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(
            status_code=404,
            detail="Sensor not found. Use a real sensor_id from GET /api/v1/equipment/{equipment_id} → sensors[].id",
        )

    filename = file.filename or "upload.csv"
    content_type = file.content_type or ""
    if not _allowed_upload(filename, content_type):
        raise HTTPException(status_code=400, detail="File must be a CSV or PDF")

    content = await file.read()
    max_bytes = settings.max_pdf_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_pdf_size_mb}MB limit")

    os.makedirs(settings.measurement_upload_dir, exist_ok=True)
    upload_id = uuid.uuid4()
    ext = ".csv" if filename.lower().endswith(".csv") else ".pdf"
    file_path = os.path.join(settings.measurement_upload_dir, f"{upload_id}{ext}")

    with open(file_path, "wb") as f:
        f.write(content)

    upload = measurement_crud.create_upload_record(
        db, sensor_id, channel_count, file_path, upload_id=upload_id
    )

    parsed_json_path = os.path.join(settings.measurement_upload_dir, f"{upload.id}.json")
    try:
        parsed = parse_sensor_file(file_path, channel_count)
        save_parsed_data(parsed_json_path, parsed)
        upload = measurement_crud.mark_upload_parsed(
            db, upload.id, parsed_json_path, parsed["sample_count"]
        )
    except Exception as e:
        measurement_crud.mark_upload_failed(db, upload.id, str(e))
        raise HTTPException(status_code=422, detail=f"PDF parsing failed: {e}")

    return upload


@router.get("/uploads", response_model=list[SensorDataUploadOut])
def list_uploads(sensor_id: UUID = Query(...), db: Session = Depends(get_db)):
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    return measurement_crud.list_uploads_by_sensor(db, sensor_id)


@router.get("/uploads/{upload_id}", response_model=SensorDataUploadOut)
def get_upload(upload_id: UUID, db: Session = Depends(get_db)):
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


# ── Plot generation ───────────────────────────────────────────────────────────

def _resolve_config(db: Session, upload, channel_count: int) -> dict:
    config = measurement_crud.get_plot_config_by_sensor(db, upload.sensor_id)
    if config:
        return measurement_crud.config_to_dict(config)
    return measurement_crud.default_config_dict(channel_count)


@router.get("/uploads/{upload_id}/plots", response_model=AllPlotsOut)
def get_all_plots(
    upload_id: UUID,
    channel: int | None = Query(None, ge=0, le=31, description="Channel to plot (ch0, ch1, ...). Overrides saved active_channel."),
    db: Session = Depends(get_db),
):
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.parse_status != "parsed" or not upload.parsed_data_path:
        raise HTTPException(status_code=422, detail=f"Upload not parsed: {upload.parse_error or upload.parse_status}")

    cfg = _resolve_config(db, upload, upload.channel_count)
    if channel is not None:
        cfg = {**cfg, "active_channel": channel}
    plots = generate_all_plots(upload_id, upload.sensor_id, upload.parsed_data_path, cfg)
    from app.services.plot_generator import resolve_active_channel, load_parsed_data
    parsed = load_parsed_data(upload.parsed_data_path)
    resolved = resolve_active_channel(parsed, int(cfg["active_channel"]))
    return AllPlotsOut(
        upload_id=upload_id,
        sensor_id=upload.sensor_id,
        channel=resolved,
        plots=plots,
    )


@router.get("/uploads/{upload_id}/plots/{plot_type}", response_model=PlotSeriesOut)
def get_single_plot(
    upload_id: UUID,
    plot_type: str,
    channel: int | None = Query(None, ge=0, le=31),
    db: Session = Depends(get_db),
):
    if plot_type not in PLOT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid plot type. Allowed: {PLOT_TYPES}")

    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.parse_status != "parsed" or not upload.parsed_data_path:
        raise HTTPException(status_code=422, detail=f"Upload not parsed: {upload.parse_error or upload.parse_status}")

    cfg = _resolve_config(db, upload, upload.channel_count)
    if channel is not None:
        cfg = {**cfg, "active_channel": channel}
    from app.services.plot_generator import load_parsed_data

    parsed = load_parsed_data(upload.parsed_data_path)
    try:
        return generate_plot(parsed, plot_type, int(cfg["active_channel"]), cfg)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/plot-types")
def list_plot_types():
    return {"plot_types": PLOT_TYPES}
