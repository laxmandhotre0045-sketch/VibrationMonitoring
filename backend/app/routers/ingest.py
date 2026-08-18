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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.crud import baseline as baseline_crud
from app.crud import feature as feature_crud
from app.crud import measurement as measurement_crud
from app.database import get_db
from app.dependencies.api_key import require_api_key
from app.models.integration import ApiKey
from app.schemas.ingest import MeasurementIngest, MeasurementIngestAck
from app.services.feature_storage import persist_upload_features_and_trends
from app.services.plot_generator import save_parsed_data
from app.services.plot_storage import persist_all_plot_results

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
    # is only a fallback for devices that do not report one.
    config = measurement_crud.get_plot_config_by_sensor(db, sensor.id)
    cfg = (
        measurement_crud.config_to_dict(config)
        if config
        else measurement_crud.default_config_dict(channel_count)
    )
    sampling_rate_hz = float(data.sampling_rate_hz or cfg["sampling_rate_hz"])
    cfg = {**cfg, "sampling_rate_hz": sampling_rate_hz}

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

    try:
        save_parsed_data(parsed_path, parsed)
        upload = measurement_crud.mark_upload_parsed(
            db, upload.id, parsed_path, parsed["sample_count"]
        )
        baseline_crud.save_upload_data(
            db,
            upload_id=upload.id,
            sensor_id=sensor.id,
            original_filename=filename,
            file_format="json",
            file_content=raw_bytes,
            parsed_data=parsed,
            channel_count=channel_count,
            sample_count=parsed["sample_count"],
        )
    except Exception as exc:
        measurement_crud.mark_upload_failed(db, upload.id, str(exc))
        logger.exception("Ingest storage failed for device %s", data.device_id)
        raise HTTPException(status_code=422, detail=f"Could not store measurement: {exc}")

    # Plots and features are graded separately: a device that keeps delivering is
    # more valuable than one rejected because a derived artefact failed, and both
    # statuses are recorded on the upload for later reprocessing.
    try:
        persist_all_plot_results(db, upload, parsed_path, cfg)
        upload = measurement_crud.mark_upload_plots_ready(db, upload.id)
    except Exception as plot_err:
        upload = measurement_crud.mark_upload_plots_failed(db, upload.id, str(plot_err))
        logger.warning("Plot generation failed for upload %s: %s", upload.id, plot_err)

    try:
        # Alert webhooks fire from inside here once the feature rows are committed.
        persist_upload_features_and_trends(db, upload, parsed, sampling_rate_hz)
        upload = feature_crud.mark_upload_features_ready(db, upload.id)
    except Exception as feat_err:
        upload = feature_crud.mark_upload_features_failed(db, upload.id, str(feat_err))
        logger.warning("Feature extraction failed for upload %s: %s", upload.id, feat_err)

    alerts_raised = sum(
        1
        for row in feature_crud.get_measurement_features(db, upload.id)
        if row.status in ("warning", "critical")
    )

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
        alerts_raised=alerts_raised,
    )
