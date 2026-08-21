import os
import uuid
from datetime import date
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import crud
from app.dependencies.auth import get_current_user, require_write_access
from app.crud import baseline as baseline_crud
from app.crud import measurement as measurement_crud
from app.schemas.measurement import (
    PLOT_TYPES,
    AllPlotsOut,
    PaginatedUploadListOut,
    PlotConfigCreate,
    PlotConfigOut,
    PlotConfigUpdate,
    PlotSeriesOut,
    SensorDataUploadOut,
)
from app.schemas.acquisition import EdgeAcquisitionConfigOut
from app.schemas.waterfall import SELECTION_MODES, WaterfallOut
from app.schemas.vector import VibrationVectorOut
from app.schemas.orbit import CasingOrbitOut
from app.services.casing_orbit import build_casing_orbit
from app.services.acquisition_config import build_edge_acquisition_config
from app.services.waterfall import (
    DEFAULT_MAX_PEAKS,
    DEFAULT_MAX_POINTS,
    WATERFALL_POOL_LIMIT,
    amplitude_axis_label,
    build_waterfall,
    detect_spectrum_peaks,
)
from app.services.vibration_vector import (
    DEFAULT_OVERLAP,
    compute_vector_blocks,
    resolve_block_size,
)
from app.services.pdf_parser import parse_sensor_file
from app.services.plot_generator import save_parsed_data
from app.crud import feature as feature_crud
from app.schemas.feature import (
    ChannelFeatureOut,
    ChannelHealthOverviewOut,
    FactorTrendSeriesOut,
    FeatureCompareItemOut,
    FeatureCompareOut,
    FeaturesSummaryOut,
    UploadFactorTrendsOut,
    UploadFeaturesOut,
)
from app.services.feature_storage import (
    # Single source of truth for "parsed samples from DB, else from disk".
    _load_parsed_for_upload,
    ensure_upload_features_ready,
    features_summary_from_rows,
    persist_upload_features_and_trends,
)
from app.services.plot_storage import (
    compute_config_fingerprint,
    get_or_load_all_plots,
    get_or_load_single_plot,
    persist_all_plot_results,
    plot_result_to_series,
)
from app.services.threshold_evaluator import status_to_health_level

router = APIRouter(
    prefix="/api/v1/measurements",
    tags=["Measurements"],
    dependencies=[Depends(get_current_user)],
)

ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "text/csv",
    "application/csv",
    "text/plain",
}


def _to_upload_out(upload, *, has_stored_data: bool = False) -> SensorDataUploadOut:
    return SensorDataUploadOut.model_validate(upload).model_copy(
        update={"has_stored_data": has_stored_data}
    )


# ── Plot configuration (configure API) ───────────────────────────────────────

@router.post(
    "/configure",
    response_model=PlotConfigOut,
    dependencies=[Depends(require_write_access)],
)
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


@router.put(
    "/configure/{sensor_id}",
    response_model=PlotConfigOut,
    dependencies=[Depends(require_write_access)],
)
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


@router.post(
    "/upload",
    response_model=SensorDataUploadOut,
    status_code=201,
    dependencies=[Depends(require_write_access)],
)
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
        db,
        sensor_id,
        channel_count,
        file_path,
        upload_id=upload_id,
        original_filename=filename,
        source="manual",
    )

    parsed_json_path = os.path.join(settings.measurement_upload_dir, f"{upload.id}.json")
    try:
        parsed = parse_sensor_file(file_path, channel_count)
        save_parsed_data(parsed_json_path, parsed)
        upload = measurement_crud.mark_upload_parsed(
            db, upload.id, parsed_json_path, parsed["sample_count"]
        )
        file_format = "csv" if filename.lower().endswith(".csv") else "pdf"
        baseline_crud.save_upload_data(
            db,
            upload_id=upload.id,
            sensor_id=sensor_id,
            original_filename=filename,
            file_format=file_format,
            file_content=content,
            parsed_data=parsed,
            channel_count=channel_count,
            sample_count=parsed["sample_count"],
        )
        cfg = _resolve_config(db, upload, upload.channel_count)
        try:
            persist_all_plot_results(db, upload, parsed_json_path, cfg)
            upload = measurement_crud.mark_upload_plots_ready(db, upload.id)
        except Exception as plot_err:
            upload = measurement_crud.mark_upload_plots_failed(db, upload.id, str(plot_err))
        try:
            persist_upload_features_and_trends(db, upload, parsed, float(cfg["sampling_rate_hz"]))
            upload = feature_crud.mark_upload_features_ready(db, upload.id)
        except Exception as feat_err:
            upload = feature_crud.mark_upload_features_failed(db, upload.id, str(feat_err))
    except Exception as e:
        measurement_crud.mark_upload_failed(db, upload.id, str(e))
        raise HTTPException(status_code=422, detail=f"PDF parsing failed: {e}")

    db.refresh(upload)
    return _to_upload_out(upload, has_stored_data=True)


