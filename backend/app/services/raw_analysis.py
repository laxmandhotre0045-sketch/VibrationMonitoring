"""Waveform, spectrum and statistics for one stored raw snapshot.

Read-only. Nothing here computes a *second* FFT: `compute_fft_spectrum` from
`signal_processing` is the single spectrum implementation in the platform, and
this module calls it with the sensor's configured LOR/Fmax so the numbers match
what the analysis tabs already show.

Statistics likewise reuse `extract_channel_features` for RMS / peak / crest /
kurtosis. Only peak-to-peak and skewness are computed here, because the stored
feature set does not include them — and they are computed on the fly rather than
added to `extract_channel_features`, which would write extra rows into
`extracted_features` and change what the threshold rules grade.
"""
from typing import Any

import numpy as np

from app.services.feature_extraction import (
    _compute_fft_magnitudes,
    _estimate_shaft_hz,
    extract_channel_features,
)
from app.services.signal_processing import compute_fft_spectrum

#: Plotting a 25 000-point spectrum in a browser is wasted work; the peak search
#: still runs on the full-resolution spectrum before any thinning.
MAX_SPECTRUM_POINTS = 4000

#: A dominant frequency reported as DC is an offset, not a machine order. The
#: bin is excluded from the peak search for the same reason the analysis tabs
#: exclude it.
DC_GUARD_HZ = 1.0


def available_channels(parsed: dict[str, Any]) -> list[int]:
    """0-based channel indexes present in a stored snapshot.

    Stored snapshots keep one array per channel under `channels`, keyed "ch0",
    "ch1", … — the flat `samples` list of rows is only produced by
    `window_samples` for plotting, so it must not be read here.
    """
    stored = parsed.get("channels") or {}
    return sorted(
        int(key[2:]) for key in stored if key.startswith("ch") and key[2:].isdigit()
    )


def channel_samples(parsed: dict[str, Any], channel: int) -> list[float]:
    stored = parsed.get("channels") or {}
    present = available_channels(parsed)
    if not present:
        raise ValueError("Snapshot contains no channel data")
    if channel not in present:
        raise ValueError(
            f"channel {channel} not in snapshot; available 0-based channels: {present}"
        )
    return [float(v) for v in stored[f"ch{channel}"]]


def _thin(x: list[float], y: list[float], limit: int) -> tuple[list[float], list[float]]:
    """Reduce to at most `limit` points, keeping the tallest line in each bucket.

    Appendix A trap 6: every-Nth sampling makes the plotted trace peak *lower*
    than the signal actually does, because the sample that happens to land on
    the peak is usually the one thrown away. Bucketed max keeps both the peak
    height and the frequency it sits at, so the trace agrees with the
    `dominant_amplitude` readout instead of quietly under-reporting it.
    """
    n = len(x)
    if limit <= 0 or n <= limit:
        return x, y
    xa = np.asarray(x, dtype=np.float64)
    ya = np.asarray(y, dtype=np.float64)
    edges = np.linspace(0, n, limit + 1).astype(int)
    out_x: list[float] = []
    out_y: list[float] = []
    for start, end in zip(edges[:-1], edges[1:]):
        if end <= start:
            continue
        j = start + int(np.argmax(ya[start:end]))
        out_x.append(float(xa[j]))
        out_y.append(float(ya[j]))
    return out_x, out_y


