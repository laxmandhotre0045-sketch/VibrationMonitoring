"""Device-facing measurement ingestion.

Everything else in the API is driven by a signed-in human holding a bearer
token. This router is the one entry point authenticated by an `X-API-Key`
device credential instead, which is why it lives apart from
`routers/measurements.py` rather than as another endpoint on it — that router
applies `get_current_user` to every route it owns.

What arrives here is already parsed, so the endpoint's job is to normalise the
payload into the same structure `pdf_parser` produces from a CSV and then hand
it to the existing pipeline. Plots, features, threshold evaluation and alert
webhooks are all shared with the manual upload path; a device measurement is a
different *source*, not a different pipeline.
"""
import json
import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.crud import baseline as baseline_crud
from app.crud import measurement as measurement_crud
from app.database import get_db
from app.dependencies.api_key import require_api_key
from app.models.integration import ApiKey
from app.schemas.ingest import MeasurementIngest, MeasurementIngestAck
from app.schemas.raw_vibration import RawTimebaseOut, RawUploadAck
<<<<<<< HEAD
from app.services.measurement_pipeline import resolve_config, run_pipeline
=======
from app.services.device_declaration import record_declaration
from app.services.feature_storage import persist_upload_features_and_trends
>>>>>>> 28b0aa6724005c5bf547cf3238877fa0ff1c5aa4
from app.services.plot_generator import save_parsed_data
from app.services.raw_storage import store_capture
from app.services.raw_vibration import (
    DEFAULT_SAMPLE_RATE_HZ,
    RawValidationError,
    inspect_timestamps,
    normalize_timebase,
    parse_raw_csv,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ingest",
    tags=["Ingest"],
    dependencies=[Depends(require_api_key)],
)


