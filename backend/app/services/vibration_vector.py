"""
Vibration vector (polar) analysis: amplitude + phase at one frequency, per FFT block.

WHY THIS EXISTS SEPARATELY
--------------------------
`signal_processing.compute_fft_spectrum` takes `np.abs(fft(...))` and throws the complex
result away, so phase cannot be recovered from anything the waterfall or cascade stores.
This module re-runs the FFT from the stored raw samples purely to keep the complex value.
It does not modify, replace or re-scale any existing output: the same Hanning window and
the same `2/n` magnitude scaling are used, so amplitudes here match the existing spectra.

BLOCKS ARE WITHIN ONE CAPTURE, NOT ACROSS CAPTURES
--------------------------------------------------
Phase is only comparable between blocks that share a continuous time base. Two separate
uploads start acquisition at arbitrary, unrelated instants, so phase(captureB) -
phase(captureA) carries no physical meaning. One capture is therefore split into
overlapping blocks and every block is referenced to block 0 of that same record.

PHASE IS SELF-REFERENCED
------------------------
There is no keyphasor/tachometer signal path in this system, so absolute shaft phase is
not available. `relative_phase_deg` is measured against the first block; the absolute
angle of block 0 is arbitrary. Only changes between blocks are meaningful.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
from scipy.fft import fft

from app.services.signal_processing import build_window, coherent_gain, remove_mean

#: Same window as compute_fft_spectrum / feature_extraction (§9.1).
FFT_WINDOW = "Hanning"

#: Phase reference modes. Only SELF is implementable without a keyphasor.
PHASE_REFERENCE_SELF = "first_block"
PHASE_REFERENCE_KEYPHASOR = "keyphasor"

#: 0 deg at 3 o'clock, positive counter-clockwise — matches atan2 directly so no
#: hidden sign flip can creep in between the maths and the chart.
ANGLE_CONVENTION = "0deg_at_3_oclock_ccw_positive"

DEFAULT_OVERLAP = 0.5
MIN_BLOCKS = 2

#: Drift heuristic: a near-linear phase ramp at near-constant amplitude usually means the
#: chosen bin does not sit on the real signal frequency, not that the machine changed.
DRIFT_MIN_R2 = 0.90
DRIFT_MAX_AMPLITUDE_CV = 0.15
DRIFT_MIN_BIN_FRACTION = 0.05


def wrap_degrees(degrees: float) -> float:
    """
    Wrap to (-180, +180] — the same half-open interval atan2 returns, so a phase of
    exactly half a turn reads as +180 rather than flipping sign to -180.
    """
    wrapped = (degrees + 180.0) % 360.0 - 180.0
    return 180.0 if wrapped == -180.0 else wrapped


def resolve_block_size(sample_count: int, requested: int | None, fft_lines: int | None) -> int:
    """
    Block length in samples.

    Defaults to the sensor's configured FFT size so frequency resolution matches the
    spectra the user already sees, then shrinks if the capture is too short to yield
    enough blocks for a vector path.
    """
    preferred = requested or fft_lines or 1024
    preferred = min(preferred, sample_count)
    if preferred < 8:
        return max(8, sample_count)
    # Guarantee at least MIN_BLOCKS at 50% overlap.
    max_for_blocks = int(sample_count / (1 + (MIN_BLOCKS - 1) * (1 - DEFAULT_OVERLAP)))
    return max(8, min(preferred, max_for_blocks))


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Least-squares slope plus R^2. Returns (slope, r_squared)."""
    if x.size < 3:
        return 0.0, 0.0
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-30 else 0.0
    return float(slope), float(max(0.0, min(1.0, r2)))


