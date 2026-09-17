"""
Vibration signal processing — time waveform, circular waveform, FFT, envelope, trend.

────────────────────────────────────────────────────────────────────────────────
FORMULA SOURCE
────────────────────────────────────────────────────────────────────────────────
Every formula below follows the reference specification reverse-engineered from
the Java analyser (`sensoVibeDash_backend`, Apache Commons Math3 3.6.1,
`DftNormalization.STANDARD`). Section numbers in the comments refer to that
document, so a reviewer can check any line against it:

  §4   KSPS → Hz parsing
  §5   LOR is the FFT block size (N_FFT = LOR), not a line count
  §8   Δf = Fs / N_FFT ; f_k = k·Fs/N_FFT ; bins = N_FFT/2 + 1
  §9   Window functions and coherent gain CG = mean(w)
  §10  DC removal, single-sided magnitude A[k] = 2|X[k]| / (N_FFT·CG)
  §11  Overlap/averaging budget and linear magnitude averaging
  §17  Band-pass → Hilbert envelope → spectrum

Amplitude convention: linear **0-to-peak**, in the channel's engineering unit.
Not RMS, not PSD, not dB.
"""
from typing import Any
import numpy as np
from scipy.fft import fft, fftfreq
from scipy.signal import hilbert


# §5 — LOR IS THE FFT BLOCK SIZE.
#
# The Java analyser sizes a block as `N_FFT = max(16, LOR)` and returns
# `N_FFT/2 + 1` lines; there is no `N = 2 × LOR` convention anywhere in it.
# This constant is kept so acquisition sizing and the FFT stay in step, but it
# is now 1 rather than 2 — the device captures one sample per line of LOR.
SAMPLES_PER_LINE = 1

#: §5 — smallest block the analyser will build.
MIN_FFT_SIZE = 16

#: §9.3 — window applied when none is configured.
DEFAULT_WINDOW = "HANNING"

#: §17.1 — envelope demodulation band and block sizing.
ENVELOPE_LOW_CUT_HZ = 2000.0
ENVELOPE_HIGH_CUT_HZ = 5000.0
ENVELOPE_SEGMENT_TARGET = 1024
ENVELOPE_SEGMENT_MIN = 256
ENVELOPE_SEGMENT_MAX = 4096

#: §17.3 — cut-off for the rectified (gE) envelope.
ENVELOPE_RECTIFIED_LP_HZ = 500.0


# ─────────────────────────────────────────────────────────────────────────────
# Appendix A — AXIS CONTRACT
#
# Rules that hold for every graph this platform emits:
#   • Every axis is LINEAR. No log, no dB, no normalisation.
#   • Amplitude is linear 0-TO-PEAK in engineering units — never RMS, never PSD.
#   • Frequency axes always include DC and Nyquist (N_FFT/2 + 1 lines).
#   • Time axes are RELATIVE and zero-shifted — never wall-clock.
#
# These are stamped into every plot's metadata rather than left to the caller,
# because a mislabelled axis is indistinguishable from a correct one downstream.
# ─────────────────────────────────────────────────────────────────────────────
AXIS_SCALE_LINEAR = "linear"
AMPLITUDE_CONVENTION = "0-peak"
TIME_REFERENCE_RELATIVE = "relative_zero_shifted"

#: Appendix A — engineering unit per plot-config data_type.
DATA_TYPE_UNITS = {
    "acceleration": "g",
    "velocity": "mm/s",
    "displacement": "um",
}


def amplitude_unit(data_type: str = "acceleration") -> str:
    return DATA_TYPE_UNITS.get(data_type, "g")


def frequency_axis_meta(
    unit: str = "g", *, includes_dc: bool = True, includes_nyquist: bool = True
) -> dict[str, Any]:
    """Appendix A — axis descriptor for any Hz-vs-amplitude graph."""
    return {
        "x_unit": "Hz",
        "x_scale": AXIS_SCALE_LINEAR,
        "y_unit": unit,
        "y_scale": AXIS_SCALE_LINEAR,
        "amplitude_convention": AMPLITUDE_CONVENTION,
        "includes_dc": includes_dc,
        "includes_nyquist": includes_nyquist,
    }


def time_axis_meta(unit: str = "g") -> dict[str, Any]:
    """Appendix A — axis descriptor for any seconds-vs-amplitude graph."""
    return {
        "x_unit": "s",
        "x_scale": AXIS_SCALE_LINEAR,
        "time_reference": TIME_REFERENCE_RELATIVE,
        "y_unit": unit,
        "y_scale": AXIS_SCALE_LINEAR,
        "amplitude_convention": AMPLITUDE_CONVENTION,
    }


