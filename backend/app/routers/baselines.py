import os
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.crud import baseline as baseline_crud
from app.crud import measurement as measurement_crud
from app.database import get_db
from app.schemas.baseline import (
    BaselineCreateFromUpload,
    BaselineListOut,
    BaselineOut,
    BaselineSetPrimary,
)
from app.schemas.measurement import AllPlotsOut, PLOT_TYPES, PlotSeriesOut
from app.services.baseline_storage import baseline_plot_to_series, persist_baseline_plot_results
from app.services.pdf_parser import parse_sensor_file
from app.services.plot_generator import save_parsed_data
from app.services.plot_storage import compute_config_fingerprint

router = APIRouter(prefix="/api/v1/baselines", tags=["Baselines"])


def _baseline_out(baseline, plots_status: str = "ready") -> BaselineOut:
    return BaselineOut(
        id=baseline.id,
        sensor_id=baseline.sensor_id,
        source_upload_id=baseline.source_upload_id,
        name=baseline.name,
        description=baseline.description,
        labels=baseline.labels or [],
        original_filename=baseline.original_filename,
        file_format=baseline.file_format,
        channel_count=baseline.channel_count,
        sample_count=baseline.sample_count,
        sampling_rate_hz=float(baseline.sampling_rate_hz),
        is_primary=baseline.is_primary,
        captured_at=baseline.captured_at,
        created_at=baseline.created_at,
        plots_status=plots_status,
    )


def _resolve_config(db: Session, sensor_id: UUID, channel_count: int) -> dict:
    config = measurement_crud.get_plot_config_by_sensor(db, sensor_id)
    if config:
        return measurement_crud.config_to_dict(config)
    return measurement_crud.default_config_dict(channel_count)


@router.get("", response_model=BaselineListOut)
def list_baselines(sensor_id: UUID = Query(...), db: Session = Depends(get_db)):
    """List all baselines for a sensor (full history — nothing is deleted)."""
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")
    items = baseline_crud.list_baselines_by_sensor(db, sensor_id)
    primary = baseline_crud.get_primary_baseline(db, sensor_id)
    return BaselineListOut(
        sensor_id=sensor_id,
        total=len(items),
        primary_baseline_id=primary.id if primary else None,
        items=[_baseline_out(b) for b in items],
    )


@router.get("/primary", response_model=BaselineOut)
def get_primary_baseline(sensor_id: UUID = Query(...), db: Session = Depends(get_db)):
    """Return the baseline marked is_primary for UI display (optional flag — all baselines remain stored)."""
    baseline = baseline_crud.get_primary_baseline(db, sensor_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="No primary baseline set for this sensor")
    return _baseline_out(baseline)