def _as_utc(value: datetime) -> datetime:
    """Normalise the device's capture time to an aware UTC instant.

    Devices report local time with an offset, UTC, or — the awkward case — no
    offset at all. An offset-less stamp is taken as UTC rather than rejected,
    since that is what an unconfigured device almost always means, and the
    column is timestamptz like the rest of this table so the value has to be
    aware either way.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_parsed_payload(data: MeasurementIngest, sampling_rate_hz: float) -> dict:
    """Shape the burst exactly like `pdf_parser.parse_sensor_file` output."""
    channel_count = len(data.channels)
    sample_count = data.sample_count

    if data.timestamps is not None:
        timestamps = list(data.timestamps)
    else:
        # Validation guarantees a rate is present whenever timestamps are not.
        timestamps = [i / sampling_rate_hz for i in range(sample_count)]

    return {
        "timestamps": timestamps,
        "channels": {f"ch{i}": list(data.channels[f"ch{i}"]) for i in range(channel_count)},
        "sample_count": sample_count,
        "channel_count": channel_count,
        "detected_channel_count": channel_count,
    }


@router.post(
    "/raw",
    response_model=RawUploadAck,
    status_code=201,
    summary="Post a raw 25 kSPS CSV snapshot from global_uploader.py",
)
async def ingest_raw_csv(
    device_id: str = Form(..., description="Device id as registered on the sensor"),
    file: UploadFile = File(..., description="CSV: timestamp_,ch0,ch1,…,ch7"),
    sample_rate_hz: float | None = Form(
        None,
        description="Declared acquisition rate. Defaults to the sensor's configured rate.",
    ),
    expected_channels: int = Form(8),
    measured_at: datetime | None = Form(None, description="Capture time (ISO 8601). Defaults to now."),
    rotation_speed_rpm: float | None = Form(None),
    sample_unit: str | None = Form(
        None,
        description="What the CSV values physically are: g, V or mm/s. The "
                    "Beckhoff gateway applies counts x (5 V / 32768) / "
                    "sensitivity before publishing, so it sends 'g'. Without "
                    "this the sensor stays unconfirmed and every severity is "
                    "withheld (VIK-005).",
    ),
    sensitivity_mv_per_g: str | None = Form(
        None,
        description="Comma-separated transducer sensitivity per channel, in "
                    "mV/g, in channel order. Not uniform on this hardware: "
                    "500,500,100,100,100,100,100,100. Must have exactly one "
                    "value per channel or it is ignored outright.",
    ),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_api_key),
):
    """
    Store one raw acquisition window exactly as measured.

    Deliberately does NOT compute plots or features. At 25 kSPS across eight channels a
    one-second window is ~200k values, and running the derived-artefact pipeline on every
    window would neither keep up nor be raw. Analysis reads the stored samples later.
    """
    sensor = crud.get_sensor_by_device_id(db, device_id)
    if not sensor:
        raise HTTPException(
            status_code=404, detail=f"No sensor is registered with device_id '{device_id}'"
        )
    if not sensor.is_active:
        raise HTTPException(status_code=409, detail=f"Sensor for device_id '{device_id}' is deactivated")

    filename = file.filename or "raw.csv"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")
    max_bytes = settings.max_pdf_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_pdf_size_mb}MB limit")

    text = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(status_code=400, detail="Could not decode CSV")

    # The rate the device was told to use is the reference for reading its time
    # column, so fall back to the sensor's saved configuration rather than a
    # module constant — the collector reads that same value from
    # GET /api/v1/acquisition/config and usually does not repeat it here.
    plot_config = measurement_crud.get_plot_config_by_sensor(db, sensor.id)
    if sample_rate_hz is None:
        sample_rate_hz = (
            float(plot_config.sampling_rate_hz) if plot_config else DEFAULT_SAMPLE_RATE_HZ
        )

    warnings: list[str] = []

    try:
        parsed = parse_raw_csv(text, expected_channels=expected_channels)
        # Device clocks write absolute wall-clock time in their own unit. Convert
        # to elapsed seconds before anything is stored, so the time axis means
        # the same thing for every snapshot and the waveform plots against real
        # elapsed time. Sample values are untouched.
        normalized, tb = normalize_timebase(parsed["timestamps"], sample_rate_hz)
        parsed["timestamps"] = normalized
        timebase = inspect_timestamps(normalized, sample_rate_hz)
    except RawValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if tb["resolved"] and tb["unit"] != "s":
        warnings.append(
            f"Time column read as {tb['unit']} and converted to seconds "
            f"({tb['observed_rate_hz']:.1f} SPS). Sample values unchanged."
        )
    elif not tb["resolved"]:
        warnings.append(
            f"Could not match the time column to the declared {sample_rate_hz:.0f} SPS "
            f"in any of s/ms/us/ns; it implies {tb['observed_rate_hz']:.1f} SPS read as "
            "seconds. Left unconverted — check the device clock unit."
        )

    if not timebase["rate_matches"]:
        warnings.append(
            f"Timestamp step implies {timebase['observed_rate_hz']:.1f} SPS, not the declared "
            f"{sample_rate_hz:.0f} SPS. Samples stored unchanged."
        )
    if not timebase["uniform"]:
        warnings.append(
            f"Sample interval varies by up to {timebase['max_step_deviation_s']:.3e} s. "
            "Samples stored unchanged."
        )

    # What the device says its own samples are. Recorded before the capture is
    # stored, so the very first snapshot from a gateway is already gradeable
    # rather than waiting for a second one -- VIK-005 refuses on an
    # unconfirmed sensor, and until this existed nothing ever confirmed one.
    declaration = record_declaration(
        db,
        sensor=sensor,
        plot_config=plot_config,
        sample_unit=sample_unit,
        sensitivity_csv=sensitivity_mv_per_g,
        channel_count=parsed["channel_count"],
    )
    warnings.extend(declaration.warnings)

    upload_id = uuid4()
    captured = _as_utc(measured_at) if measured_at else datetime.now(timezone.utc)

    os.makedirs(settings.measurement_upload_dir, exist_ok=True)
    raw_path = os.path.join(settings.measurement_upload_dir, f"{upload_id}.raw.csv")
    parsed_path = os.path.join(settings.measurement_upload_dir, f"{upload_id}.json")
    with open(raw_path, "wb") as handle:
        handle.write(content)

    upload = measurement_crud.create_upload_record(
        db,
        sensor.id,
        parsed["channel_count"],
        raw_path,
        upload_id=upload_id,
        original_filename=filename,
        source="device_raw",
        measured_at=captured,
        rotation_speed_rpm=rotation_speed_rpm,
        api_key_id=api_key.id,
    )

    try:
        save_parsed_data(parsed_path, parsed)
        # Samples also go into the database (migration 018) as float8[] rows.
        # The disk copy stays: it is the fallback for every snapshot ingested
        # before those tables existed.
        store_capture(
            db,
            upload_id=upload.id,
            sensor_id=sensor.id,
            parsed=parsed,
            sample_rate_hz=sample_rate_hz,
            start_epoch_s=tb["start_epoch_s"],
            timebase_unit=tb["unit"],
        )
        upload = measurement_crud.mark_upload_parsed(db, upload.id, parsed_path, parsed["sample_count"])
        baseline_crud.save_upload_data(
            db,
            upload_id=upload.id,
            sensor_id=sensor.id,
            original_filename=filename,
            file_format="csv",
            file_content=content,
            # Deliberately empty for the raw path. The samples are already held twice —
            # verbatim in file_content above and normalised in the .json written beside
            # it — and a third copy as JSONB costs seconds per snapshot, because Postgres
            # must parse ~225k numbers into binary JSONB. An empty dict is falsy, so
            # `_load_parsed_for_upload` skips it and reads the file instead.
            parsed_data={},
            channel_count=parsed["channel_count"],
            sample_count=parsed["sample_count"],
        )
    except Exception as exc:
        measurement_crud.mark_upload_failed(db, upload.id, str(exc))
        logger.exception("Raw ingest storage failed for device %s", device_id)
        raise HTTPException(status_code=422, detail=f"Could not store raw snapshot: {exc}")

    return RawUploadAck(
        upload_id=upload.id,
        sensor_id=sensor.id,
        device_id=device_id,
        original_filename=filename,
        sample_count=parsed["sample_count"],
        channel_count=parsed["channel_count"],
        sample_rate_hz=sample_rate_hz,
        measured_at=captured,
        timebase=RawTimebaseOut(**timebase),
        warnings=warnings,
    )


@router.post(
    "/measurements",
    response_model=MeasurementIngestAck,
    status_code=201,
    summary="Post a captured waveform from a device",
)
def ingest_measurement(
    data: MeasurementIngest,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_api_key),
):
    """
    Accepts one capture burst and runs it through the standard pipeline.

    The device is identified by `device_id` on the payload; the API key
    authenticates the caller but does not scope it to a single sensor, so the
    same key can serve a gateway relaying several devices.
    """
    sensor = crud.get_sensor_by_device_id(db, data.device_id)
    if not sensor:
        raise HTTPException(
            status_code=404,
            detail=f"No sensor is registered with device_id '{data.device_id}'",
        )
    if not sensor.is_active:
        raise HTTPException(
            status_code=409,
            detail=f"Sensor for device_id '{data.device_id}' is deactivated",
        )

    upload_id = uuid4()
    channel_count = len(data.channels)
    measured_at = _as_utc(data.measured_at)

    # The device's own rate describes this burst; the stored plot configuration
    # is only a fallback for devices that do not report one. `resolve_config`
    # applies exactly that precedence.
    cfg = resolve_config(db, sensor.id, channel_count, data.sampling_rate_hz)
    sampling_rate_hz = float(cfg["sampling_rate_hz"])

    parsed = _to_parsed_payload(data, sampling_rate_hz)
    raw_bytes = data.model_dump_json().encode("utf-8")

    os.makedirs(settings.measurement_upload_dir, exist_ok=True)
    # Two files with distinct jobs: what the device actually sent, kept verbatim
    # for provenance, and the normalised form the pipeline reads.
    raw_path = os.path.join(settings.measurement_upload_dir, f"{upload_id}.device.json")
    parsed_path = os.path.join(settings.measurement_upload_dir, f"{upload_id}.json")
    with open(raw_path, "wb") as handle:
        handle.write(raw_bytes)

    filename = f"{data.device_id}-{measured_at:%Y%m%dT%H%M%S}Z.json"
    upload = measurement_crud.create_upload_record(
        db,
        sensor.id,
        channel_count,
        raw_path,
        upload_id=upload_id,
        original_filename=filename,
        source="device",
        measured_at=measured_at,
        rotation_speed_rpm=data.rotation_speed_rpm,
        api_key_id=api_key.id,
    )

    # Store, plots, features and the alert count all live in the pipeline, which
    # the manual upload path runs too. Alert webhooks still fire from inside the
    # features step once its rows are committed.
    result = run_pipeline(
        db,
        upload,
        parsed,
        cfg,
        raw_content=raw_bytes,
        original_filename=filename,
        file_format="json",
        parsed_path=parsed_path,
    )
    upload = result.upload

    # The endpoint, not the pipeline, decides what a failure is worth. A failed
    # store is fatal: nothing was written, so there is no parse for plots,
    # features or a later reprocess to read. Plots and features are graded
    # separately — a device that keeps delivering is more valuable than one
    # rejected because a derived artefact failed, and both statuses are recorded
    # on the upload for later reprocessing.
    if result.failed("store"):
        error = result.error_for("store")
        logger.error("Ingest storage failed for device %s: %s", data.device_id, error)
        raise HTTPException(status_code=422, detail=f"Could not store measurement: {error}")

    return MeasurementIngestAck(
        upload_id=upload.id,
        sensor_id=sensor.id,
        device_id=data.device_id,
        sample_count=parsed["sample_count"],
        channel_count=channel_count,
        measured_at=measured_at,
        sampling_rate_hz=sampling_rate_hz,
        parse_status=upload.parse_status,
        plots_status=upload.plots_status,
        features_status=upload.features_status,
        alerts_raised=result.alerts_raised,
    )