def _to_array(samples: list[float]) -> np.ndarray:
    return np.asarray(samples, dtype=np.float64)


# ─────────────────────────────────────────────────────────────────────────────
# §4 — Sample rate
# ─────────────────────────────────────────────────────────────────────────────
def parse_ksps_to_hz(raw: Any) -> float | None:
    """KSPS string → Hz.

    §4: strip every character except digits, sign, decimal point and exponent;
    a value of 1000 or more is already in Hz, anything smaller is kSPS.

        "256" → 256 000 Hz      "256000" → 256 000 Hz      "25" → 25 000 Hz
    """
    if raw is None:
        return None
    cleaned = "".join(c for c in str(raw) if c.isdigit() or c in ".Ee+-")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not np.isfinite(value) or value <= 0:
        return None
    return value if value >= 1000.0 else value * 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# §9 — Windows and coherent gain
# ─────────────────────────────────────────────────────────────────────────────
def parse_window(raw: Any) -> str:
    """§9.3 — window name → canonical type, defaulting to HANNING."""
    if raw is None:
        return DEFAULT_WINDOW
    name = str(raw).strip().upper().replace("-", "_")
    if name in ("RECT", "RECTANGULAR", "BOXCAR"):
        return "RECTANGULAR"
    if name in ("HANNING", "HANN"):
        return "HANNING"
    if name == "HAMMING":
        return "HAMMING"
    if name in ("FLAT_TOP", "FLATTOP"):
        return "FLAT_TOP"
    return DEFAULT_WINDOW


def build_window(n: int, window_type: str = DEFAULT_WINDOW) -> np.ndarray:
    """§9.1 — window coefficients over φ = 2πi/(n−1).

    The flat-top is the normalised 5-term ISO 18431-1 form used by the Java
    `VibrationFftUtil`, not the unnormalised variant in its DAQ path — both
    divide out by their own gain, so amplitude is correct either way.
    """
    if n < 2:
        return np.ones(max(n, 1), dtype=np.float64)

    kind = parse_window(window_type)
    if kind == "RECTANGULAR":
        return np.ones(n, dtype=np.float64)

    phi = 2.0 * np.pi * np.arange(n, dtype=np.float64) / (n - 1)
    if kind == "HAMMING":
        return 0.54 - 0.46 * np.cos(phi)
    if kind == "FLAT_TOP":
        return (
            0.21557895
            - 0.41663158 * np.cos(phi)
            + 0.277263158 * np.cos(2.0 * phi)
            - 0.083578947 * np.cos(3.0 * phi)
            + 0.006947368 * np.cos(4.0 * phi)
        )
    return 0.5 * (1.0 - np.cos(phi))


def coherent_gain(window: np.ndarray) -> float:
    """§9.4 — CG = mean(w). Amplitude (not noise-power) correction only."""
    if window.size == 0:
        return 1.0
    cg = float(np.mean(window))
    return cg if abs(cg) > 1e-15 else 1.0


# ─────────────────────────────────────────────────────────────────────────────
# §5 — Block sizing
# ─────────────────────────────────────────────────────────────────────────────
def next_power_of_two(n: int) -> int:
    """§5 — smallest power of two ≥ max(16, n)."""
    v = max(MIN_FFT_SIZE, int(n))
    return 1 << (v - 1).bit_length()


def resolve_fft_size(
    sample_count: int,
    requested_lines: int,
    min_fft: int = 256,
    max_fft: int = 1 << 20,
) -> int:
    """§5 — block size for the stored-file analysis path."""
    if sample_count < 1:
        return min_fft
    requested = next_power_of_two(max(min_fft, min(requested_lines, max_fft)))
    seg_cap = min(sample_count, requested)
    nfft = next_power_of_two(max(min_fft, seg_cap))
    return min(nfft, requested)


# ─────────────────────────────────────────────────────────────────────────────
# §10 — Spectrum primitives
# ─────────────────────────────────────────────────────────────────────────────
def remove_mean(data: np.ndarray) -> np.ndarray:
    """§10.1 — subtract the arithmetic mean so DC does not leak into line 1."""
    if data.size == 0:
        return data
    return data - float(np.mean(data))


