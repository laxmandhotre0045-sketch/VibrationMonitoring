"""
Extract scalar vibration features from channel time series (scaled eng. units from CSV).
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.fft import fft, fftfreq
from scipy.signal import hilbert

SHAFT_FREQ_MIN_HZ = 5.0
SHAFT_FREQ_MAX_HZ = 120.0
FFT_BAND_MAX_HZ = 500.0
SEGMENT_COUNT = 32

FEATURE_CODES = [
    "rms",
    "peak",
    "crest_factor",
    "kurtosis",
    "fft_band_energy_0_500",
    "amplitude_1x",
    "amplitude_2x",
    "amplitude_3x",
    "envelope_rms",
    "noise_floor",
]


def _to_array(samples: list[float]) -> np.ndarray:
    return np.asarray(samples, dtype=np.float64)


def _compute_fft_magnitudes(samples: np.ndarray, sampling_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(samples)
    if n < 4:
        raise ValueError("Need at least 4 samples for FFT")
    window = np.hanning(n)
    # Normalise by the window's coherent gain (sum, not n) so peak amplitudes
    # stay true to the input signal — Hann halves them otherwise.
    spectrum = np.abs(fft(samples * window))[: n // 2] * (2.0 / window.sum())
    freqs = fftfreq(n, d=1.0 / sampling_rate_hz)[: n // 2]
    return freqs, spectrum


def _estimate_shaft_hz(freqs: np.ndarray, spectrum: np.ndarray) -> float:
    mask = (freqs >= SHAFT_FREQ_MIN_HZ) & (freqs <= SHAFT_FREQ_MAX_HZ)
    if not np.any(mask):
        return float(freqs[int(np.argmax(spectrum))])
    band_freqs = freqs[mask]
    band_spec = spectrum[mask]
    return float(band_freqs[int(np.argmax(band_spec))])


def _magnitude_at_freq(freqs: np.ndarray, spectrum: np.ndarray, target_hz: float) -> float:
    if target_hz <= 0:
        return 0.0
    idx = int(np.argmin(np.abs(freqs - target_hz)))
    return float(spectrum[idx])


def _excess_kurtosis(data: np.ndarray) -> float:
    if len(data) < 4:
        return 0.0
    m = np.mean(data)
    v = np.var(data)
    if v < 1e-30:
        return 0.0
    m4 = np.mean((data - m) ** 4)
    return float(m4 / (v ** 2) - 3.0)


def extract_channel_features(
    samples: list[float],
    sampling_rate_hz: float,
) -> dict[str, dict[str, Any]]:
    data = _to_array(samples)
    n = len(data)
    if n < 4:
        raise ValueError("Need at least 4 samples per channel")

    rms = float(np.sqrt(np.mean(data ** 2)))
    peak = float(np.max(np.abs(data)))
    crest = float(peak / rms) if rms > 1e-30 else 0.0
    kurt = _excess_kurtosis(data)

    freqs, spectrum = _compute_fft_magnitudes(data, sampling_rate_hz)
    band_mask = freqs <= FFT_BAND_MAX_HZ
    band_energy = float(np.sum(spectrum[band_mask] ** 2))

    shaft_hz = _estimate_shaft_hz(freqs, spectrum)
    amp_1x = _magnitude_at_freq(freqs, spectrum, shaft_hz)
    amp_2x = _magnitude_at_freq(freqs, spectrum, 2.0 * shaft_hz)
    amp_3x = _magnitude_at_freq(freqs, spectrum, 3.0 * shaft_hz)

    analytic = hilbert(data)
    envelope = np.abs(analytic)
    env_rms = float(np.sqrt(np.mean(envelope ** 2)))

    mean_mag = float(np.mean(spectrum))
    noise_db = float(20.0 * np.log10(max(mean_mag, 1e-30)))

    shaft_meta = {
        "estimated_shaft_hz": shaft_hz,
        "sampling_rate_hz": sampling_rate_hz,
        "sample_count": n,
    }

    return {
        "rms": {"value": rms, "unit": "scaled_eng", "metadata": {}},
        "peak": {"value": peak, "unit": "scaled_eng", "metadata": {}},
        "crest_factor": {"value": crest, "unit": "dimensionless", "metadata": {}},
        "kurtosis": {"value": kurt, "unit": "dimensionless", "metadata": {}},
        "fft_band_energy_0_500": {
            "value": band_energy,
            "unit": "scaled_eng_sq",
            "metadata": {"band_hz": [0.0, FFT_BAND_MAX_HZ]},
        },
        "amplitude_1x": {"value": amp_1x, "unit": "scaled_eng", "metadata": shaft_meta},
        "amplitude_2x": {"value": amp_2x, "unit": "scaled_eng", "metadata": shaft_meta},
        "amplitude_3x": {"value": amp_3x, "unit": "scaled_eng", "metadata": shaft_meta},
        "envelope_rms": {"value": env_rms, "unit": "scaled_eng", "metadata": {}},
        "noise_floor": {"value": noise_db, "unit": "dB", "metadata": {"reference": "mean_fft_magnitude"}},
    }


def extract_segment_trends(
    samples: list[float],
    sampling_rate_hz: float,
    *,
    num_segments: int = SEGMENT_COUNT,
) -> dict[str, dict[str, Any]]:
    """Compute per-segment trend series for each feature code."""
    data = _to_array(samples)
    n = len(data)
    if n < 4:
        raise ValueError("Need at least 4 samples per channel")

    segment_size = max(1, n // num_segments)
    trend_x: list[float] = []
    segments: list[np.ndarray] = []

    for start in range(0, n - segment_size + 1, segment_size):
        segment = data[start : start + segment_size]
        segments.append(segment)
        mid = start + segment_size // 2
        trend_x.append(float(mid / sampling_rate_hz))

    if not segments:
        segments = [data]
        trend_x = [float((n // 2) / sampling_rate_hz)]

    result: dict[str, dict[str, Any]] = {}
    for code in FEATURE_CODES:
        trend_y: list[float] = []
        for segment in segments:
            feats = extract_channel_features(segment.tolist(), sampling_rate_hz)
            trend_y.append(float(feats[code]["value"]))
        scalar = extract_channel_features(samples, sampling_rate_hz)[code]
        result[code] = {
            "trend_x": trend_x,
            "trend_y": trend_y,
            "value": scalar["value"],
            "unit": scalar["unit"],
            "metadata": scalar.get("metadata") or {},
        }
    return result


def extract_all_channels(
    parsed_data: dict[str, Any],
    channel_count: int,
    sampling_rate_hz: float,
) -> dict[int, dict[str, dict[str, Any]]]:
    channels = parsed_data.get("channels", {})
    effective = parsed_data.get("channel_count", channel_count)
    result: dict[int, dict[str, dict[str, Any]]] = {}

    for ch in range(effective):
        key = f"ch{ch}"
        samples = channels.get(key, [])
        if not samples or len(samples) < 4:
            continue
        result[ch] = extract_channel_features(samples, sampling_rate_hz)

    return result


def extract_all_channel_trends(
    parsed_data: dict[str, Any],
    channel_count: int,
    sampling_rate_hz: float,
) -> dict[int, dict[str, dict[str, Any]]]:
    channels = parsed_data.get("channels", {})
    effective = parsed_data.get("channel_count", channel_count)
    result: dict[int, dict[str, dict[str, Any]]] = {}

    for ch in range(effective):
        key = f"ch{ch}"
        samples = channels.get(key, [])
        if not samples or len(samples) < 4:
            continue
        result[ch] = extract_segment_trends(samples, sampling_rate_hz)

    return result
