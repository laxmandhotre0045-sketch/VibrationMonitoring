"""
Extract scalar vibration features from channel time series (scaled eng. units from CSV).
"""
from __future__ import annotations

from typing import Any

import numpy as np

from app.ai.envelope_features import (
    ENVELOPE_FEATURE_CODES,
    extract_envelope_features,
)
from app.ai.shaft_speed import ShaftSpeed, resolve_shaft_speed
from app.ai.frequency_features import (
    FREQUENCY_FEATURE_CODES,
    extract_frequency_features,
)
from app.ai.time_features import (
    TIME_FEATURE_CODES,
    extract_time_features,
)

from app.services.signal_processing import (
    build_window,
    coherent_gain,
    frequency_axis_hz,
    magnitude_spectrum_half,
    rectified_envelope,
    remove_mean,
)

SHAFT_FREQ_MIN_HZ = 5.0
SHAFT_FREQ_MAX_HZ = 120.0
FFT_BAND_MAX_HZ = 500.0
SEGMENT_COUNT = 32

#: The ten the platform started with, then the thirteen time-domain features
#: from VIK-018. APPENDED, never reordered: the frontend treats this as a
#: positional contract, so inserting a code in the middle silently relabels
#: every feature after it.
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
] + TIME_FEATURE_CODES + FREQUENCY_FEATURE_CODES + ENVELOPE_FEATURE_CODES


def _to_array(samples: list[float]) -> np.ndarray:
    return np.asarray(samples, dtype=np.float64)