def magnitude_spectrum_half(
    windowed: np.ndarray, nfft: int, cg: float
) -> np.ndarray:
    """§10.2 — single-sided linear 0-peak magnitude, `nfft/2 + 1` lines.

        A[0]        = |X[0]|      / (nfft·CG)        DC — not doubled
        A[k]        = 2·|X[k]|    / (nfft·CG)        1 ≤ k < nfft/2
        A[nfft/2]   = |X[nfft/2]| / (nfft·CG)        Nyquist — not doubled

    A segment shorter than `nfft` is zero-padded, which attenuates the reported
    amplitude by `len/nfft` — the Java behaviour, kept deliberately so numbers
    match. Feed a full-length segment to avoid it.
    """
    if windowed.size > nfft:
        raise ValueError("segment longer than FFT size")

    padded = windowed
    if windowed.size < nfft:
        padded = np.zeros(nfft, dtype=np.float64)
        padded[: windowed.size] = windowed

    spectrum = np.abs(fft(padded))[: nfft // 2 + 1]
    scale = 1.0 / (nfft * (cg if abs(cg) > 1e-15 else 1.0))

    magnitude = spectrum * (2.0 * scale)
    magnitude[0] = spectrum[0] * scale
    magnitude[-1] = spectrum[-1] * scale
    return magnitude


def frequency_axis_hz(bins: int, sampling_rate_hz: float, nfft: int) -> np.ndarray:
    """§8 — f_k = k · Fs / N_FFT."""
    return np.arange(bins, dtype=np.float64) * (sampling_rate_hz / nfft)


# ─────────────────────────────────────────────────────────────────────────────
# §11 — Averaging and overlap
# ─────────────────────────────────────────────────────────────────────────────
def acquisition_sample_budget(
    nfft: int, averages: int, overlap_percent: float
) -> tuple[int, int]:
    """§11.1 — (step size, required samples) for a block/average/overlap plan.

        overlapFrac     = clamp(overlap, 0, 90) / 100
        stepSize        = max(1, round(N_FFT × (1 − overlapFrac)))
        requiredSamples = N_FFT + max(0, averages − 1) × stepSize
    """
    overlap_frac = min(max(float(overlap_percent), 0.0), 90.0) / 100.0
    step = max(1, int(round(nfft * (1.0 - overlap_frac))))
    required = nfft + max(0, int(averages) - 1) * step
    return step, required


def resolve_time_seconds(timestamps: list[float], sampling_rate_hz: float) -> np.ndarray:
    """
    Convert timestamp column to relative time in seconds for plotting.

    §14.1: for DAQ-format captures the time axis is `t_i = i / Fs` and the
    timestamp column is discarded. Sensor exports often use Unix epoch
    (e.g. 1777747212) as a batch ID, not per-sample time — those fall back to
    the index axis for the same reason.
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
        "metadata": {"plot_style": "line", **time_axis_meta()},
    }


def compute_circular_time_waveform(
    timestamps: list[float],
    samples: list[float],
    max_points: int = 2048,
) -> dict[str, Any]:
    """
    Map time waveform onto a circular orbit (polar → XY).
    Each sample is placed on a circle: x = A·cos(θ), y = A·sin(θ).

    No equivalent exists in the Java analyser (§16, NOT FOUND IN SOURCE CODE),
    so this keeps its existing definition.
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
        "metadata": {
            "plot_style": "orbit",
            "samples": len(data),
            # Appendix A: an orbit has no time or frequency axis — X and Y are
            # both amplitude, so the frequency/time descriptors do not apply.
            "x_unit": "g",
            "y_unit": "g",
            "x_scale": AXIS_SCALE_LINEAR,
            "y_scale": AXIS_SCALE_LINEAR,
            "amplitude_convention": AMPLITUDE_CONVENTION,
        },
    }


