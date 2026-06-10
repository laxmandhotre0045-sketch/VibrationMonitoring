"""
Vibration signal processing — time waveform, circular waveform, FFT, envelope, trend.
"""
from typing import Any
import numpy as np
from scipy.fft import fft, fftfreq
from scipy.signal import hilbert


def _to_array(samples: list[float]) -> np.ndarray:
    return np.asarray(samples, dtype=np.float64)


def resolve_time_seconds(timestamps: list[float], sampling_rate_hz: float) -> np.ndarray:
    """
    Convert timestamp column to relative time in seconds for plotting.

    Sensor exports often use Unix epoch (e.g. 1777747212) as a batch ID, not per-sample
    time — in that case we derive time from sample index and sampling rate.
    """
    ts = _to_array(timestamps)
    n = len(ts)
    if n == 0:
        return ts

    index_time = np.arange(n, dtype=np.float64) / sampling_rate_hz

    if n == 1:
        return index_time

    span = float(ts[-1] - ts[0])
    # Constant or duplicate timestamps → use sample index
    if span == 0.0 or np.std(ts) < 1e-12:
        return index_time

    # Unix epoch seconds or milliseconds
    if float(np.max(ts)) > 1e9:
        rel = ts - ts[0]
        if float(np.max(ts)) > 1e12:
            rel = rel / 1000.0
        # If span is tiny vs recording duration, timestamps are not real sample times
        expected_span = (n - 1) / sampling_rate_hz
        if rel[-1] < expected_span * 0.01:
            return index_time
        return rel

    # Small increasing values — treat as seconds, normalize to start at 0
    return ts - ts[0]


def compute_time_waveform(
    timestamps: list[float], samples: list[float], sampling_rate_hz: float = 25600
) -> dict[str, Any]:
    time_s = resolve_time_seconds(timestamps, sampling_rate_hz)
    return {
        "x": time_s.tolist(),
        "y": samples,
        "x_label": "Time (s)",
        "y_label": "Amplitude",
        "title": "Time Waveform",
        "metadata": {"plot_style": "line"},
    }


def compute_circular_time_waveform(
    timestamps: list[float],
    samples: list[float],
    max_points: int = 2048,
) -> dict[str, Any]:
    """
    Map time waveform onto a circular orbit (polar → XY).
    Each sample is placed on a circle: x = A·cos(θ), y = A·sin(θ).
    """
    data = _to_array(samples)
    n = len(data)
    if n < 4:
        raise ValueError("Need at least 4 samples for circular waveform")

    if n > max_points:
        step = max(1, n // max_points)
        data = data[::step]

    theta = np.linspace(0, 2 * np.pi, len(data), endpoint=False)
    orbit_x = (data * np.cos(theta)).tolist()
    orbit_y = (data * np.sin(theta)).tolist()

    return {
        "x": orbit_x,
        "y": orbit_y,
        "x_label": "X",
        "y_label": "Y",
        "title": "Circular Time Waveform",
        "metadata": {"plot_style": "orbit", "samples": len(data)},
    }


def compute_fft_spectrum(
    samples: list[float],
    sampling_rate_hz: float,
    fft_lines: int | None = None,
    frequency_max_hz: float | None = None,
) -> dict[str, Any]:
    data = _to_array(samples)
    n = len(data)
    if n < 4:
        raise ValueError("Need at least 4 samples for FFT")

    target = min(fft_lines or n, n)
    if target < n:
        data = data[:target]
        n = target

    window = np.hanning(n)
    windowed = data * window
    spectrum = np.abs(fft(windowed))[: n // 2] * (2.0 / n)
    freqs = fftfreq(n, d=1.0 / sampling_rate_hz)[: n // 2]

    if frequency_max_hz:
        mask = freqs <= frequency_max_hz
        freqs = freqs[mask]
        spectrum = spectrum[mask]

    return {
        "x": freqs.tolist(),
        "y": spectrum.tolist(),
        "x_label": "Frequency (Hz)",
        "y_label": "Magnitude",
        "title": "FFT Spectrum",
        "metadata": {"plot_style": "line", "fft_lines": n, "sampling_rate_hz": sampling_rate_hz},
    }


def compute_envelope_spectrum(
    samples: list[float],
    sampling_rate_hz: float,
    fft_lines: int | None = None,
    frequency_max_hz: float | None = None,
) -> dict[str, Any]:
    data = _to_array(samples)
    analytic = hilbert(data)
    envelope = np.abs(analytic)
    envelope = envelope - np.mean(envelope)
    result = compute_fft_spectrum(
        envelope.tolist(),
        sampling_rate_hz,
        fft_lines=fft_lines,
        frequency_max_hz=frequency_max_hz,
    )
    result["title"] = "Envelope Spectrum"
    result["y_label"] = "Envelope Magnitude"
    return result


def compute_trend_plot(
    timestamps: list[float],
    samples: list[float],
    sampling_rate_hz: float,
    num_segments: int = 32,
) -> dict[str, Any]:
    """Amplitude trend over time — RMS per time segment."""
    data = _to_array(samples)
    time_s = resolve_time_seconds(timestamps, sampling_rate_hz)
    n = len(data)
    segment_size = max(1, n // num_segments)

    trend_values: list[float] = []
    time_centers: list[float] = []

    for start in range(0, n - segment_size + 1, segment_size):
        segment = data[start : start + segment_size]
        rms = float(np.sqrt(np.mean(segment ** 2)))
        trend_values.append(rms)
        mid = start + segment_size // 2
        time_centers.append(float(time_s[mid]) if mid < len(time_s) else float(mid / sampling_rate_hz))

    if not trend_values:
        trend_values = [float(np.sqrt(np.mean(data ** 2)))]
        time_centers = [float(time_s[len(time_s) // 2]) if len(time_s) else 0.0]

    return {
        "x": time_centers,
        "y": trend_values,
        "x_label": "Time (s)",
        "y_label": "Amplitude (RMS)",
        "title": "Trend Plot",
        "metadata": {"plot_style": "line", "num_segments": num_segments},
    }
