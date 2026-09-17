"""
Build edge-device acquisition JSON from sensor + plot configuration.
Compatible with UDP acquisition scripts that poll config by device_id (MAC-style).

──────────────────────────────────────────────────────────────────────────────
LOR / FFT SIZING — THE ONE FORMULA USED EVERYWHERE
──────────────────────────────────────────────────────────────────────────────
There are two competing industry conventions for "lines of resolution", and
mixing them silently doubles or halves every reported frequency. This platform
follows the reference Java analyser (§5), where **LOR is the FFT block size**:

  Block-size LOR (THIS CODEBASE, matching the reference analyser)
      N_FFT = max(16, LOR)                    LOR *is* the block, not a count
      lines returned         = N_FFT / 2 + 1  including DC and Nyquist
      frequency resolution   Δf = Fs / N_FFT
      block time             T  = N_FFT / Fs = 1 / Δf

    Worked example, Fs = 50 000 Hz, LOR = 2500:
      N_FFT = 2500 samples,  Δf = 20 Hz,  T = 0.05 s,  1251 lines

  Fmax-based (many portable analysers, and the vendor dashboard we were shown)
      LOR = number of spectral lines spanning DC .. Fmax
      Δf = Fmax / LOR,  T = 1 / Δf = LOR / Fmax,  N = Fs * T

    Same inputs plus Fmax = 9000 Hz:
      Δf = 3.6 Hz,  T = 0.277778 s,  N = 13 889 samples

Both are internally consistent; they answer different questions. `SAMPLES_PER_LINE`
is therefore 1, and `signal_processing.compute_fft_spectrum` slices exactly
`fft_lines` samples per block.

  ⚠ This changed from the earlier `N = 2 × LOR` convention. Every spectrum
    stored before the change was computed on a block twice this size, so its
    frequency axis is at half this Δf. Re-generate stored plots and features
    rather than comparing old and new rows directly.

The Fmax-relative figures are still computed — see `fmax_line_metrics` — and
surfaced read-only in the UI, so an analyst comparing against a portable
analyser can see both numbers instead of assuming one is a bug.
"""
from typing import Any, Iterable

from app.models.measurement import PlotConfiguration
from app.models.sensor import SensorConfiguration
from app.services.signal_processing import (
    MIN_FFT_SIZE,
    SAMPLES_PER_LINE,
    acquisition_sample_budget,
)

DEFAULT_SAMPLE_RATE_HZ = 256_000.0
DEFAULT_LOR = 51_200
DEFAULT_FMAX_HZ = 15_000.0
DEFAULT_CHANNEL_COUNT = 8
DEFAULT_WINDOW = "HANNING"
DEFAULT_MINUTES = "1"
DEFAULT_AVERAGING = 1
DEFAULT_OVERLAP = 0

#: Cadence between captures when a sensor predates migration 017.
DEFAULT_COLLECTION_INTERVAL_MINUTES = 2

#: Casing accelerometers are mounted in one of three directions. A triaxial
#: install repeats V/H/A, which is also the default this module hands out for
#: an unmapped channel count.
AXIS_CYCLE = ("VERTICAL", "HORIZONTAL", "AXIAL")

#: A real IEPE accelerometer is 10–1000 mV/g. Anything far below that is a
#: placeholder rather than hardware data, and the UI flags it instead of
#: quietly scaling every amplitude by it.
MIN_PLAUSIBLE_SENSITIVITY_MV_PER_G = 1.0


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
    # §5 — LOR is the FFT block size, so the device captures one sample per
    # line. §11.1 then adds one step per extra average.
    nfft = max(MIN_FFT_SIZE, lor * SAMPLES_PER_LINE)
    step, required_samples = acquisition_sample_budget(
        nfft, average_count, overlap_decimal * 100.0
    )
    block_time = nfft / sample_rate_hz
    return {
        # §8 — Δf = Fs / N_FFT.
        "frequencyResolutionHz": sample_rate_hz / nfft,
        # §11.1 — one block, not the whole averaged acquisition.
        "blockTimeSeconds": block_time,
        "sampleRateHz": sample_rate_hz,
        "requiredSamples": float(required_samples),
        "overlapDecimal": overlap_decimal,
        # §11.1 — every sample the plan needs, independent of Fs.
        "totalAcquisitionTimeSeconds": required_samples / sample_rate_hz,
        "averageCount": float(average_count),
        "fmaxHz": DEFAULT_FMAX_HZ,
        "lor": float(lor),
        "stepSizeSamples": float(step),
    }