def compute_fft_spectrum(
    samples: list[float],
    sampling_rate_hz: float,
    fft_lines: int | None = None,
    frequency_max_hz: float | None = None,
    *,
    window: str = DEFAULT_WINDOW,
    averages: int = 1,
    overlap_percent: float = 0.0,
) -> dict[str, Any]:
    """Averaged single-sided spectrum, following §10 and §11.

    §5  N_FFT = max(16, LOR) — LOR is the block size, not a line count.
    §10.1 the record mean is removed once, before segmentation.
    §11.1 stepSize = max(1, round(N_FFT × (1 − overlap/100))).
    §11.2 a frame start is clamped to N − N_FFT, so a short record re-reads its
          last window rather than cutting the average short.
    §11.3 LINEAR MAGNITUDE averaging — the mean of |A_s|, not power or vector
          averaging.
    """
    data = _to_array(samples)
    n = len(data)
    if n < 4:
        raise ValueError("Need at least 4 samples for FFT")

    # §5 — LOR is the block size directly.
    nfft = max(MIN_FFT_SIZE, int(fft_lines)) if fft_lines else n
    nfft = min(nfft, n) if nfft > n else nfft

    # §10.1 — DC removed once over the whole record (Pipeline A).
    dc_removed = remove_mean(data)

    win = build_window(nfft, window)
    cg = coherent_gain(win)

    # §11.1 / §11.4 — sample budget, and the guard rail for a short record.
    step, required = acquisition_sample_budget(nfft, max(1, int(averages)), overlap_percent)
    effective_averages = max(1, int(averages))
    averaging_skipped = effective_averages > 1 and n < required
    if averaging_skipped:
        effective_averages = 1

    accum = np.zeros(nfft // 2 + 1, dtype=np.float64)
    used = 0
    for s in range(effective_averages):
        # §11.2 — clamp so the frame always lies inside the record.
        start = 0 if effective_averages <= 1 else min(max(0, n - nfft), s * step)
        segment = dc_removed[start : start + nfft]
        if segment.size == 0:
            break
        accum += magnitude_spectrum_half(segment * win[: segment.size], nfft, cg)
        used += 1

    if used == 0:
        raise ValueError("No usable FFT segment")

    # §11.3 — linear magnitude averaging.
    spectrum = accum / used
    freqs = frequency_axis_hz(spectrum.size, sampling_rate_hz, nfft)

    # Retained from this platform, not from §6: the Java analyser never limits a
    # spectrum by Fmax, but the UI passes one and expects the axis to honour it.
    # Appendix A expects a full DC..Nyquist axis, so when the mask does clip the
    # top the metadata says so rather than silently claiming an untruncated axis.
    full_bins = int(spectrum.size)
    if frequency_max_hz:
        mask = freqs <= frequency_max_hz
        freqs = freqs[mask]
        spectrum = spectrum[mask]
    includes_nyquist = int(spectrum.size) == full_bins

    return {
        "x": freqs.tolist(),
        "y": spectrum.tolist(),
        "x_label": "Frequency (Hz)",
        "y_label": "Magnitude",
        "title": "FFT Spectrum",
        "metadata": {
            "plot_style": "line",
            "fft_lines": int(spectrum.size),
            "block_size": int(nfft),
            "averages": used,
            "window": parse_window(window),
            "coherent_gain": cg,
            "step_size": step,
            "required_samples": required,
            "averaging_skipped": averaging_skipped,
            "delta_f_hz": sampling_rate_hz / nfft,
            "nyquist_hz": sampling_rate_hz / 2.0,
            "sampling_rate_hz": sampling_rate_hz,
            **frequency_axis_meta(includes_nyquist=includes_nyquist),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# §17 — Envelope
# ─────────────────────────────────────────────────────────────────────────────
def one_pole_lowpass(data: np.ndarray, sampling_rate_hz: float, fc_hz: float) -> np.ndarray:
    """§17.1 — first-order causal low-pass.

        Δt = 1/Fs ; RC = 1/(2π·fc) ; α = Δt/(RC + Δt)
        y[0] = x[0] ;  y[i] = α·x[i] + (1 − α)·y[i−1]

    Forward only — phase-distorting, and deliberately not a zero-phase pass, so
    it matches the Java filter.
    """
    if data.size == 0 or sampling_rate_hz <= 0:
        return data
    dt = 1.0 / sampling_rate_hz
    rc = 1.0 / (2.0 * np.pi * max(1.0, fc_hz))
    alpha = dt / (rc + dt)

    out = np.empty_like(data)
    out[0] = data[0]
    for i in range(1, data.size):
        out[i] = alpha * data[i] + (1.0 - alpha) * out[i - 1]
    return out


def one_pole_highpass(data: np.ndarray, sampling_rate_hz: float, fc_hz: float) -> np.ndarray:
    """§17.1 — x − lowpass(x)."""
    return data - one_pole_lowpass(data, sampling_rate_hz, fc_hz)


def band_pass(
    data: np.ndarray, sampling_rate_hz: float, f_low_hz: float, f_high_hz: float
) -> np.ndarray:
    """§17.1 — cascade of one 1-pole high-pass and one 1-pole low-pass."""
    return one_pole_lowpass(
        one_pole_highpass(data, sampling_rate_hz, f_low_hz), sampling_rate_hz, f_high_hz
    )


def rectified_envelope(
    data: np.ndarray, sampling_rate_hz: float, lp_hz: float = ENVELOPE_RECTIFIED_LP_HZ
) -> np.ndarray:
    """§17.3 — gE envelope: |a| through a 1-pole low-pass. No Hilbert, no band-pass."""
    return one_pole_lowpass(np.abs(data), sampling_rate_hz, lp_hz)


def compute_envelope_spectrum(
    samples: list[float],
    sampling_rate_hz: float,
    fft_lines: int | None = None,
    frequency_max_hz: float | None = None,
    *,
    low_cut_hz: float = ENVELOPE_LOW_CUT_HZ,
    high_cut_hz: float = ENVELOPE_HIGH_CUT_HZ,
) -> dict[str, Any]:
    """§17.1 — band-pass → Hilbert envelope → Hann block → spectrum.

    Band limits are clamped against Nyquist exactly as the Java util does. The
    block is a single Hann-windowed segment taken from the *start* of the
    envelope, so there is no averaging and no overlap on this path.

    One deliberate departure: the Java implementation multiplies the analytic
    magnitude by a further 1/nfft on top of the inverse transform's own 1/N,
    which drives envelope amplitudes to ~1e-6 and makes its sideband alarm
    unreachable. That second factor is dropped here so the envelope carries the
    signal's real amplitude.
    """
    data = _to_array(samples)
    n = len(data)
    if n < 16 or sampling_rate_hz <= 0:
        raise ValueError("Need at least 16 samples and a positive sample rate")

    # §17.1 — band clamping against Nyquist.
    nyquist = sampling_rate_hz / 2.0
    lo = max(1.0, low_cut_hz)
    hi = max(lo + 1.0, high_cut_hz)
    if hi >= 0.98 * nyquist:
        hi = 0.95 * nyquist
    if lo >= hi:
        lo = max(1.0, 0.4 * hi)

    filtered = band_pass(data, sampling_rate_hz, lo, hi)
    envelope = np.abs(hilbert(filtered))

    # §17.1 — segment sizing: effectively a single 1024-point block.
    target = fft_lines if fft_lines else ENVELOPE_SEGMENT_TARGET
    segment_len = min(
        ENVELOPE_SEGMENT_MAX,
        max(ENVELOPE_SEGMENT_MIN, next_power_of_two(min(envelope.size, target))),
    )
    segment_len = min(segment_len, envelope.size)
    nfft = next_power_of_two(segment_len)

    segment = remove_mean(envelope[:segment_len])
    win = build_window(segment_len, "HANNING")
    cg = coherent_gain(win)

    spectrum = magnitude_spectrum_half(segment * win, nfft, cg)
    freqs = frequency_axis_hz(spectrum.size, sampling_rate_hz, nfft)

    full_bins = int(spectrum.size)
    if frequency_max_hz:
        mask = freqs <= frequency_max_hz
        freqs = freqs[mask]
        spectrum = spectrum[mask]

    return {
        "x": freqs.tolist(),
        "y": spectrum.tolist(),
        "x_label": "Frequency (Hz)",
        "y_label": "Envelope Magnitude",
        "title": "Envelope Spectrum",
        "metadata": {
            "plot_style": "line",
            "fft_lines": int(spectrum.size),
            "block_size": int(nfft),
            "segment_samples": int(segment_len),
            "averages": 1,
            "window": "HANNING",
            "low_cut_hz": lo,
            "high_cut_hz": hi,
            "delta_f_hz": sampling_rate_hz / nfft,
            "nyquist_hz": sampling_rate_hz / 2.0,
            "sampling_rate_hz": sampling_rate_hz,
            **frequency_axis_meta(
                includes_nyquist=int(spectrum.size) == full_bins
            ),
        },
    }


def compute_envelope_waveform(
    samples: list[float],
    sampling_rate_hz: float,
    *,
    low_cut_hz: float = ENVELOPE_LOW_CUT_HZ,
    high_cut_hz: float = ENVELOPE_HIGH_CUT_HZ,
) -> dict[str, Any]:
    """§17.1 — the demodulated envelope itself, before any transform.

    Appendix A: X = i/Fs in seconds, Y = envelope in g. Same band-pass and same
    Hilbert magnitude the envelope *spectrum* is built from, so the two graphs
    are two views of one signal rather than two different envelopes.

    The reference implementation divides this trace by `nfft` — the same stray
    factor dropped from `compute_envelope_spectrum`, and dropped here for the
    same reason: it is a scaling artefact, not a definition.
    """
    data = _to_array(samples)
    n = len(data)
    if n < 16 or sampling_rate_hz <= 0:
        raise ValueError("Need at least 16 samples and a positive sample rate")

    nyquist = sampling_rate_hz / 2.0
    lo = max(1.0, low_cut_hz)
    hi = max(lo + 1.0, high_cut_hz)
    if hi >= 0.98 * nyquist:
        hi = 0.95 * nyquist
    if lo >= hi:
        lo = max(1.0, 0.4 * hi)

    envelope = np.abs(hilbert(band_pass(data, sampling_rate_hz, lo, hi)))
    # Appendix A: t_i = i / Fs — index-derived, never the timestamp column.
    time_s = np.arange(n, dtype=np.float64) / sampling_rate_hz

    return {
        "x": time_s.tolist(),
        "y": envelope.tolist(),
        "x_label": "Time (s)",
        "y_label": "Envelope Amplitude",
        "title": "Envelope Waveform",
        "metadata": {
            "plot_style": "line",
            "low_cut_hz": lo,
            "high_cut_hz": hi,
            "sample_count": n,
            "sampling_rate_hz": sampling_rate_hz,
            **time_axis_meta(),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# §13 / §14.3 — Unit conversion and time-domain integration
# ─────────────────────────────────────────────────────────────────────────────
#: §13.2 — exact standard gravity.
G_TO_MS2 = 9.80665

#: §13.1 — configured acceleration unit → g.
_UNIT_TO_G = {
    "g": 1.0,
    "mg": 1.0 / 1000.0,
    "m/s2": 1.0 / G_TO_MS2,
    "mm/s2": 1.0 / (G_TO_MS2 * 1000.0),
}


def normalize_acceleration_unit(raw: Any) -> str:
    """§13.1 — unit string → canonical key, defaulting silently to g."""
    if raw is None:
        return "g"
    name = str(raw).strip().lower()
    if name == "g":
        return "g"
    if name == "mg":
        return "mg"
    if name in ("m/s2", "m/s^2", "mps2"):
        return "m/s2"
    if name in ("mm/s2", "mm/s^2", "mmps2"):
        return "mm/s2"
    return "g"


def convert_acceleration_to_g(data: np.ndarray, unit: Any) -> np.ndarray:
    """§13.1 — scale a channel into g."""
    factor = _UNIT_TO_G.get(normalize_acceleration_unit(unit), 1.0)
    return data if factor == 1.0 else data * factor


def integrate(data: np.ndarray, dt: float) -> np.ndarray:
    """§14.3 — cumulative trapezoid, v[0] = 0.

        v[i] = v[i−1] + 0.5·(a[i] + a[i−1])·Δt
    """
    if data.size == 0:
        return data
    out = np.zeros_like(data)
    out[1:] = np.cumsum(0.5 * (data[1:] + data[:-1]) * dt)
    return out


def detrend(data: np.ndarray) -> np.ndarray:
    """§14.3 — mean removal only, not a linear-regression detrend."""
    return remove_mean(data)


def velocity_rms_mm_s(acceleration_g: np.ndarray, sampling_rate_hz: float) -> float:
    """§14.3 — VRMS by time-domain integration.

        a[m/s²] = a[g] × 9.80665
        v[m/s]  = detrend(cumulative trapezoid(a, Δt))
        VRMS    = rms(v) × 1000
    """
    if acceleration_g.size == 0 or sampling_rate_hz <= 0:
        return 0.0
    accel_ms2 = acceleration_g * G_TO_MS2
    velocity = detrend(integrate(accel_ms2, 1.0 / sampling_rate_hz))
    return float(np.sqrt(np.mean(velocity**2)) * 1000.0)


def compute_trend_plot(
    timestamps: list[float],
    samples: list[float],
    sampling_rate_hz: float,
    num_segments: int = 32,
) -> dict[str, Any]:
    """Amplitude trend over time — RMS per time segment.

    §18: the Java analyser stores one trend point per file per channel with no
    aggregation. This in-capture segmentation is a plotting aid this platform
    adds on top; the per-segment statistic is the same RMS, √(Σx²/N).
    """
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
        "metadata": {
            "plot_style": "line",
            "num_segments": num_segments,
            # Appendix A: this trend's X is elapsed time *inside one capture*,
            # not the capture-to-capture datetime axis of the fleet trend.
            "trend_domain": "within_capture",
            **time_axis_meta(),
            # ...and Y here is RMS, the one place amplitude is not 0-peak.
            "amplitude_convention": "rms",
        },
    }