def compute_raw_statistics(samples: list[float], sampling_rate_hz: float) -> dict[str, float]:
    """RMS, peak, peak-to-peak, crest factor, kurtosis and skewness.

    RMS / peak / crest / kurtosis come from the shared feature extractor so a
    number shown on the raw page cannot disagree with the same number on the
    health page.

    Kurtosis is returned three ways on purpose (Appendix A trap 1):
    `kurtosis` and `kurtosis_excess` are excess kurtosis (Gaussian = 0), the
    convention the stored feature and the threshold rules use; `kurtosis_raw`
    is Pearson (Gaussian = 3). The platform's kurtosis limits of 3.5 warn / 5.0
    critical are on the excess scale, i.e. 6.5 / 8.0 raw.

    All values are dimensionless or in the channel's engineering unit; none is
    dB or normalised, per the Appendix A axis rules.
    """
    features = extract_channel_features(samples, sampling_rate_hz)

    data = np.asarray(samples, dtype=np.float64)
    peak_to_peak = float(np.max(data) - np.min(data)) if data.size else 0.0
    peak = float(features["peak"]["value"])

    # Fisher-Pearson skewness. scipy.stats is not imported anywhere else in the
    # service layer, so this stays numpy-only for consistency.
    mean = float(np.mean(data)) if data.size else 0.0
    std = float(np.std(data)) if data.size else 0.0
    skewness = float(np.mean((data - mean) ** 3) / std**3) if std > 1e-30 else 0.0

    # Appendix A trap 1 — "kurtosis" means two different things in the reference
    # system: excess (Gaussian → 0) on the trend endpoint, raw Pearson
    # (Gaussian → 3) on the statistics-history endpoint. They differ by exactly
    # 3.0, so a single unqualified field is indistinguishable from the other
    # convention. Both are returned here under names that cannot be confused.
    #
    # `kurtosis` stays EXCESS — it is the stored feature the threshold rules
    # grade, and renaming it would silently shift every displayed value by 3.
    kurtosis_excess = float(features["kurtosis"]["value"])

    # Appendix A trap 5 — the reference exposes zero-to-peak and "true peak" as
    # separate fields holding the same unsigned max|x|. Only the honest one is
    # returned; `peak` IS zero-to-peak, and there is no signed-peak field to
    # mistake it for.
    return {
        "rms": float(features["rms"]["value"]),
        "peak": peak,
        "zero_to_peak": peak,
        "peak_to_peak": peak_to_peak,
        "crest_factor": float(features["crest_factor"]["value"]),
        "kurtosis": kurtosis_excess,
        "kurtosis_excess": kurtosis_excess,
        "kurtosis_raw": kurtosis_excess + 3.0,
        "skewness": skewness,
    }


def compute_raw_spectrum(
    samples: list[float],
    sampling_rate_hz: float,
    fft_lines: int | None,
    frequency_max_hz: float | None,
) -> dict[str, Any]:
    """FFT of one channel plus its dominant frequency.

    Delegates entirely to `compute_fft_spectrum`, so windowing, block sizing,
    averaging and amplitude scaling are identical to every other spectrum in the
    platform.
    """
    spectrum = compute_fft_spectrum(
        samples,
        sampling_rate_hz,
        fft_lines=fft_lines,
        frequency_max_hz=frequency_max_hz,
    )
    freqs = spectrum["x"]
    amps = spectrum["y"]

    dominant_hz = 0.0
    dominant_amplitude = 0.0
    if freqs:
        arr_f = np.asarray(freqs, dtype=np.float64)
        arr_a = np.asarray(amps, dtype=np.float64)
        mask = arr_f > DC_GUARD_HZ
        if mask.any():
            idx = int(np.argmax(arr_a[mask]))
            dominant_hz = float(arr_f[mask][idx])
            dominant_amplitude = float(arr_a[mask][idx])

    thin_f, thin_a = _thin(freqs, amps, MAX_SPECTRUM_POINTS)

    metadata = spectrum.get("metadata", {})
    return {
        "frequencies": thin_f,
        "amplitudes": thin_a,
        "dominant_frequency_hz": dominant_hz,
        "dominant_amplitude": dominant_amplitude,
        "line_count": len(freqs),
        "returned_points": len(thin_f),
        "block_size": int(metadata.get("block_size") or 0),
        "averages": int(metadata.get("averages") or 0),
        "frequency_resolution_hz": (
            sampling_rate_hz / metadata["block_size"]
            if metadata.get("block_size")
            else 0.0
        ),
    }


def estimate_shaft_hz(samples: list[float], sampling_rate_hz: float) -> float | None:
    """Shaft-speed estimate straight from the samples, for captures with no features.

    The raw ingest path deliberately skips the derived-artefact pipeline, so a
    snapshot posted by the collector has no stored features and therefore no
    stored `estimated_shaft_hz`. The orbit and 1x-migration plots both need one.

    Rather than run the whole feature pipeline for a single number, this reuses
    the same two pieces the pipeline itself uses — its FFT and its band-limited
    peak search — so the estimate is identical to the stored one when both exist.

    Still an estimate from the spectrum, not a measured speed: there is no
    keyphasor on this system.
    """
    if sampling_rate_hz <= 0 or len(samples) < 4:
        return None
    try:
        freqs, spectrum = _compute_fft_magnitudes(
            np.asarray(samples, dtype=np.float64), sampling_rate_hz
        )
        value = _estimate_shaft_hz(freqs, spectrum)
    except Exception:
        return None
    return float(value) if value and value > 0 else None
