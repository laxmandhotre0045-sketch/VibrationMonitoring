"""
Build 3D FFT waterfall data: N captures of one sensor channel, stacked oldest -> newest.

Reuses the already-computed spectra in `plot_results` (same config fingerprint the 2D
charts use). Nothing here recomputes the FFT - a capture without a stored spectrum is
filled in through the existing plot pipeline so both views stay identical.
"""
from __future__ import annotations

import random
from typing import Any, Sequence

import numpy as np
from scipy.signal import find_peaks
from sqlalchemy.orm import Session

from app.crud import measurement as measurement_crud
from app.models.measurement import SensorDataUpload
from app.schemas.measurement import PlotSeriesOut
from app.services.signal_processing import DATA_TYPE_UNITS
from app.services.plot_storage import (
    compute_config_fingerprint,
    get_or_load_single_plot,
    plot_result_to_series,
)

#: Window applied by signal_processing.compute_fft_spectrum (build_window, §9.1).
FFT_WINDOW = "Hanning"

#: A local maximum counts as a peak when it stands this far above its surroundings,
#: as a fraction of the strongest line in that spectrum.
PEAK_PROMINENCE_RATIO = 0.08

DEFAULT_MAX_PEAKS = 8
DEFAULT_MAX_POINTS = 512

#: Newest N captures loaded as the selection pool. Beyond this, "oldest" and "random"
#: draw from the most recent WATERFALL_POOL_LIMIT captures rather than all history.
WATERFALL_POOL_LIMIT = 1000



def amplitude_axis_label(data_type: str) -> str:
    """`|A| peak (g)` for acceleration, matching whatever unit the config actually uses."""
    unit = DATA_TYPE_UNITS.get(data_type)
    return f"|A| peak ({unit})" if unit else "|A| peak"


def select_uploads(
    uploads_newest_first: Sequence[SensorDataUpload],
    mode: str,
    count: int,
    seed: int | None = None,
) -> tuple[list[SensorDataUpload], int]:
    """
    Pick `count` captures and return them in stacking order (oldest -> newest).

    `uploads_newest_first` is what list_uploads_by_sensor returns. Only parsed captures
    can produce a spectrum, so unparsed ones never enter the selection.
    """
    parsed = [u for u in uploads_newest_first if u.parse_status == "parsed"]
    oldest_first = list(reversed(parsed))
    total = len(oldest_first)
    if total == 0:
        return [], 0

    n = max(1, min(count, total))

    if mode == "oldest":
        chosen = oldest_first[:n]
    elif mode == "random":
        picked = random.Random(seed).sample(range(total), n)
        chosen = [oldest_first[i] for i in sorted(picked)]
    else:  # "last" - newest N, still stacked oldest -> newest
        chosen = oldest_first[total - n:]

    return chosen, total