def fmax_line_metrics(
    sample_rate_hz: float,
    lor: int,
    fmax_hz: float | None,
) -> dict[str, float | None]:
    """Analyser-style (Fmax-based) view of the same settings.

    Read-only. Provided so a portable analyser reporting Δf = Fmax/LOR can be
    reconciled with the Nyquist-based numbers this platform computes with,
    rather than looking like a defect. Not used for any FFT.
    """
    if sample_rate_hz <= 0 or lor <= 0:
        return {
            "linesBelowFmax": None,
            "fmaxRelativeResolutionHz": None,
            "fmaxRelativeBlockTimeSeconds": None,
        }

    resolution = sample_rate_hz / (lor * SAMPLES_PER_LINE)
    effective_fmax = float(fmax_hz) if fmax_hz else sample_rate_hz / 2.0

    return {
        # How many of this platform's lines actually fall in the band of
        # interest. DC counts as a line, hence the +1.
        "linesBelowFmax": float(int(effective_fmax / resolution) + 1),
        "fmaxRelativeResolutionHz": effective_fmax / lor,
        "fmaxRelativeBlockTimeSeconds": lor / effective_fmax if effective_fmax > 0 else None,
    }


def default_channel_map(channel_count: int) -> list[dict[str, Any]]:
    """V/H/A repeating — CH1 Vertical, CH2 Horizontal, CH3 Axial, CH4 Vertical…

    Used only when a sensor has no saved mapping. It is a starting point for the
    operator to correct, not an assertion about how the machine is wired.
    """
    return [
        {
            "channel_index": i + 1,
            "machine_axis": AXIS_CYCLE[i % len(AXIS_CYCLE)],
            "signal_type": "VIBRATION",
            "label": None,
        }
        for i in range(max(0, channel_count))
    ]


def resolve_channel_map(
    stored: Iterable[dict[str, Any]] | None,
    channel_count: int,
) -> list[dict[str, Any]]:
    """Normalise a saved mapping to exactly `channel_count` ordered entries.

    Channel count and channel mapping are edited independently, so a saved map
    can be short (count was raised) or long (count was lowered). Missing
    channels fall back to the V/H/A default; extra ones are dropped from the
    response but left untouched in the database, so lowering then raising the
    count again does not lose the operator's labels.
    """
    by_index: dict[int, dict[str, Any]] = {}
    for entry in stored or []:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("channel_index"))
        except (TypeError, ValueError):
            continue
        if index < 1:
            continue
        axis = str(entry.get("machine_axis") or "").upper()
        by_index[index] = {
            "channel_index": index,
            "machine_axis": axis if axis in AXIS_CYCLE else AXIS_CYCLE[(index - 1) % len(AXIS_CYCLE)],
            "signal_type": str(entry.get("signal_type") or "VIBRATION").upper(),
            "label": entry.get("label") or None,
        }

    resolved: list[dict[str, Any]] = []
    for fallback in default_channel_map(channel_count):
        resolved.append(by_index.get(fallback["channel_index"], fallback))
    return resolved


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


