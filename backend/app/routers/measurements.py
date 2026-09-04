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
from app.schemas.migration import MigrationSummaryOut, OneXMigrationOut
from app.schemas.raw_vibration import (
    RawAnalysisOut,
    RawSamplesOut,
    RawSnapshotListOut,
    RawSnapshotSummaryOut,
)
from app.services.raw_storage import load_capture
from app.services.raw_analysis import (
    channel_samples,
    compute_raw_spectrum,
    compute_raw_statistics,
    estimate_shaft_hz,
)
from app.services.raw_vibration import (
    DEFAULT_WINDOW,
    MAX_WINDOW,
    normalize_timebase,
    window_samples,
)
from app.services.casing_orbit import build_casing_orbit
from app.services.one_x_migration import (
    AMPLITUDE_UNIT,
    SOURCE_UNIT,
    SPEED_SOURCE_ESTIMATED,
    SPEED_SOURCE_OVERRIDE,
    build_migration_point,
    summarise_migration,
)
from app.services.acquisition_config import build_edge_acquisition_config, resolve_channel_map
from app.services.waterfall import (
    DEFAULT_MAX_PEAKS,
    DEFAULT_MAX_POINTS,
    WATERFALL_POOL_LIMIT,
    amplitude_axis_label,
    build_waterfall,
    detect_spectrum_peaks,
    select_uploads,
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
    The FFT-derived shaft estimate for one capture.

    Prefers the stored feature. Snapshots posted by the collector have none —
    the raw ingest path deliberately skips the derived-artefact pipeline — so
    rather than leave the orbit and 1x-migration plots without a shaft frequency,
    fall back to estimating it from the stored samples with the same band-limited
    peak search the feature pipeline uses.

    Still does not trigger full feature computation: that runs an FFT and a
    Hilbert transform over thirty-two segments per channel, which is far more
    work than this one number needs.
    """
    try:
        rows = feature_crud.get_measurement_features(db, upload_id, channel=channel)
    except Exception:
        rows = []
    for row in rows:
        meta = row.metadata_ or {}
        value = meta.get("estimated_shaft_hz")
        if isinstance(value, (int, float)) and value > 0:
            return float(value)

    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if upload is None or upload.parse_status != "parsed":
        return None
    try:
        parsed, rate = _load_raw_parsed(db, upload)
        samples = channel_samples(parsed, channel)
    except (HTTPException, ValueError):
        return None
    return estimate_shaft_hz(samples, rate)


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


# ── Raw vibration snapshots (25 kSPS device data, stored verbatim) ───────────

def _raw_snapshot_summary(upload, has_samples: bool) -> RawSnapshotSummaryOut:
    return RawSnapshotSummaryOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        original_filename=upload.original_filename,
        captured_at=upload.created_at,
        measured_at=getattr(upload, "measured_at", None),
        sample_count=upload.sample_count,
        channel_count=upload.channel_count,
        source=upload.source,
        has_raw_samples=has_samples,
    )


@router.get(
    "/raw/snapshots",
    response_model=RawSnapshotListOut,
    summary="List stored raw snapshots for a sensor, newest first",
)
def list_raw_snapshots(
    sensor_id: UUID = Query(...),
    limit: int = Query(50, ge=1, le=200),
    source: str | None = Query("device_raw", description="Filter by upload source; omit for all"),
    db: Session = Depends(get_db),
):
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    items, total = measurement_crud.list_uploads_by_sensor(
        db, sensor_id, parse_status="parsed", page=1, page_size=limit
    )
    if source:
        items = [u for u in items if u.source == source]

    stored = measurement_crud.get_stored_upload_ids(db, [u.id for u in items])
    return RawSnapshotListOut(
        sensor_id=sensor_id,
        total=len(items) if source else total,
        items=[_raw_snapshot_summary(u, u.id in stored) for u in items],
    )


@router.get(
    "/raw/latest",
    response_model=RawSamplesOut,
    summary="Newest raw snapshot for a sensor, windowed",
)
def get_latest_raw(
    sensor_id: UUID = Query(...),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_WINDOW, ge=1, le=MAX_WINDOW),
    channels: str | None = Query(None, description="Comma-separated channel indexes, e.g. 0,1,2"),
    source: str | None = Query("device_raw"),
    db: Session = Depends(get_db),
):
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    items, _total = measurement_crud.list_uploads_by_sensor(
        db, sensor_id, parse_status="parsed", page=1, page_size=200
    )
    if source:
        items = [u for u in items if u.source == source]
    if not items:
        raise HTTPException(
            status_code=404,
            detail=f"No parsed raw snapshots for this sensor"
            + (f" with source '{source}'" if source else ""),
        )

    return _raw_samples_response(db, items[0], offset, limit, channels)


@router.get(
    "/uploads/{upload_id}/raw",
    response_model=RawSamplesOut,
    summary="Raw samples of one snapshot, windowed",
)
def get_raw_samples(
    upload_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_WINDOW, ge=1, le=MAX_WINDOW),
    channels: str | None = Query(None, description="Comma-separated channel indexes, e.g. 0,1,2"),
    db: Session = Depends(get_db),
):
    """
    Returns stored samples verbatim inside the requested window.

    Windowed, never decimated: a browser must not be handed an unbounded series, but what
    it does receive is exactly what the device measured.
    """
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    if upload.parse_status != "parsed":
        raise HTTPException(
            status_code=422, detail=f"Upload not parsed: {upload.parse_error or upload.parse_status}"
        )
    return _raw_samples_response(db, upload, offset, limit, channels)


def _raw_samples_response(db, upload, offset: int, limit: int, channels: str | None) -> RawSamplesOut:
    parsed, rate = _load_raw_parsed(db, upload)

    selected: list[int] | None = None
    if channels:
        try:
            selected = [int(c) for c in channels.split(",") if c.strip() != ""]
        except ValueError:
            raise HTTPException(status_code=400, detail="channels must be comma-separated integers")

    window = window_samples(parsed, offset=offset, limit=limit, channels=selected)

    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    return RawSamplesOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        device_id=sensor.device_id if sensor else None,
        original_filename=upload.original_filename,
        measured_at=getattr(upload, "measured_at", None),
        captured_at=upload.created_at,
        sampleRate=rate,
        channelCount=int(parsed.get("channel_count") or upload.channel_count),
        offset=window["offset"],
        limit=limit,
        returned=window["returned"],
        total_samples=window["total_samples"],
        has_more=window["has_more"],
        channels=window["channels"],
        samples=window["samples"],
    )


def _load_raw_parsed(db: Session, upload) -> tuple[dict, float]:
    """Samples plus a trustworthy sample rate for one raw snapshot.

    Three things happen here, in order:

    1. Prefer the database rows written since migration 018. Snapshots ingested
       before that have none, so fall back to the on-disk parsed JSON.
    2. Repair the time axis if it needs it. Captures stored before timebase
       normalisation existed still carry the device's raw wall-clock column —
       epoch milliseconds, in the case seen in the field — which makes every
       frequency read 1000x low. Re-normalising here is idempotent: data already
       stored as elapsed seconds passes through untouched.
    3. Report the rate the time axis actually implies, preferring it over the
       configured rate, so the spectrum is scaled by what was measured.
    """
    cfg = _resolve_config(db, upload, upload.channel_count)
    declared = float(cfg["sampling_rate_hz"])

    parsed = load_capture(db, upload.id)
    if parsed is None:
        try:
            parsed = _load_parsed_for_upload(db, upload)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"No stored samples for this upload: {exc}"
            )
    else:
        # Rows written by the current ingest path are already normalised, and
        # the capture row carries the rate that was resolved at the time.
        stored_rate = float(parsed.get("sampling_rate_hz") or 0.0)
        if stored_rate > 0:
            return parsed, stored_rate

    timestamps = parsed.get("timestamps") or []
    if len(timestamps) > 1:
        normalized, tb = normalize_timebase(timestamps, declared)
        parsed = {**parsed, "timestamps": normalized}
        if tb["observed_rate_hz"] > 0:
            # 1/0.00004 lands on 24999.999999999996; round the reported rate only.
            return parsed, round(tb["observed_rate_hz"], 6)

    return parsed, declared


# ── Raw snapshot analysis (waveform stats + spectrum) ────────────────────────

def _raw_analysis_response(db, upload, channel: int) -> RawAnalysisOut:
    """Spectrum + statistics for one channel of one stored snapshot.

    Uses the sensor's saved LOR and Fmax so the spectrum matches the analysis
    tabs, and the shared feature extractor so the statistics match the health
    page. Nothing is recomputed with a private FFT.
    """
    parsed, rate = _load_raw_parsed(db, upload)
    cfg = _resolve_config(db, upload, upload.channel_count)

    try:
        samples = channel_samples(parsed, channel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if len(samples) < 4:
        raise HTTPException(status_code=422, detail='Need at least 4 samples to analyse')

    try:
        spectrum = compute_raw_spectrum(
            samples,
            rate,
            fft_lines=cfg.get('fft_lines'),
            frequency_max_hz=cfg.get('frequency_max_hz'),
        )
        statistics = compute_raw_statistics(samples, rate)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Channel wiring, so the page can say 'CH3 — Axial' rather than 'channel 2'.
    plot_config = measurement_crud.get_plot_config_by_sensor(db, upload.sensor_id)
    stored_map = getattr(plot_config, 'channel_map', None) if plot_config else None
    channel_count = int(parsed.get('channel_count') or upload.channel_count)
    mapping = resolve_channel_map(stored_map, channel_count)
    entry = mapping[channel] if channel < len(mapping) else {}

    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    return RawAnalysisOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        device_id=sensor.device_id if sensor else None,
        original_filename=upload.original_filename,
        captured_at=upload.created_at,
        measured_at=getattr(upload, 'measured_at', None),
        channel=channel,
        channel_label=entry.get('label'),
        machine_axis=entry.get('machine_axis'),
        signal_type=entry.get('signal_type'),
        sample_rate_hz=rate,
        sample_count=len(samples),
        channel_count=channel_count,
        spectrum=spectrum,
        statistics=statistics,
    )


@router.get(
    '/raw/latest/analysis',
    response_model=RawAnalysisOut,
    summary='FFT spectrum and vibration statistics for the newest raw snapshot',
)
def get_latest_raw_analysis(
    sensor_id: UUID = Query(...),
    channel: int = Query(0, ge=0, le=31, description='0-based channel index'),
    source: str | None = Query('device_raw'),
    db: Session = Depends(get_db),
):
    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail='Sensor not found')

    items, _total = measurement_crud.list_uploads_by_sensor(
        db, sensor_id, parse_status='parsed', page=1, page_size=200
    )
    if source:
        items = [u for u in items if u.source == source]
    if not items:
        raise HTTPException(
            status_code=404,
            detail='No parsed raw snapshots for this sensor'
            + (f" with source '{source}'" if source else ''),
        )
    return _raw_analysis_response(db, items[0], channel)


@router.get(
    '/uploads/{upload_id}/raw/analysis',
    response_model=RawAnalysisOut,
    summary='FFT spectrum and vibration statistics for one raw snapshot',
)
def get_raw_analysis(
    upload_id: UUID,
    channel: int = Query(0, ge=0, le=31, description='0-based channel index'),
    db: Session = Depends(get_db),
):
    upload = measurement_crud.get_upload_by_id(db, upload_id)
    if not upload:
        raise HTTPException(status_code=404, detail='Upload not found')
    return _raw_analysis_response(db, upload, channel)


# ── 1x amplitude migration (one point per capture, across captures) ──────────

@router.get(
    "/one-x-migration",
    response_model=OneXMigrationOut,
    summary="1x amplitude migration: Vertical vs Horizontal 1x response across captures",
)
def get_one_x_migration(
    sensor_id: UUID = Query(..., description="Sensor UUID"),
    x_channel: int = Query(0, ge=0, le=31, description="Vertical channel"),
    y_channel: int = Query(1, ge=0, le=31, description="Horizontal channel"),
    count: int = Query(40, ge=2, le=200, description="How many captures to trend"),
    mode: str = Query("last", description="last | oldest | random"),
    shaft_hz: float | None = Query(
        None, gt=0, description="Override the per-capture FFT shaft estimate"
    ),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    """
    Read-only. One point per capture: X = vertical 1x amplitude, Y = horizontal 1x
    amplitude, both as double-integrated displacement.

    Each capture uses its OWN estimated shaft frequency — a fixed bin would turn ordinary
    speed drift into fake migration.

    This is NOT a shaft-centreline plot. The sensors are AC accelerometers on the casing;
    static shaft position, attitude angle, eccentricity and bearing clearance require
    DC-capable proximity probes and are neither computed nor reported.
    """
    if x_channel == y_channel:
        raise HTTPException(status_code=400, detail="X and Y must be different channels")
    if mode not in SELECTION_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {SELECTION_MODES}")
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be on or before to_date")

    sensor = crud.get_sensor_by_id(db, sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    cfg = measurement_crud.get_plot_config_by_sensor(db, sensor_id)
    cfg = (
        measurement_crud.config_to_dict(cfg)
        if cfg
        else measurement_crud.default_config_dict(max(x_channel, y_channel) + 1)
    )
    sampling_rate = float(cfg["sampling_rate_hz"])

    uploads, total_parsed = measurement_crud.list_uploads_by_sensor(
        db,
        sensor_id,
        from_date=from_date,
        to_date=to_date,
        parse_status="parsed",
        page=1,
        page_size=WATERFALL_POOL_LIMIT,
    )
    # Same selection helper the waterfall uses: returns oldest -> newest.
    selected, _pool = select_uploads(uploads, mode, count)

    points: list[dict] = []
    skipped = 0
    for index, upload in enumerate(selected):
        try:
            parsed = _load_parsed_for_upload(db, upload)
            channels = parsed.get("channels") or {}
            samples_x = channels.get(f"ch{x_channel}")
            samples_y = channels.get(f"ch{y_channel}")
        except Exception:
            samples_x = samples_y = None

        resolved_shaft = shaft_hz or _stored_estimated_shaft_hz(db, upload.id, x_channel)
        point = build_migration_point(
            upload_id=upload.id,
            captured_at=upload.created_at,
            sequence=index + 1,
            samples_x=samples_x,
            samples_y=samples_y,
            sampling_rate_hz=sampling_rate,
            shaft_hz=resolved_shaft,
            speed_source=SPEED_SOURCE_OVERRIDE if shaft_hz else SPEED_SOURCE_ESTIMATED,
            x_channel=x_channel,
            y_channel=y_channel,
        )
        if point["quality"] == "invalid":
            skipped += 1
        points.append(point)

    summary = summarise_migration(points)

    warnings: list[str] = []
    if summary["valid_count"] < 2:
        warnings.append("At least two valid captures are required to show migration.")
    if summary["shaft_hz_min"] and summary["shaft_hz_max"]:
        drift = summary["shaft_hz_max"] - summary["shaft_hz_min"]
        if drift > 0:
            warnings.append(
                f"Shaft estimate varies {summary['shaft_hz_min']:.2f}-{summary['shaft_hz_max']:.2f} Hz "
                "across the selection; each capture is tracked at its own 1x."
            )

    return OneXMigrationOut(
        sensor_id=sensor_id,
        x_channel=x_channel,
        y_channel=y_channel,
        amplitude_unit=AMPLITUDE_UNIT,
        source_unit=SOURCE_UNIT,
        selection_mode=mode,
        requested_count=count,
        returned_count=len(points),
        total_available=total_parsed,
        skipped_count=skipped,
        sampling_rate_hz=sampling_rate,
        sensor_label=sensor.sensor_type,
        sensor_orientation=sensor.orientation,
        mounting_location=sensor.mounting_location,
        points=points,
        summary=MigrationSummaryOut(
            valid_count=summary["valid_count"],
            x_max=summary["x_max"],
            y_max=summary["y_max"],
            shaft_hz_min=summary["shaft_hz_min"],
            shaft_hz_max=summary["shaft_hz_max"],
        ),
        warnings=warnings,
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
        captured_at=upload.measured_at or upload.created_at,
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