@router.get("/uploads", response_model=PaginatedUploadListOut)
def list_uploads(
    sensor_id: UUID = Query(..., description="Sensor UUID"),
    from_date: date | None = Query(None, description="Include uploads on or after this date (UTC)"),
    to_date: date | None = Query(None, description="Include uploads on or before this date (UTC)"),
    parse_status: str | None = Query(None, description="Filter by parse_status, e.g. parsed"),
    plots_status: str | None = Query(None, description="Filter by plots_status, e.g. ready"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List uploads for a sensor, optionally filtered by date range and status."""
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be on or before to_date")

    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    items, total = measurement_crud.list_uploads_by_sensor(
        db,
        sensor_id,
        from_date=from_date,
        to_date=to_date,
        parse_status=parse_status,
        plots_status=plots_status,
        page=page,
        page_size=page_size,
    )
    stored_ids = measurement_crud.get_stored_upload_ids(db, [u.id for u in items])
    return PaginatedUploadListOut(
        items=[_to_upload_out(u, has_stored_data=u.id in stored_ids) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/uploads/{upload_id}", response_model=SensorDataUploadOut)
def get_upload(upload_id: UUID, db: Session = Depends(get_db)):
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    stored_ids = measurement_crud.get_stored_upload_ids(db, [upload.id])
    return _to_upload_out(upload, has_stored_data=upload.id in stored_ids)


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
    try:
        return get_or_load_all_plots(db, upload, cfg, channel=channel)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


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
    try:
        return get_or_load_single_plot(db, upload, cfg, plot_type, channel=channel)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/plot-types")
def list_plot_types():
    return {"plot_types": PLOT_TYPES}


# ── 3D FFT waterfall (many captures, one channel) ────────────────────────────

@router.get(
    "/waterfall",
    response_model=WaterfallOut,
    summary="Stacked FFT spectra across captures for the 3D waterfall",
)
def get_waterfall(
    sensor_id: UUID = Query(..., description="Sensor UUID"),
    channel: int = Query(0, ge=0, le=31, description="Channel to stack (ch0, ch1, ...)"),
    count: int = Query(40, ge=1, le=200, description="How many captures to stack"),
    mode: str = Query("last", description="last | oldest | random"),
    plot_type: str = Query("fft_spectrum", description="fft_spectrum or envelope_spectrum"),
    max_points: int = Query(
        DEFAULT_MAX_POINTS, ge=32, le=4096, description="Bins per spectrum after peak-preserving decimation"
    ),
    max_peaks: int = Query(DEFAULT_MAX_PEAKS, ge=0, le=64, description="Peak markers per spectrum"),
    seed: int | None = Query(None, description="Fixes the random selection so it stays stable across refetches"),
    from_date: date | None = Query(None, description="Include captures on or after this date (UTC)"),
    to_date: date | None = Query(None, description="Include captures on or before this date (UTC)"),
    db: Session = Depends(get_db),
):
    """
    Read-only. Returns the already-computed spectra stored for each capture, stacked
    oldest to newest, plus detected peaks and the real frequency/amplitude ranges.
    """
    if mode not in SELECTION_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {SELECTION_MODES}")
    if plot_type not in ("fft_spectrum", "envelope_spectrum"):
        raise HTTPException(
            status_code=400, detail="plot_type must be fft_spectrum or envelope_spectrum"
        )
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be on or before to_date")

    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    config = measurement_crud.get_plot_config_by_sensor(db, sensor_id)
    cfg = (
        measurement_crud.config_to_dict(config)
        if config
        else measurement_crud.default_config_dict(channel + 1)
    )

    # Whole parsed pool, not one page: "oldest N" and "random" both need it.
    uploads, total_parsed = measurement_crud.list_uploads_by_sensor(
        db,
        sensor_id,
        from_date=from_date,
        to_date=to_date,
        parse_status="parsed",
        page=1,
        page_size=WATERFALL_POOL_LIMIT,
    )

    try:
        payload = build_waterfall(
            db,
            sensor=sensor,
            uploads_newest_first=uploads,
            config=cfg,
            channel=channel,
            mode=mode,
            count=count,
            plot_type=plot_type,
            max_points=max_points,
            max_peaks=max_peaks,
            seed=seed,
            total_available=total_parsed,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return WaterfallOut(**payload)


# ── Polar / vibration vector (one capture, blocks within it) ─────────────────

def _stored_estimated_shaft_hz(db: Session, upload_id: UUID, channel: int) -> float | None:
    """
    Read-only lookup of the FFT-derived shaft estimate.

    Deliberately does not trigger feature computation — returns None when features were
    never computed for this capture.
    """
    try:
        rows = feature_crud.get_measurement_features(db, upload_id, channel=channel)
    except Exception:
        return None
    for row in rows:
        meta = row.metadata_ or {}
        value = meta.get("estimated_shaft_hz")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def _frequency_candidates(
    db: Session,
    upload,
    cfg: dict,
    channel: int,
    shaft_hz: float | None,
) -> list[dict]:
    """Orders of interest the user can choose from: shaft harmonics, then stored peaks."""
    candidates: list[dict] = []

    if shaft_hz:
        for order in (1, 2, 3):
            candidates.append(
                {
                    "label": f"{order}x estimated shaft ({shaft_hz * order:.1f} Hz)",
                    "frequency_hz": shaft_hz * order,
                    "source": "estimated_shaft",
                    "amplitude": None,
                }
            )

    # Reuse the waterfall's peak detector on the already-stored spectrum — no second
    # peak-detection implementation, and no recompute of the FFT.
    try:
        fingerprint = compute_config_fingerprint(cfg)
        rows = measurement_crud.get_plot_results(
            db,
            upload_id=upload.id,
            config_fingerprint=fingerprint,
            channel=channel,
            plot_type="fft_spectrum",
        )
        if rows:
            series = plot_result_to_series(rows[0])
            freqs = np.asarray(series.x, dtype=float)
            mags = np.asarray(series.y, dtype=float)
            for peak in detect_spectrum_peaks(freqs, mags, 6):
                candidates.append(
                    {
                        "label": f"Peak {peak['frequency']:.1f} Hz",
                        "frequency_hz": peak["frequency"],
                        "source": "peak",
                        "amplitude": peak["amplitude"],
                    }
                )
    except Exception:
        pass

    return candidates


@router.get(
    "/uploads/{upload_id}/vector",
    response_model=VibrationVectorOut,
    summary="Amplitude + self-referenced phase at one frequency, per FFT block",
)
def get_vibration_vector(
    upload_id: UUID,
    channel: int = Query(0, ge=0, le=31),
    target_hz: float | None = Query(
        None, gt=0, description="Order of interest. Defaults to 1x estimated shaft, else the strongest peak."
    ),
    block_size: int | None = Query(
        None, ge=8, le=65536, description="Samples per FFT block. Defaults to the sensor's configured FFT size."
    ),
    overlap: float = Query(DEFAULT_OVERLAP, ge=0.0, le=0.95),
    db: Session = Depends(get_db),
):
    """
    Read-only. Re-runs the FFT on the stored raw samples of ONE capture purely to keep the
    complex value, which `compute_fft_spectrum` discards. Same window and same magnitude
    scaling, so amplitudes match the existing spectra.

    Phase is self-referenced to block 0 — there is no keyphasor in this system, so
    absolute shaft phase is not available.
    """
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.parse_status != "parsed":
        raise HTTPException(
            status_code=422, detail=f"Upload not parsed: {upload.parse_error or upload.parse_status}"
        )

    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    cfg = _resolve_config(db, upload, upload.channel_count)

    try:
        parsed = _load_parsed_for_upload(db, upload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No raw samples available: {exc}")

    samples = (parsed.get("channels") or {}).get(f"ch{channel}")
    if not samples:
        raise HTTPException(status_code=404, detail=f"Channel ch{channel} not present in this capture")

    shaft_hz = _stored_estimated_shaft_hz(db, upload_id, channel)
    candidates = _frequency_candidates(db, upload, cfg, channel, shaft_hz)

    # Selection priority: explicit request, then 1x estimated shaft, then strongest peak.
    if target_hz is not None:
        resolved_hz, source, label = target_hz, "explicit", f"{target_hz:.1f} Hz (selected)"
    elif shaft_hz:
        resolved_hz, source = shaft_hz, "estimated_shaft"
        label = f"{shaft_hz:.1f} Hz (1x estimated shaft speed)"
    else:
        peaks = [c for c in candidates if c["source"] == "peak"]
        if not peaks:
            raise HTTPException(
                status_code=422,
                detail="No frequency of interest available. Select a frequency, or compute "
                "features for this capture so an estimated shaft speed exists.",
            )
        strongest = max(peaks, key=lambda c: c["amplitude"] or 0.0)
        resolved_hz, source = strongest["frequency_hz"], "peak"
        label = f"{resolved_hz:.1f} Hz (strongest spectral peak)"

    sampling_rate = float(cfg["sampling_rate_hz"])
    resolved_block = resolve_block_size(len(samples), block_size, cfg.get("fft_lines"))

    try:
        result = compute_vector_blocks(
            samples,
            sampling_rate,
            resolved_hz,
            block_size=resolved_block,
            overlap=overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    data_type = cfg.get("data_type", "acceleration")
    unit = amplitude_axis_label(data_type)
    unit = unit[unit.find("(") + 1 : unit.find(")")] if "(" in unit else ""

    return VibrationVectorOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        channel=channel,
        captured_at=upload.created_at,
        original_filename=upload.original_filename,
        sampling_rate_hz=sampling_rate,
        sample_count=len(samples),
        target_hz_requested=resolved_hz,
        target_source=source,
        target_label=label,
        amplitude_unit=unit,
        data_type=data_type,
        estimated_shaft_hz=shaft_hz,
        keyphasor_available=False,
        sensor_label=sensor.sensor_type if sensor else None,
        orientation=sensor.orientation if sensor else None,
        mounting_location=sensor.mounting_location if sensor else None,
        candidates=candidates,
        **result,
    )


# ── Casing orbit / Lissajous (two orthogonal channels of one capture) ────────

@router.get(
    "/uploads/{upload_id}/orbit",
    response_model=CasingOrbitOut,
    summary="Casing orbit X(t) vs Y(t) from two synchronously-sampled channels",
)
def get_casing_orbit(
    upload_id: UUID,
    x_channel: int = Query(0, ge=0, le=31),
    y_channel: int = Query(1, ge=0, le=31),
    harmonic: int = Query(1, ge=1, le=10, description="1x or 2x of estimated shaft speed"),
    bandwidth_percent: float = Query(
        20.0, gt=0, le=100, description="Half-bandwidth as a percent of the centre frequency"
    ),
    filter_revolutions: int | None = Query(
        None, ge=1, le=512, description="Revolutions used for filtering. Omit for auto."
    ),
    display_revolutions: float = Query(1.0, gt=0, le=64),
    include_unfiltered: bool = Query(False),
    shaft_hz: float | None = Query(
        None, gt=0, description="Override the FFT-estimated shaft frequency"
    ),
    db: Session = Depends(get_db),
):
    """
    Read-only. Casing motion from accelerometers — NOT a shaft-centreline orbit.

    X and Y come from the same interleaved capture, so sample i is the same instant on
    both channels; no timestamp re-alignment is required or performed.
    """
    if x_channel == y_channel:
        raise HTTPException(status_code=400, detail="X and Y must be different channels")

    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.parse_status != "parsed":
        raise HTTPException(
            status_code=422, detail=f"Upload not parsed: {upload.parse_error or upload.parse_status}"
        )

    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    cfg = _resolve_config(db, upload, upload.channel_count)

    try:
        parsed = _load_parsed_for_upload(db, upload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"No raw samples available: {exc}")

    channels = parsed.get("channels") or {}
    samples_x = channels.get(f"ch{x_channel}")
    samples_y = channels.get(f"ch{y_channel}")
    if not samples_x or not samples_y:
        missing = f"ch{x_channel}" if not samples_x else f"ch{y_channel}"
        raise HTTPException(status_code=404, detail=f"Channel {missing} not present in this capture")

    resolved_shaft = shaft_hz or _stored_estimated_shaft_hz(db, upload_id, x_channel)
    if not resolved_shaft:
        raise HTTPException(
            status_code=422,
            detail="Unable to determine shaft frequency for 1x/2x filtering. Compute features "
            "for this capture, or supply shaft_hz directly.",
        )

    try:
        result = build_casing_orbit(
            samples_x=samples_x,
            samples_y=samples_y,
            sampling_rate_hz=float(cfg["sampling_rate_hz"]),
            shaft_hz=resolved_shaft,
            harmonic=harmonic,
            bandwidth_percent=bandwidth_percent,
            filter_revolutions=filter_revolutions,
            display_revolutions=display_revolutions,
            include_unfiltered=include_unfiltered,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    warnings = list(result.pop("warnings", []))
    if cfg.get("data_type", "acceleration") != "acceleration":
        warnings.append(
            f"Plot config data_type is '{cfg.get('data_type')}'; displacement conversion assumes "
            "the stored samples are acceleration in g."
        )

    return CasingOrbitOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        captured_at=upload.created_at,
        original_filename=upload.original_filename,
        x_channel=x_channel,
        y_channel=y_channel,
        sampling_rate_hz=float(cfg["sampling_rate_hz"]),
        sample_count=len(samples_x),
        estimated_shaft_hz=resolved_shaft,
        shaft_source="override" if shaft_hz else "estimated_fft",
        sensor_label=sensor.sensor_type if sensor else None,
        sensor_orientation=sensor.orientation if sensor else None,
        mounting_location=sensor.mounting_location if sensor else None,
        warnings=warnings,
        **result,
    )


def _feature_rows_to_out(rows, definitions: dict) -> list[ChannelFeatureOut]:
    return [
        ChannelFeatureOut(
            channel=r.channel,
            feature_code=r.feature_code,
            feature_name=definitions.get(r.feature_code),
            value=float(r.value),
            unit=r.unit,
            status=r.status,
            metadata=r.metadata_ or {},
            computed_at=r.computed_at,
        )
        for r in rows
    ]


def _channel_health_overview(rows, definitions: dict) -> ChannelHealthOverviewOut:
    if not rows:
        return ChannelHealthOverviewOut(health_state="Unknown", feature_count=0)
    statuses = [r.status for r in rows]
    if "critical" in statuses:
        state = "Critical"
    elif "warning" in statuses:
        state = "Warning"
    elif all(s == "normal" for s in statuses):
        state = "Normal"
    else:
        state = status_to_health_level(statuses[0])
    return ChannelHealthOverviewOut(
        health_state=state,
        feature_count=len(rows),
        computed_at=rows[0].computed_at,
    )


def _summary_from_rows(rows) -> FeaturesSummaryOut:
    s = features_summary_from_rows(rows)
    return FeaturesSummaryOut(**s)


@router.get("/uploads/{upload_id}/features", response_model=UploadFeaturesOut)
def get_upload_features(
    upload_id: UUID,
    channel: int | None = Query(None, ge=0, le=31),
    db: Session = Depends(get_db),
):
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.parse_status != "parsed":
        raise HTTPException(status_code=422, detail=f"Upload not parsed: {upload.parse_error or upload.parse_status}")

    cfg = _resolve_config(db, upload, upload.channel_count)
    try:
        upload = ensure_upload_features_ready(db, upload, float(cfg["sampling_rate_hz"]))
    except Exception as exc:
        feature_crud.mark_upload_features_failed(db, upload.id, str(exc))
        raise HTTPException(status_code=422, detail=f"Feature compute failed: {exc}")

    definitions = {d.code: d.name for d in feature_crud.get_feature_definitions(db)}
    rows = feature_crud.get_measurement_features(db, upload_id, channel=channel)
    channel_rows = rows if channel is not None else rows
    return UploadFeaturesOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        channel=channel,
        features_status=upload.features_status,
        features_error=upload.features_error,
        features_computed_at=upload.features_computed_at,
        items=_feature_rows_to_out(channel_rows, definitions),
        summary=_summary_from_rows(channel_rows),
        channel_overview=_channel_health_overview(channel_rows, definitions),
    )


@router.get("/uploads/{upload_id}/factor-trends", response_model=UploadFactorTrendsOut)
def get_upload_factor_trends(
    upload_id: UUID,
    channel: int = Query(0, ge=0, le=31),
    db: Session = Depends(get_db),
):
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.parse_status != "parsed":
        raise HTTPException(status_code=422, detail=f"Upload not parsed: {upload.parse_error or upload.parse_status}")

    cfg = _resolve_config(db, upload, upload.channel_count)
    try:
        upload = ensure_upload_features_ready(db, upload, float(cfg["sampling_rate_hz"]))
    except Exception as exc:
        feature_crud.mark_upload_features_failed(db, upload.id, str(exc))
        raise HTTPException(status_code=422, detail=f"Feature compute failed: {exc}")

    definitions = feature_crud.get_definition_map(db)
    scalar_rows = {
        r.feature_code: r
        for r in feature_crud.get_measurement_features(db, upload_id, channel=channel)
    }
    trend_rows = feature_crud.get_measurement_feature_trends(db, upload_id, channel)

    by_code: dict[str, dict] = {}
    for row in trend_rows:
        bucket = by_code.setdefault(row.feature_code, {"trend_x": [], "trend_y": []})
        bucket["trend_x"].append(float(row.time_s))
        bucket["trend_y"].append(float(row.value))

    factors: list[FactorTrendSeriesOut] = []
    for code, scalar in scalar_rows.items():
        defn = definitions.get(code)
        series = by_code.get(code, {"trend_x": [], "trend_y": []})
        factors.append(
            FactorTrendSeriesOut(
                feature_code=code,
                feature_name=defn.name if defn else code,
                unit=scalar.unit,
                value=float(scalar.value),
                status=scalar.status,
                trend_x=series["trend_x"],
                trend_y=series["trend_y"],
            )
        )

    factors.sort(
        key=lambda f: (
            definitions[f.feature_code].sort_order
            if f.feature_code in definitions
            else 999
        )
    )

    return UploadFactorTrendsOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        channel=channel,
        features_status=upload.features_status,
        sampling_rate_hz=float(cfg["sampling_rate_hz"]),
        factors=factors,
    )


@router.get("/uploads/{upload_id}/features/compare", response_model=FeatureCompareOut)
def compare_upload_features(
    upload_id: UUID,
    baseline_id: UUID | None = Query(None),
    channel: int | None = Query(None, ge=0, le=31),
    db: Session = Depends(get_db),
):
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")

    cfg = _resolve_config(db, upload, upload.channel_count)
    if upload.parse_status == "parsed":
        try:
            upload = ensure_upload_features_ready(db, upload, float(cfg["sampling_rate_hz"]))
        except Exception as exc:
            feature_crud.mark_upload_features_failed(db, upload.id, str(exc))
            raise HTTPException(status_code=422, detail=f"Feature compute failed: {exc}")

    if baseline_id is None:
        baseline = baseline_crud.get_primary_baseline(db, upload.sensor_id)
        if not baseline:
            raise HTTPException(status_code=404, detail="No primary baseline for this sensor")
        baseline_id = baseline.id
    else:
        baseline = baseline_crud.get_baseline_by_id(db, baseline_id)
        if not baseline:
            raise HTTPException(status_code=404, detail="Baseline not found")

    definitions = {d.code: d.name for d in feature_crud.get_feature_definitions(db)}
    upload_rows = feature_crud.get_measurement_features(db, upload_id, channel=channel)
    baseline_map = {
        (r.channel, r.feature_code): float(r.value)
        for r in feature_crud.get_baseline_features(db, baseline_id, channel=channel)
    }

    items: list[FeatureCompareItemOut] = []
    for r in upload_rows:
        bval = baseline_map.get((r.channel, r.feature_code))
        pct = (100.0 * float(r.value) / bval) if bval and bval > 1e-30 else None
        items.append(
            FeatureCompareItemOut(
                channel=r.channel,
                feature_code=r.feature_code,
                feature_name=definitions.get(r.feature_code),
                unit=r.unit,
                upload_value=float(r.value),
                baseline_value=bval,
                percent_of_baseline=pct,
                status=r.status,
            )
        )

    return FeatureCompareOut(
        upload_id=upload_id,
        baseline_id=baseline_id,
        channel=channel,
        items=items,
        summary=_summary_from_rows(upload_rows),
    )