@router.get("/{baseline_id}", response_model=BaselineOut)
def get_baseline(baseline_id: UUID, db: Session = Depends(get_db)):
    baseline = baseline_crud.get_baseline_by_id(db, baseline_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return _baseline_out(baseline)


@router.patch("/{baseline_id}/primary", response_model=BaselineOut)
def set_primary_baseline(
    baseline_id: UUID,
    data: BaselineSetPrimary,
    db: Session = Depends(get_db),
):
    """Mark one baseline as primary for UI. Does not delete other baselines."""
    baseline = baseline_crud.set_baseline_primary(db, baseline_id, data.is_primary)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return _baseline_out(baseline)


@router.post("/upload", response_model=BaselineOut, status_code=201)
async def upload_baseline(
    sensor_id: UUID = Form(...),
    channel_count: int = Form(..., ge=1, le=32),
    name: str = Form(...),
    description: str | None = Form(None),
    set_as_primary: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload CSV/PDF directly as a new baseline record (append-only — never replaces old baselines)."""
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    filename = file.filename or "baseline.csv"
    content = await file.read()
    file_format = "csv" if filename.lower().endswith(".csv") else "pdf"

    os.makedirs(settings.measurement_upload_dir, exist_ok=True)
    temp_path = os.path.join(settings.measurement_upload_dir, f"baseline_{uuid.uuid4()}.{file_format}")
    with open(temp_path, "wb") as f:
        f.write(content)

    try:
        parsed = parse_sensor_file(temp_path, channel_count)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Parse failed: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    cfg = _resolve_config(db, sensor_id, channel_count)
    baseline = baseline_crud.create_baseline(
        db,
        sensor_id=sensor_id,
        source_upload_id=None,
        name=name,
        description=description,
        labels=[],
        original_filename=filename,
        file_format=file_format,
        file_content=content,
        parsed_data=parsed,
        channel_count=channel_count,
        sample_count=parsed["sample_count"],
        sampling_rate_hz=float(cfg["sampling_rate_hz"]),
        set_as_primary=set_as_primary,
    )
    try:
        persist_baseline_plot_results(db, baseline, parsed, cfg)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Baseline plot compute failed: {e}")
    return _baseline_out(baseline)


@router.post("/from-upload/{upload_id}", response_model=BaselineOut, status_code=201)
def create_baseline_from_upload(
    upload_id: UUID,
    data: BaselineCreateFromUpload,
    db: Session = Depends(get_db),
):
    """Copy an existing upload into sensor_baselines (keeps upload + adds new baseline row)."""
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload or upload.parse_status != "parsed":
        raise HTTPException(status_code=404, detail="Parsed upload not found")

    upload_data = baseline_crud.get_upload_data_by_upload_id(db, upload_id)
    if not upload_data:
        raise HTTPException(
            status_code=422,
            detail="Upload file data not in DB. Re-upload the file after migration 007.",
        )

    cfg = _resolve_config(db, upload.sensor_id, upload.channel_count)
    baseline = baseline_crud.create_baseline(
        db,
        sensor_id=upload.sensor_id,
        source_upload_id=upload_id,
        name=data.name,
        description=data.description,
        labels=data.labels,
        original_filename=upload_data.original_filename,
        file_format=upload_data.file_format,
        file_content=upload_data.file_content,
        parsed_data=upload_data.parsed_data,
        channel_count=upload_data.channel_count,
        sample_count=upload_data.sample_count,
        sampling_rate_hz=float(cfg["sampling_rate_hz"]),
        set_as_primary=data.set_as_primary,
        captured_at=data.captured_at,
    )
    try:
        persist_baseline_plot_results(db, baseline, upload_data.parsed_data, cfg)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Baseline plot compute failed: {e}")
    return _baseline_out(baseline)


@router.get("/{baseline_id}/plots", response_model=AllPlotsOut)
def get_baseline_plots(
    baseline_id: UUID,
    channel: int | None = Query(None, ge=0, le=31),
    db: Session = Depends(get_db),
):
    baseline = baseline_crud.get_baseline_by_id(db, baseline_id)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")

    cfg = _resolve_config(db, baseline.sensor_id, baseline.channel_count)
    if channel is not None:
        cfg = {**cfg, "active_channel": channel}
    fingerprint = compute_config_fingerprint(cfg)
    resolved_channel = channel if channel is not None else int(cfg.get("active_channel", 0))

    stored = baseline_crud.get_baseline_plot_results(db, baseline_id, fingerprint, resolved_channel)
    if not stored:
        try:
            persist_baseline_plot_results(db, baseline, baseline.parsed_data, cfg)
            stored = baseline_crud.get_baseline_plot_results(db, baseline_id, fingerprint, resolved_channel)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))

    plots = [baseline_plot_to_series(r) for r in stored]
    return AllPlotsOut(
        upload_id=baseline_id,
        sensor_id=baseline.sensor_id,
        channel=resolved_channel,
        plots=plots,
    )


@router.get("/{baseline_id}/plots/{plot_type}", response_model=PlotSeriesOut)
def get_baseline_single_plot(
    baseline_id: UUID,
    plot_type: str,
    channel: int | None = Query(None, ge=0, le=31),
    db: Session = Depends(get_db),
):
    if plot_type not in PLOT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid plot type. Allowed: {PLOT_TYPES}")
    all_plots = get_baseline_plots(baseline_id, channel, db)
    for plot in all_plots.plots:
        if plot.plot_type == plot_type:
            return plot
    raise HTTPException(status_code=404, detail=f"Plot {plot_type} not found")