def _compute_fft_magnitudes(samples: np.ndarray, sampling_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Single-sided 0-peak spectrum of the whole channel, per §10.

    One Hann-windowed block over the full record: the mean is removed first
    (§10.1), amplitude is corrected by the window's coherent gain, and DC and
    Nyquist are not doubled (§10.2). Shares its primitives with
    `compute_fft_spectrum`, so a feature and a plotted spectrum cannot disagree.
    """
    n = len(samples)
    if n < 4:
        raise ValueError("Need at least 4 samples for FFT")
    window = build_window(n, "HANNING")
    cg = coherent_gain(window)
    spectrum = magnitude_spectrum_half(remove_mean(samples) * window, n, cg)
    freqs = frequency_axis_hz(spectrum.size, sampling_rate_hz, n)
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
    machine: "ShaftSpeed | None" = None,
    bearing_orders: dict | None = None,
    with_envelope: bool = True,
) -> dict[str, dict[str, Any]]:
    """Every feature for one channel.

    `machine` carries the shaft speed and how it was established. Passing it
    is what makes every "order" in the result mean anything: without it the
    speed falls back to the tallest line between 5 and 120 Hz, which on the
    test pump reads 2x or 4x the true speed on all eight channels. The
    fallback is kept so a caller with no machine record still gets numbers,
    but it is marked unusable and the features say so.
    """
    data = _to_array(samples)
    n = len(data)
    if n < 4:
        raise ValueError("Need at least 4 samples per channel")

    # RMS, peak and crest are measured about the channel's own resting
    # position, not about zero.
    #
    # This was the largest single source of false alarms in the platform.
    # A transducer's standing bias is not vibration, and including it made
    # five of the pump's eight channels read critical against the 0.02 limit
    # while their actual movement was 0.0025 to 0.005 -- comfortably normal.
    # On the worst channel the stored RMS was 0.145 against a true 0.012,
    # because the bias alone is -0.144. Across everything stored, 1,163 of
    # 1,479 critical rows came from these three features, and they were
    # measuring the sensor rather than the machine.
    #
    # The platform already knew the difference: raw_vibration_channels has
    # carried `rms` and `ac_rms` in separate columns since migration 021.
    # Only this path did not use it.
    #
    # Crest factor was doubly affected, with the bias in both the numerator
    # and the denominator, so a badly biased channel drifted towards 1.0 --
    # the value that means a pure sine -- no matter what it was doing.
    #
    # Thresholds are unchanged. They were written for vibration amplitude,
    # which is what they now actually receive.
    centred = data - float(np.mean(data))
    rms = float(np.sqrt(np.mean(centred ** 2)))
    peak = float(np.max(np.abs(centred)))
    crest = float(peak / rms) if rms > 1e-30 else 0.0
    kurt = _excess_kurtosis(data)

    freqs, spectrum = _compute_fft_magnitudes(data, sampling_rate_hz)
    band_mask = freqs <= FFT_BAND_MAX_HZ
    band_energy = float(np.sum(spectrum[band_mask] ** 2))

    if machine is None:
        machine = resolve_shaft_speed(freqs, spectrum)
    shaft_hz = machine.hz if machine.hz else _estimate_shaft_hz(freqs, spectrum)
    amp_1x = _magnitude_at_freq(freqs, spectrum, shaft_hz)
    amp_2x = _magnitude_at_freq(freqs, spectrum, 2.0 * shaft_hz)
    amp_3x = _magnitude_at_freq(freqs, spectrum, 3.0 * shaft_hz)

    # §17.3 — gE envelope: rectify, then a single 1-pole low-pass at 500 Hz.
    # Full-band and Hilbert-free; the Hilbert path (§17.1) belongs to the
    # envelope *spectrum*, not to this scalar.
    envelope = rectified_envelope(data, sampling_rate_hz)
    env_rms = float(np.sqrt(np.mean(envelope ** 2)))

    mean_mag = float(np.mean(spectrum))
    noise_db = float(20.0 * np.log10(max(mean_mag, 1e-30)))

    # Where the shaft speed came from travels with every order-based number.
    # An order is a frequency divided by this, so a wrong one is wrong by the
    # same factor everywhere -- and the only way to trace that back is to
    # record which record answered.
    shaft_meta = {
        "estimated_shaft_hz": shaft_hz,
        "shaft_hz_source": machine.source,
        "shaft_hz_confidence": machine.confidence,
        "shaft_hz_usable": machine.usable,
        "sampling_rate_hz": sampling_rate_hz,
        "sample_count": n,
    }

    result = {
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

    # VIK-018. The shaft estimate is already computed above, so the modulation
    # index gets a real shaft rate rather than falling back to envelope
    # variability -- which is a different quantity under the same name.
    # None rather than a number when the speed is not trustworthy: these
    # features already report 'shaft speed unknown' in that case, which is
    # true, where an order against a 4x-wrong speed is plausible and false.
    for_orders = shaft_hz if machine.usable else None
    result.update(extract_time_features(data, sampling_rate_hz, shaft_hz=for_orders))

    # VIK-019. Handed the spectrum computed above rather than the samples, so
    # this cannot start a second FFT -- the ticket's "one spectrum per segment
    # and fan out", enforced by the signature.
    result.update(extract_frequency_features(freqs, spectrum, shaft_hz=for_orders))

    # VIK-020. Whole record only, and that is a physical limit rather than a
    # saving: a segment is a thirty-second of the capture -- 434 samples on a
    # real one -- and an envelope spectrum of 434 samples has 98 Hz lines,
    # coarser than the gap between any two bearing frequencies on this
    # machine. The transform also costs 30 ms, so running it on all 32
    # segments would turn a 0.2 s capture into 8 s for numbers that could not
    # be read anyway.
    if with_envelope:
        result.update(extract_envelope_features(
            data, sampling_rate_hz,
            freqs=freqs, amplitudes=spectrum,
            shaft_hz=for_orders, bearing_orders=bearing_orders,
        ))
    return result


def extract_segment_trends(
    samples: list[float],
    sampling_rate_hz: float,
    machine: "ShaftSpeed | None" = None,
    *,
    bearing_orders: dict | None = None,
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

    # One extraction per segment, then fan out across the codes (VIK-014).
    #
    # This loop used to run the other way round -- codes outside, segments
    # inside -- so extract_channel_features was called once per code per
    # segment even though a single call already returns every code. With 10
    # codes and 32 segments that is 320 extractions where 32 suffice.
    #
    # The full-length extraction was inside the code loop too, so it ran ten
    # times as well, and each of those is over the whole record rather than a
    # thirty-second of it. Measured: 330 calls per channel, 2,640 for an
    # 8-channel capture. Now 33 and 264.
    per_segment = [
        extract_channel_features(segment.tolist(), sampling_rate_hz, machine,
                                 bearing_orders, with_envelope=False)
        for segment in segments
    ]
    whole_record = extract_channel_features(samples, sampling_rate_hz, machine,
                                            bearing_orders, with_envelope=False)

    result: dict[str, dict[str, Any]] = {}
    for code in FEATURE_CODES:
        # The envelope features have no per-segment series and are absent
        # here rather than carried with an empty one. A segment is a
        # thirty-second of the capture -- 434 samples on a real one -- and an
        # envelope spectrum of that has 98 Hz lines, coarser than the gap
        # between any two bearing frequencies on this machine. A trend of
        # numbers that cannot be read is not a trend.
        scalar = whole_record.get(code)
        if scalar is None:
            continue
        result[code] = {
            "trend_x": trend_x,
            "trend_y": [float(feats[code]["value"]) for feats in per_segment],
            "value": scalar["value"],
            "unit": scalar["unit"],
            "metadata": scalar.get("metadata") or {},
        }
    return result


def extract_all_channels(
    parsed_data: dict[str, Any],
    channel_count: int,
    sampling_rate_hz: float,
    machine: "ShaftSpeed | None" = None,
    bearing_orders: dict | None = None,
) -> dict[int, dict[str, dict[str, Any]]]:
    channels = parsed_data.get("channels", {})
    effective = parsed_data.get("channel_count", channel_count)
    result: dict[int, dict[str, dict[str, Any]]] = {}

    for ch in range(effective):
        key = f"ch{ch}"
        samples = channels.get(key, [])
        if not samples or len(samples) < 4:
            continue
        result[ch] = extract_channel_features(samples, sampling_rate_hz, machine,
                                              bearing_orders)

    return result


def extract_all_channel_trends(
    parsed_data: dict[str, Any],
    channel_count: int,
    sampling_rate_hz: float,
    machine: "ShaftSpeed | None" = None,
    bearing_orders: dict | None = None,
) -> dict[int, dict[str, dict[str, Any]]]:
    channels = parsed_data.get("channels", {})
    effective = parsed_data.get("channel_count", channel_count)
    result: dict[int, dict[str, dict[str, Any]]] = {}

    for ch in range(effective):
        key = f"ch{ch}"
        samples = channels.get(key, [])
        if not samples or len(samples) < 4:
            continue
        result[ch] = extract_segment_trends(samples, sampling_rate_hz, machine=machine,
                                            bearing_orders=bearing_orders)

    return result
