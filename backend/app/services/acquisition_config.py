"""
Build edge-device acquisition JSON from sensor + plot configuration.
Compatible with UDP acquisition scripts that poll config by device_id (MAC-style).
"""
from typing import Any

from app.models.measurement import PlotConfiguration
from app.models.sensor import SensorConfiguration
from app.services.signal_processing import SAMPLES_PER_LINE

DEFAULT_SAMPLE_RATE_HZ = 256_000.0
DEFAULT_LOR = 51_200
DEFAULT_FMAX_HZ = 15_000.0
DEFAULT_CHANNEL_COUNT = 8
DEFAULT_WINDOW = "HANNING"
DEFAULT_MINUTES = "1"
DEFAULT_AVERAGING = 1
DEFAULT_OVERLAP = 0


def _axis_from_orientation(orientation: str) -> str:
    o = (orientation or "").upper()
    if "HORIZONTAL" in o or o == "X" or o == "AXIAL":
        return "HORIZONTAL"
    if "AXIAL" in o:
        return "AXIAL"
    return "VERTICAL"


def compute_acquisition_formula(
    sample_rate_hz: float,
    lor: int,
    overlap_decimal: float = 0.0,
    average_count: int = 1,
) -> dict[str, float]:
    # lor is lines of resolution, so the device must capture SAMPLES_PER_LINE
    # samples per line — the same block sizing compute_fft_spectrum applies.
    required_samples = lor * SAMPLES_PER_LINE
    block_time = required_samples / sample_rate_hz
    step = int(required_samples * (1.0 - overlap_decimal))
    return {
        "frequencyResolutionHz": sample_rate_hz / required_samples,
        "blockTimeSeconds": block_time,
        "sampleRateHz": sample_rate_hz,
        "requiredSamples": float(required_samples),
        "overlapDecimal": overlap_decimal,
        "totalAcquisitionTimeSeconds": block_time * average_count,
        "averageCount": float(average_count),
        "fmaxHz": DEFAULT_FMAX_HZ,
        "lor": float(lor),
        "stepSizeSamples": float(step if step > 0 else required_samples),
    }


def build_channels(sensor: SensorConfiguration, channel_count: int) -> list[dict[str, Any]]:
    axis = _axis_from_orientation(sensor.orientation)
    transducer = "MEMS" if "MEMS" in (sensor.sensor_type or "").upper() else sensor.sensor_type or "MEMS"
    return [
        {
            "transducerType": transducer,
            "signalType": "VIBRATION",
            "channelIndex": i + 1,
            "machineAxis": axis,
        }
        for i in range(channel_count)
    ]


def build_edge_acquisition_config(
    sensor: SensorConfiguration,
    plot_config: PlotConfiguration | None = None,
) -> dict[str, Any]:
    device_id = sensor.device_id or str(sensor.id)

    if plot_config:
        sample_rate = float(plot_config.sampling_rate_hz)
        lor = int(plot_config.fft_lines)
        channel_count = int(plot_config.channel_count)
        fmax = float(plot_config.frequency_max_hz) if plot_config.frequency_max_hz else DEFAULT_FMAX_HZ
    else:
        sample_rate = DEFAULT_SAMPLE_RATE_HZ
        lor = DEFAULT_LOR
        channel_count = DEFAULT_CHANNEL_COUNT
        fmax = DEFAULT_FMAX_HZ

    formula = compute_acquisition_formula(sample_rate, lor)
    formula["fmaxHz"] = fmax

    sensitivity = float(sensor.sensitivity) if sensor.sensitivity is not None else None

    return {
        "acquisitionFormula": formula,
        "minutes": DEFAULT_MINUTES,
        "averaging": DEFAULT_AVERAGING,
        "sensitivityMvPerG": sensitivity,
        "totalChannelCount": channel_count,
        "averageCount": DEFAULT_AVERAGING,
        "lastAveraging": None,
        "lastOverlapping": None,
        "lor": str(lor),
        "fmax": str(int(fmax)),
        "windowType": DEFAULT_WINDOW,
        "sensorId": device_id,
        "channels": build_channels(sensor, channel_count),
        "success": True,
        "overlapping": DEFAULT_OVERLAP,
        "ksps": str(int(sample_rate / 1000)),
        "id": 1,
        "overlapPercentage": DEFAULT_OVERLAP,
        "platformSensorId": str(sensor.id),
    }