def _finite_pairs(x: Sequence[float], y: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    """Drop any bin where frequency or amplitude is NaN/Inf before it can reach the chart."""
    size = min(len(x), len(y))
    if size == 0:
        return np.empty(0), np.empty(0)
    fx = np.asarray(x[:size], dtype=np.float64)
    fy = np.asarray(y[:size], dtype=np.float64)
    mask = np.isfinite(fx) & np.isfinite(fy)
    return fx[mask], fy[mask]


def detect_spectrum_peaks(
    freqs: np.ndarray,
    mags: np.ndarray,
    max_peaks: int = DEFAULT_MAX_PEAKS,
) -> list[dict[str, float]]:
    """Prominent local maxima of one spectrum, strongest first then re-sorted by frequency."""
    if mags.size < 3:
        return []
    strongest = float(np.max(mags))
    if strongest <= 0.0:
        return []

    indices, _ = find_peaks(mags, prominence=strongest * PEAK_PROMINENCE_RATIO)
    if indices.size == 0:
        return []

    ranked = indices[np.argsort(mags[indices])[::-1][:max_peaks]]
    return [
        {"frequency": float(freqs[i]), "amplitude": float(mags[i])}
        for i in np.sort(ranked)
    ]


def decimate_spectrum(
    freqs: np.ndarray,
    mags: np.ndarray,
    max_points: int,
) -> tuple[list[float], list[float]]:
    """
    Reduce a spectrum to at most `max_points` bins by keeping the largest magnitude in
    each bucket. Peak heights and their frequencies survive; every-Nth sampling would
    lose them.
    """
    n = mags.size
    if max_points <= 0 or n <= max_points:
        return freqs.tolist(), mags.tolist()

    edges = np.linspace(0, n, max_points + 1).astype(int)
    out_f: list[float] = []
    out_a: list[float] = []
    for start, end in zip(edges[:-1], edges[1:]):
        if end <= start:
            continue
        j = start + int(np.argmax(mags[start:end]))
        out_f.append(float(freqs[j]))
        out_a.append(float(mags[j]))
    return out_f, out_a


def _spectrum_for_upload(
    db: Session,
    upload: SensorDataUpload,
    config: dict[str, Any],
    fingerprint: str,
    plot_type: str,
    channel: int,
) -> PlotSeriesOut | None:
    """Stored spectrum if present, otherwise compute-and-store it the normal way."""
    rows = measurement_crud.get_plot_results(
        db,
        upload_id=upload.id,
        config_fingerprint=fingerprint,
        channel=channel,
        plot_type=plot_type,
    )
    if rows:
        return plot_result_to_series(rows[0])

    cfg = {**config, "active_channel": channel}
    return get_or_load_single_plot(db, upload, cfg, plot_type, channel=channel)


class _AxisRanges:
    """Running min/max across every capture, for axis bounds the frontend can trust."""

    def __init__(self) -> None:
        self.freq_min: float | None = None
        self.freq_max: float | None = None
        self.amp_min: float | None = None
        self.amp_max: float | None = None
        self.resolution: float | None = None

    def absorb(self, freqs: np.ndarray, mags: np.ndarray) -> None:
        if self.resolution is None and freqs.size > 1:
            self.resolution = float(freqs[1] - freqs[0])
        lo, hi = float(freqs[0]), float(freqs[-1])
        self.freq_min = lo if self.freq_min is None else min(self.freq_min, lo)
        self.freq_max = hi if self.freq_max is None else max(self.freq_max, hi)
        a_lo, a_hi = float(np.min(mags)), float(np.max(mags))
        self.amp_min = a_lo if self.amp_min is None else min(self.amp_min, a_lo)
        self.amp_max = a_hi if self.amp_max is None else max(self.amp_max, a_hi)


def _build_capture(
    db: Session,
    upload: SensorDataUpload,
    config: dict[str, Any],
    fingerprint: str,
    plot_type: str,
    channel: int,
    max_points: int,
    max_peaks: int,
    ranges: _AxisRanges,
    capture_number: int,
) -> dict[str, Any] | None:
    """One waterfall row, or None when this capture has no usable spectrum."""
    try:
        series = _spectrum_for_upload(db, upload, config, fingerprint, plot_type, channel)
    except Exception:
        return None
    if series is None:
        return None

    freqs, mags = _finite_pairs(series.x, series.y)
    if freqs.size < 2:
        return None

    peaks = detect_spectrum_peaks(freqs, mags, max_peaks)
    thin_f, thin_a = decimate_spectrum(freqs, mags, max_points)
    if len(thin_f) < 2:
        return None

    ranges.absorb(freqs, mags)
    return {
        "capture_number": capture_number,
        "upload_id": upload.id,
        "original_filename": upload.original_filename,
        "captured_at": upload.created_at,
        "channel": series.channel,
        "point_count": len(thin_f),
        "frequencies": thin_f,
        "amplitudes": thin_a,
        "peaks": peaks,
    }


def build_waterfall(
    db: Session,
    *,
    sensor,
    uploads_newest_first: Sequence[SensorDataUpload],
    config: dict[str, Any],
    channel: int,
    mode: str,
    count: int,
    plot_type: str = "fft_spectrum",
    max_points: int = DEFAULT_MAX_POINTS,
    max_peaks: int = DEFAULT_MAX_PEAKS,
    seed: int | None = None,
    total_available: int | None = None,
) -> dict[str, Any]:
    selected, pool_size = select_uploads(uploads_newest_first, mode, count, seed)
    total = total_available if total_available is not None else pool_size
    fingerprint = compute_config_fingerprint(config)
    data_type = config.get("data_type", "acceleration")

    captures: list[dict[str, Any]] = []
    ranges = _AxisRanges()
    skipped = 0

    for upload in selected:
        row = _build_capture(
            db,
            upload,
            config,
            fingerprint,
            plot_type,
            channel,
            max_points,
            max_peaks,
            ranges,
            len(captures) + 1,
        )
        if row is None:
            skipped += 1
            continue
        captures.append(row)

    return {
        "sensor_id": sensor.id,
        "channel": channel,
        "plot_type": plot_type,
        "selection_mode": mode,
        "requested_count": count,
        "returned_count": len(captures),
        "total_available": total,
        "skipped_count": skipped,
        "sampling_rate_hz": float(config["sampling_rate_hz"]),
        "fft_lines": config.get("fft_lines"),
        "window": FFT_WINDOW,
        "data_type": data_type,
        "frequency_min_hz": ranges.freq_min,
        "frequency_max_hz": ranges.freq_max,
        "frequency_resolution_hz": ranges.resolution,
        "amplitude_min": ranges.amp_min,
        "amplitude_max": ranges.amp_max,
        "x_label": "Frequency (Hz)",
        # Appendix A trap 3 — the row axis is capture *time*, not a uniform
        # index. The label names both so a chart that plots row order cannot
        # imply the captures are evenly spaced.
        "y_label": "Capture time (non-uniform)",
        "z_label": amplitude_axis_label(data_type),
        "waterfall_kind": "stacked_spectra",
        "x_unit": "Hz",
        "y_values": [c["captured_at"] for c in captures],
        "y_unit": "datetime",
        "y_uniform": False,
        "z_unit": DATA_TYPE_UNITS.get(data_type, "g"),
        "sensor_label": sensor.sensor_type,
        "orientation": sensor.orientation,
        "mounting_location": sensor.mounting_location,
        "captures": captures,
    }