def build_mapped_channels(
    sensor: SensorConfiguration,
    plot_config: PlotConfiguration | None,
    channel_count: int,
    *,
    fallback_to_orientation: bool = True,
) -> list[dict[str, Any]]:
    """Edge channel list that honours the saved per-channel mapping.

    Same shape as `build_channels` so existing consumers keep parsing it, but
    `machineAxis` comes from the operator's mapping instead of being copied from
    the sensor's single mounting orientation across all channels.

    `fallback_to_orientation` decides what an *unmapped* sensor reports. The
    legacy `/measurements/acquisition` route keeps it True so devices already in
    the field see no change in behaviour. The acquisition-config endpoint sets it
    False so `channels` and `channelMap` in the same response always agree —
    otherwise the settings page would show V/H/A while the device received the
    sensor's single mounting orientation on every channel.
    """
    transducer = (
        "MEMS" if "MEMS" in (sensor.sensor_type or "").upper() else sensor.sensor_type or "MEMS"
    )
    stored = getattr(plot_config, "channel_map", None) if plot_config else None
    mapping = resolve_channel_map(stored, channel_count)

    if not stored and fallback_to_orientation:
        fallback_axis = _axis_from_orientation(sensor.orientation)
        for entry in mapping:
            entry["machine_axis"] = fallback_axis

    return [
        {
            "transducerType": transducer,
            "signalType": entry["signal_type"],
            "channelIndex": entry["channel_index"],
            "machineAxis": entry["machine_axis"],
            "label": entry["label"],
        }
        for entry in mapping
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
        # Stored per sensor since migration 016; the constants are the fallback for
        # sensors configured before that.
        window = getattr(plot_config, "window_type", None) or DEFAULT_WINDOW
        averaging = int(getattr(plot_config, "averaging", None) or DEFAULT_AVERAGING)
        overlap = int(getattr(plot_config, "overlap_percent", None) or DEFAULT_OVERLAP)
        interval = int(
            getattr(plot_config, "collection_interval_minutes", None)
            or DEFAULT_COLLECTION_INTERVAL_MINUTES
        )
    else:
        sample_rate = DEFAULT_SAMPLE_RATE_HZ
        lor = DEFAULT_LOR
        channel_count = DEFAULT_CHANNEL_COUNT
        fmax = DEFAULT_FMAX_HZ
        window = DEFAULT_WINDOW
        averaging = DEFAULT_AVERAGING
        overlap = DEFAULT_OVERLAP
        interval = DEFAULT_COLLECTION_INTERVAL_MINUTES

    formula = compute_acquisition_formula(
        sample_rate, lor, overlap_decimal=overlap / 100.0, average_count=averaging
    )
    formula["fmaxHz"] = fmax

    sensitivity = float(sensor.sensitivity) if sensor.sensitivity is not None else None

    return {
        "acquisitionFormula": formula,
        # `minutes` is the legacy field name the UDP scripts already read; it now
        # carries the configured collection interval instead of a constant.
        "minutes": str(interval),
        "averaging": averaging,
        "sensitivityMvPerG": sensitivity,
        "totalChannelCount": channel_count,
        "averageCount": averaging,
        "lastAveraging": None,
        "lastOverlapping": None,
        "lor": str(lor),
        "fmax": str(int(fmax)),
        "windowType": window,
        "sensorId": device_id,
        # Honours the saved channel mapping. Identical to build_channels() until
        # an operator saves one, so existing devices see no change.
        "channels": build_mapped_channels(sensor, plot_config, channel_count),
        "success": True,
        "overlapping": overlap,
        "ksps": str(int(sample_rate / 1000)),
        "id": 1,
        "overlapPercentage": overlap,
        "platformSensorId": str(sensor.id),
    }


def build_acquisition_config(
    sensor: SensorConfiguration,
    plot_config: PlotConfiguration | None,
) -> dict[str, Any]:
    """Full acquisition configuration for the Python collector and the UI.

    One source of truth: the collector reads sample rate, block size, channel
    mapping and cadence from here instead of carrying its own copies that can
    drift out of step with the dashboard.

    No MQTT settings are included by design — the broker connection and the
    topic subscription belong to the collector script, not to the dashboard.
    """
    if plot_config:
        sample_rate = float(plot_config.sampling_rate_hz)
        lor = int(plot_config.fft_lines)
        channel_count = int(plot_config.channel_count)
        fmax = (
            float(plot_config.frequency_max_hz)
            if plot_config.frequency_max_hz
            else sample_rate / 2.0
        )
        window = getattr(plot_config, "window_type", None) or DEFAULT_WINDOW
        averaging = int(getattr(plot_config, "averaging", None) or DEFAULT_AVERAGING)
        overlap = int(getattr(plot_config, "overlap_percent", None) or DEFAULT_OVERLAP)
        interval = int(
            getattr(plot_config, "collection_interval_minutes", None)
            or DEFAULT_COLLECTION_INTERVAL_MINUTES
        )
        stored_map = getattr(plot_config, "channel_map", None)
    else:
        sample_rate = DEFAULT_SAMPLE_RATE_HZ
        lor = DEFAULT_LOR
        channel_count = DEFAULT_CHANNEL_COUNT
        fmax = DEFAULT_FMAX_HZ
        window = DEFAULT_WINDOW
        averaging = DEFAULT_AVERAGING
        overlap = DEFAULT_OVERLAP
        interval = DEFAULT_COLLECTION_INTERVAL_MINUTES
        stored_map = None

    formula = compute_acquisition_formula(
        sample_rate, lor, overlap_decimal=overlap / 100.0, average_count=averaging
    )
    formula["fmaxHz"] = fmax
    formula.update(fmax_line_metrics(sample_rate, lor, fmax))

    sensitivity = float(sensor.sensitivity) if sensor.sensitivity is not None else None
    unit = sensor.sensitivity_unit or "mV/g"
    sensitivity_suspect = (
        sensitivity is not None
        and unit.replace(" ", "").upper() == "MV/G"
        and sensitivity < MIN_PLAUSIBLE_SENSITIVITY_MV_PER_G
    )

    return {
        # ── Editable acquisition settings ──────────────────────────────────
        "sampleRateHz": sample_rate,
        "ksps": sample_rate / 1000.0,
        "fmaxHz": fmax,
        "lor": lor,
        "windowType": window,
        "averageCount": averaging,
        "overlapPercentage": overlap,
        "sensitivityMvPerG": sensitivity,
        "sensitivityUnit": unit,
        "sensitivitySuspect": sensitivity_suspect,
        "totalChannelCount": channel_count,
        "collectionIntervalMinutes": interval,
        # ── Derived, read-only ─────────────────────────────────────────────
        # Flat copies so the collector can read them directly; identical to the
        # matching keys inside "calculated".
        "frequencyResolutionHz": formula["frequencyResolutionHz"],
        "blockTimeSeconds": formula["blockTimeSeconds"],
        "samplesPerBlock": int(formula["requiredSamples"]),
        "totalAcquisitionTimeSeconds": formula["totalAcquisitionTimeSeconds"],
        "calculated": {
            "frequencyResolutionHz": formula["frequencyResolutionHz"],
            "blockTimeSeconds": formula["blockTimeSeconds"],
            "samplesPerBlock": int(formula["requiredSamples"]),
            "totalAcquisitionTimeSeconds": formula["totalAcquisitionTimeSeconds"],
            "stepSizeSamples": int(formula["stepSizeSamples"]),
            "nyquistHz": sample_rate / 2.0,
            "samplesPerLine": SAMPLES_PER_LINE,
            "linesBelowFmax": formula["linesBelowFmax"],
            "fmaxRelativeResolutionHz": formula["fmaxRelativeResolutionHz"],
            "fmaxRelativeBlockTimeSeconds": formula["fmaxRelativeBlockTimeSeconds"],
        },
        # ── Identity & wiring ──────────────────────────────────────────────
        "sensorId": sensor.device_id or str(sensor.id),
        "platformSensorId": str(sensor.id),
        "deviceId": sensor.device_id,
        "channels": build_mapped_channels(
            sensor, plot_config, channel_count, fallback_to_orientation=False
        ),
        "channelMap": resolve_channel_map(stored_map, channel_count),
        "success": True,
    }
