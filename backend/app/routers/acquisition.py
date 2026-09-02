"""Acquisition & DAQ configuration.

One endpoint the existing Python acquisition script polls for everything it
needs — sample rate, block sizing, channel mapping and capture cadence — so the
collector does not carry its own copy of these constants and drift out of step
with the dashboard.

This module deliberately holds no MQTT logic. The broker connection, the
`Vibration_Data` subscription and the sample capture all live in the existing
Python collector; the backend only publishes the settings it should use and
stores the data it sends back through `/api/v1/ingest/*`.

Auth split:

  GET  is public by default, so the collector can fetch its settings with a bare
       HTTP GET and no credential handling. Note this differs from
       `/api/v1/measurements/acquisition`, whose router requires a bearer token.
       The response carries device and sensor IDs, so a deployment reachable
       beyond a trusted plant network should set
       `ACQUISITION_CONFIG_REQUIRE_KEY=true` and have the collector send the
       `X-API-Key` it already uses for `/api/v1/ingest/*`. A valid key is
       accepted either way.
  PUT  always requires an admin/engineer bearer token. Reading how the DAQ is
       configured is one thing; changing what the plant records is another.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import equipment as crud
from app.crud import integration as integration_crud
from app.crud import measurement as measurement_crud
from app.database import get_db
from app.dependencies.api_key import API_KEY_HEADER
from app.dependencies.auth import require_write_access
from app.models.sensor import SensorConfiguration
from app.schemas.acquisition import AcquisitionConfigOut, AcquisitionConfigUpdate
from app.schemas.equipment import SensorConfigUpdate
from app.schemas.measurement import PlotConfigCreate, PlotConfigUpdate
from app.services.acquisition_config import build_acquisition_config

router = APIRouter(prefix="/api/v1/acquisition", tags=["Acquisition & DAQ"])


def optional_api_key(
    x_api_key: Optional[str] = Header(default=None, alias=API_KEY_HEADER),
    db: Session = Depends(get_db),
) -> None:
    """Accept an API key always; demand one only when configured to.

    Separate from `require_api_key` because that dependency rejects a missing
    header outright, which would stop a bare edge GET from working in the
    default configuration.
    """
    if x_api_key:
        key = integration_crud.resolve_api_key(db, x_api_key.strip())
        if key is None:
            raise HTTPException(
                status_code=401, detail="Invalid, revoked or expired API key"
            )
        integration_crud.touch_api_key(db, key)
        return

    if settings.acquisition_config_require_key:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Missing {API_KEY_HEADER} header. This deployment sets "
                "ACQUISITION_CONFIG_REQUIRE_KEY=true."
            ),
        )


def _resolve_sensor(
    db: Session,
    device_id: Optional[str],
    sensor_id: Optional[UUID],
) -> SensorConfiguration:
    """sensor_id wins, then device_id, then the most recently saved config.

    The no-parameter fallback exists so a single-machine edge deployment can
    poll `GET /api/v1/acquisition/config` with no query string at all.
    """
    if sensor_id is not None:
        sensor = crud.get_sensor_by_id(db, sensor_id)
        if not sensor:
            raise HTTPException(status_code=404, detail=f"Sensor {sensor_id} not found")
        return sensor

    if device_id:
        sensor = crud.get_sensor_by_device_id(db, device_id.strip())
        if not sensor:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No sensor found with device_id '{device_id}'. Set device_id on the "
                    "sensor under Equipment Master, then save acquisition settings."
                ),
            )
        return sensor

    latest = measurement_crud.get_latest_plot_config(db)
    if latest is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No acquisition configuration has been saved yet. Configure a sensor "
                "under Settings → Platform → Acquisition & DAQ, or pass ?device_id=…"
            ),
        )
    sensor = crud.get_sensor_by_id(db, latest.sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Configured sensor no longer exists")
    return sensor


def _config_response(db: Session, sensor: SensorConfiguration) -> AcquisitionConfigOut:
    plot_config = measurement_crud.get_plot_config_by_sensor(db, sensor.id)
    payload = build_acquisition_config(sensor, plot_config)
    return AcquisitionConfigOut(**payload)


@router.get(
    "/config",
    response_model=AcquisitionConfigOut,
    dependencies=[Depends(optional_api_key)],
    summary="Acquisition & DAQ configuration (public by default — polled by the Python collector)",
)
def get_acquisition_config(
    device_id: Optional[str] = Query(
        default=None, description="Edge device ID / MAC, e.g. 08:F9:E0:AD:FB:36"
    ),
    sensor_id: Optional[UUID] = Query(default=None, description="Platform sensor UUID"),
    db: Session = Depends(get_db),
):
    """Everything the existing Python acquisition script needs, in one call.

    ```
    GET /api/v1/acquisition/config
    GET /api/v1/acquisition/config?device_id=08:F9:E0:AD:FB:36
    GET /api/v1/acquisition/config?sensor_id=<uuid>
    ```

    `samplesPerBlock` is authoritative — capture exactly that many samples per
    block. It is `2 * lor` because LOR counts spectral lines from DC to Nyquist
    (see `services/acquisition_config.py`), so deriving a block length from
    `lor` alone would halve the frequency resolution.

    `collectionIntervalMinutes` is the wait between captures. It is unrelated to
    `sampleRateHz` and to `blockTimeSeconds`.

    No MQTT settings are returned: the broker connection and the
    `Vibration_Data` subscription stay entirely inside the collector script.
    """
    sensor = _resolve_sensor(db, device_id, sensor_id)
    return _config_response(db, sensor)


@router.get(
    "/config/{device_id:path}",
    response_model=AcquisitionConfigOut,
    dependencies=[Depends(optional_api_key)],
    summary="Acquisition & DAQ configuration by device_id in the path",
)
def get_acquisition_config_by_path(device_id: str, db: Session = Depends(get_db)):
    """Same payload as `/config`, with the device ID as a path segment.

    Exists so a collector written as `f"{BASE_URL}/{SENSOR_ID}"` works without
    being rewritten to use a query string. Declared `:path` because a MAC-style
    ID contains colons, which would otherwise be read as a path parameter
    converter and 404.
    """
    sensor = _resolve_sensor(db, device_id, None)
    return _config_response(db, sensor)


@router.put(
    "/config",
    response_model=AcquisitionConfigOut,
    dependencies=[Depends(require_write_access)],
    summary="Save acquisition and channel-mapping settings",
)
def update_acquisition_config(data: AcquisitionConfigUpdate, db: Session = Depends(get_db)):
    """Partial save. Omitted fields keep their stored values.

    Writes to two places, because they describe different things: acquisition
    settings live on the sensor's plot configuration, while sensitivity is
    transducer hardware and lives on the sensor record.
    """
    sensor = crud.get_sensor_by_id(db, data.sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail=f"Sensor {data.sensor_id} not found")

    existing = measurement_crud.get_plot_config_by_sensor(db, data.sensor_id)

    # Fmax against Nyquist is only fully checkable here: a partial save may send
    # Fmax while the sample rate stays as stored, and vice versa.
    effective_rate = data.sample_rate_hz
    if effective_rate is None and existing is not None:
        effective_rate = float(existing.sampling_rate_hz)
    effective_fmax = data.fmax_hz
    if effective_fmax is None and existing is not None and existing.frequency_max_hz:
        effective_fmax = float(existing.frequency_max_hz)

    if effective_rate and effective_fmax and effective_fmax >= effective_rate / 2.0:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Fmax {effective_fmax:g} Hz must stay below Nyquist {effective_rate / 2.0:g} Hz "
                f"for sample rate {effective_rate:g} Hz. Lower Fmax or raise the sample rate."
            ),
        )

    fields: dict = {}
    if data.sample_rate_hz is not None:
        fields["sampling_rate_hz"] = data.sample_rate_hz
    if data.fmax_hz is not None:
        fields["frequency_max_hz"] = data.fmax_hz
    if data.lor is not None:
        fields["fft_lines"] = data.lor
    if data.window_type is not None:
        fields["window_type"] = data.window_type
    if data.average_count is not None:
        fields["averaging"] = data.average_count
    if data.overlap_percentage is not None:
        fields["overlap_percent"] = data.overlap_percentage
    if data.total_channel_count is not None:
        fields["channel_count"] = data.total_channel_count
    if data.collection_interval_minutes is not None:
        fields["collection_interval_minutes"] = data.collection_interval_minutes
    if data.channel_map is not None:
        fields["channel_map"] = [entry.model_dump() for entry in data.channel_map]

    if existing is None:
        # First save for this sensor. active_channel stays 0 and enabled_plots
        # falls back to the full set, matching /measurements/configure.
        created = PlotConfigCreate(
            sensor_id=data.sensor_id,
            channel_count=fields.get("channel_count", 8),
            **{k: v for k, v in fields.items() if k != "channel_count"},
        )
        measurement_crud.create_plot_config(db, created)
    elif fields:
        channel_count = fields.get("channel_count", existing.channel_count)
        if existing.active_channel >= channel_count:
            # Lowering the channel count would otherwise leave active_channel
            # pointing at a channel the device no longer reports.
            fields["active_channel"] = channel_count - 1
        measurement_crud.update_plot_config(db, data.sensor_id, PlotConfigUpdate(**fields))

    if data.sensitivity_mv_per_g is not None:
        crud.update_sensor(
            db,
            data.sensor_id,
            SensorConfigUpdate(sensitivity=data.sensitivity_mv_per_g, sensitivity_unit="mV/g"),
        )

    db.refresh(sensor)
    return _config_response(db, sensor)