def analyse_drift(
    times_s: Sequence[float],
    relative_phases_deg: Sequence[float],
    amplitudes: Sequence[float],
    bin_width_hz: float,
) -> dict[str, Any]:
    """
    Detect a phase ramp that is better explained by bin mismatch than by machine change.

    A signal at f_true observed in a bin at f_bin advances by 360*(f_true-f_bin) degrees
    per second, so the fitted slope converts straight back into an implied offset.
    Informational only — never an alarm, and never called a fault.
    """
    if len(times_s) < 3:
        return {
            "phase_slope_deg_per_s": None,
            "implied_frequency_offset_hz": None,
            "amplitude_cv": None,
            "linear_fit_r2": None,
            "likely_bin_mismatch": False,
        }

    t = np.asarray(times_s, dtype=np.float64)
    # Unwrap before fitting: wrapped phase would break a linear fit at the +/-180 seam.
    phase = np.degrees(np.unwrap(np.radians(np.asarray(relative_phases_deg, dtype=np.float64))))
    amp = np.asarray(amplitudes, dtype=np.float64)

    slope, r2 = _linear_fit(t, phase)
    implied_offset = slope / 360.0

    mean_amp = float(np.mean(amp))
    cv = float(np.std(amp) / mean_amp) if mean_amp > 1e-30 else None

    likely = bool(
        r2 >= DRIFT_MIN_R2
        and cv is not None
        and cv <= DRIFT_MAX_AMPLITUDE_CV
        and bin_width_hz > 0
        and abs(implied_offset) >= bin_width_hz * DRIFT_MIN_BIN_FRACTION
    )

    return {
        "phase_slope_deg_per_s": slope,
        "implied_frequency_offset_hz": implied_offset,
        "amplitude_cv": cv,
        "linear_fit_r2": r2,
        "likely_bin_mismatch": likely,
    }


def compute_vector_blocks(
    samples: Sequence[float],
    sampling_rate_hz: float,
    target_hz: float,
    *,
    block_size: int,
    overlap: float = DEFAULT_OVERLAP,
) -> dict[str, Any]:
    """
    Complex FFT at one bin for every block of a capture.

    amplitude = 2|X[k]| / (N*CG)   (§10.2 scaling, as compute_fft_spectrum)
    phase     = atan2(Im, Re)
    relative  = wrap(phase - phase_of_block_0)
    """
    data = np.asarray(samples, dtype=np.float64)
    data = data[np.isfinite(data)]
    n = data.size
    if n < 8:
        raise ValueError("Capture has too few samples for vector analysis")

    bs = max(8, min(int(block_size), n))
    step = max(1, int(round(bs * (1.0 - max(0.0, min(0.95, overlap))))))
    bin_width = sampling_rate_hz / bs

    max_bin = bs // 2 - 1
    bin_index = int(round(target_hz / bin_width)) if bin_width > 0 else 0
    bin_index = max(0, min(bin_index, max_bin))
    bin_hz = bin_index * bin_width

    window = build_window(bs, FFT_WINDOW)
    cg = coherent_gain(window)
    blocks: list[dict[str, Any]] = []
    reference_phase: float | None = None

    for start in range(0, n - bs + 1, step):
        # §10.1 - the block mean is removed before the transform.
        segment = remove_mean(data[start : start + bs]) * window
        spectrum = fft(segment)
        value = spectrum[bin_index]
        amplitude = float(np.abs(value) * (2.0 / (bs * cg)))
        raw_phase = math.degrees(math.atan2(float(value.imag), float(value.real)))

        # De-rotate to a common origin (sample 0).
        #
        # An FFT bin's phase is referenced to the START of its own block, so shifting the
        # block by m samples rotates bin k by -360*k*m/N. Without removing that, a
        # perfectly steady tone appears to jump between blocks (at 50% overlap and k=25
        # it flips a full 180 deg every block) and swamps the real phase change.
        block_origin_correction = 360.0 * bin_index * start / bs
        phase = wrap_degrees(raw_phase + block_origin_correction)

        if reference_phase is None:
            reference_phase = phase

        blocks.append(
            {
                "block_index": len(blocks),
                "start_sample": int(start),
                # Block centre: the natural time stamp for a windowed estimate.
                "time_s": float((start + bs / 2.0) / sampling_rate_hz),
                "amplitude": amplitude,
                "phase_deg": phase,
                "relative_phase_deg": wrap_degrees(phase - reference_phase),
                "is_reference": len(blocks) == 0,
            }
        )

    if not blocks:
        raise ValueError("Capture is shorter than one analysis block")

    amplitudes = [b["amplitude"] for b in blocks]
    drift = analyse_drift(
        [b["time_s"] for b in blocks],
        [b["relative_phase_deg"] for b in blocks],
        amplitudes,
        bin_width,
    )

    return {
        "blocks": blocks,
        "block_size": bs,
        "block_step": step,
        "overlap": 1.0 - step / bs,
        "block_count": len(blocks),
        "window": FFT_WINDOW,
        "bin_index": bin_index,
        "bin_hz": bin_hz,
        "frequency_resolution_hz": bin_width,
        "block_duration_s": bs / sampling_rate_hz,
        "amplitude_min": float(min(amplitudes)),
        "amplitude_max": float(max(amplitudes)),
        "phase_reference": PHASE_REFERENCE_SELF,
        "angle_convention": ANGLE_CONVENTION,
        "drift": drift,
    }
