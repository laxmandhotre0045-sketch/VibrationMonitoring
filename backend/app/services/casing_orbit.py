"""
Casing orbit (Lissajous) from two synchronously-sampled accelerometer channels.

WHAT THIS IS
------------
A time-domain parametric plot X(t) vs Y(t) of bearing-housing motion. The sensors are
IEPE accelerometers on the casing, NOT shaft proximity probes, so this is a CASING orbit
and never a shaft-centreline orbit.

SIGNAL PATH
-----------
    raw g  ->  x9.80665 (m/s^2)  ->  rFFT  ->  band mask around n x shaft
           ->  divide by (2*pi*f)^2  (frequency-domain double integration)
           ->  irFFT  ->  x1e6  ->  displacement in micrometres

Integrating in the frequency domain avoids the unbounded low-frequency drift that
time-domain double integration produces. Bins at or below INTEGRATION floor are zeroed
rather than divided, so f = 0 can never divide by zero.

WINDOWING
---------
No Hann window is applied on this path. Hann is right for spectrum estimation, but
applying it before FFT -> zero bins -> IFFT tapers the reconstruction to zero at both
ends and drags the orbit into a false spiral toward the origin. The reconstruction uses
the full rectangular record and the displayed segment is taken from the MIDDLE, away
from both edges.

NO KEYPHASOR
------------
There is no tach/keyphasor input in this system. The orbit is time-parametric only:
no absolute phase, no once-per-rev marker, and no forward/reverse precession claim.
`phase_reference` is carried in the response so a real keyphasor can replace it later.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

G_TO_MS2 = 9.80665
M_TO_UM = 1.0e6

PHASE_REFERENCE_TIME = "time_only"

#: Never integrate below this: double integration divides by f^2, so a near-DC bin would
#: explode into metres of fictitious displacement.
ABSOLUTE_MIN_INTEGRATION_HZ = 2.0
SHAFT_FRACTION_MIN_INTEGRATION = 0.25

#: Practical default when the record is long enough; clamped to what actually exists.
PREFERRED_FILTER_REVS = 16

#: Cap on points sent to the browser per trace.
MAX_ORBIT_POINTS = 4000


def integration_floor_hz(shaft_hz: float) -> float:
    """Lowest frequency allowed through the double integrator."""
    return max(ABSOLUTE_MIN_INTEGRATION_HZ, SHAFT_FRACTION_MIN_INTEGRATION * shaft_hz)


def resolve_filter_revolutions(
    sample_count: int,
    sampling_rate_hz: float,
    shaft_hz: float,
    requested: int | None,
) -> tuple[int, float]:
    """
    Revolutions actually usable for filtering, plus the total revolutions in the record.

    A capture is one continuous record; there is no longer stream to borrow from, so the
    request is clamped to what the record holds rather than silently padded.
    """
    if shaft_hz <= 0 or sampling_rate_hz <= 0:
        return 0, 0.0
    duration_s = sample_count / sampling_rate_hz
    available_revs = duration_s * shaft_hz
    target = requested if requested and requested > 0 else PREFERRED_FILTER_REVS
    usable = min(float(target), available_revs)
    return max(0, int(math.floor(usable))), available_revs


def evaluate_bandwidth(
    sample_count: int,
    sampling_rate_hz: float,
    centre_hz: float,
    bandwidth_percent: float,
) -> dict[str, Any]:
    """
    Compare the requested band against what the record can actually resolve.

    Delta f = Fs / N. A band narrower than one bin cannot be isolated, so the effective
    band is widened to one bin and the caller is told, rather than returning an empty
    or meaningless orbit.
    """
    resolution_hz = sampling_rate_hz / sample_count if sample_count else float("inf")
    requested_half = centre_hz * (bandwidth_percent / 100.0)

    # Resolving a half-band of B needs delta-f <= B, i.e. at least one bin inside the
    # band either side of centre. Anything coarser cannot isolate the component, so the
    # band is widened to the resolution and the caller is told.
    min_half = resolution_hz
    effective_half = max(requested_half, min_half)
    sufficient = requested_half >= min_half

    required_duration_s = (1.0 / requested_half) if requested_half > 0 else float("inf")

    return {
        "frequency_resolution_hz": resolution_hz,
        "requested_half_bandwidth_hz": requested_half,
        "effective_half_bandwidth_hz": effective_half,
        "effective_bandwidth_percent": (effective_half / centre_hz * 100.0) if centre_hz > 0 else 0.0,
        "bandwidth_sufficient": bool(sufficient),
        "required_duration_s": required_duration_s,
        "lower_hz": max(0.0, centre_hz - effective_half),
        "upper_hz": centre_hz + effective_half,
    }


def _to_finite_array(samples: Sequence[float]) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float64)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def acceleration_to_displacement_um(
    accel_g: np.ndarray,
    sampling_rate_hz: float,
    *,
    lower_hz: float | None,
    upper_hz: float | None,
    floor_hz: float,
) -> np.ndarray:
    """
    Band-limited double integration, entirely in the frequency domain.

    `lower_hz`/`upper_hz` None means "no band mask" (the unfiltered overlay), but the
    integration floor still applies — otherwise near-DC bins dominate everything.
    """
    n = accel_g.size
    if n < 4:
        return np.zeros(n)

    spectrum = np.fft.rfft(accel_g * G_TO_MS2)
    freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate_hz)

    transfer = np.zeros_like(freqs)
    usable = freqs > max(floor_hz, 0.0)
    if lower_hz is not None and upper_hz is not None:
        usable &= (freqs >= lower_hz) & (freqs <= upper_hz)

    # x(f) = a(f) / (2*pi*f)^2 — only where f is safely above the floor.
    transfer[usable] = 1.0 / np.square(2.0 * np.pi * freqs[usable])

    displacement_m = np.fft.irfft(spectrum * transfer, n=n)
    return displacement_m * M_TO_UM


def _decimate(values: np.ndarray, max_points: int) -> np.ndarray:
    if values.size <= max_points:
        return values
    step = int(np.ceil(values.size / max_points))
    return values[::step]


def build_casing_orbit(
    *,
    samples_x: Sequence[float],
    samples_y: Sequence[float],
    sampling_rate_hz: float,
    shaft_hz: float,
    harmonic: int,
    bandwidth_percent: float,
    filter_revolutions: int | None,
    display_revolutions: float,
    include_unfiltered: bool,
) -> dict[str, Any]:
    """
    Returns filtered (and optionally unfiltered) displacement orbits in micrometres.

    X and Y are processed with identical parameters over the identical sample window —
    they come from the same interleaved capture, so index i is the same instant in both.
    """
    warnings: list[str] = []

    x_all = _to_finite_array(samples_x)
    y_all = _to_finite_array(samples_y)
    if x_all.size != y_all.size:
        # Same capture, same rows, so this should not happen; truncating is still safer
        # than pairing mismatched instants.
        size = min(x_all.size, y_all.size)
        x_all, y_all = x_all[:size], y_all[:size]
        warnings.append("X and Y channel lengths differed; truncated to the common length.")

    total_samples = x_all.size
    if total_samples < 16:
        raise ValueError("Capture has too few samples for an orbit")
    if shaft_hz <= 0:
        raise ValueError("Unable to determine shaft frequency for 1x/2x filtering")

    centre_hz = shaft_hz * harmonic
    nyquist = sampling_rate_hz / 2.0
    if centre_hz >= nyquist:
        raise ValueError(f"{harmonic}x target ({centre_hz:.1f} Hz) is above Nyquist")

    filter_revs, available_revs = resolve_filter_revolutions(
        total_samples, sampling_rate_hz, shaft_hz, filter_revolutions
    )
    if filter_revs <= 0:
        raise ValueError("Record is shorter than one shaft revolution")
    if filter_revolutions and filter_revs < filter_revolutions:
        warnings.append(
            f"Requested {filter_revolutions} revolutions for filtering but the capture holds "
            f"only {available_revs:.1f}; using {filter_revs}."
        )

    # Filtering window: centred on the record so the displayed middle stays clear of edges.
    filter_samples = min(total_samples, int(round(filter_revs * sampling_rate_hz / shaft_hz)))
    filter_start = (total_samples - filter_samples) // 2
    x_filt_src = x_all[filter_start : filter_start + filter_samples]
    y_filt_src = y_all[filter_start : filter_start + filter_samples]

    band = evaluate_bandwidth(filter_samples, sampling_rate_hz, centre_hz, bandwidth_percent)
    if not band["bandwidth_sufficient"]:
        warnings.append(
            f"Insufficient record length for the requested bandwidth. Requested ±"
            f"{band['requested_half_bandwidth_hz']:.3f} Hz, but {filter_samples / sampling_rate_hz:.3f} s "
            f"of data resolves only ≈{band['frequency_resolution_hz']:.2f} Hz. "
            f"Widened to ±{band['effective_half_bandwidth_hz']:.3f} Hz "
            f"({band['effective_bandwidth_percent']:.1f}%); ≈{band['required_duration_s']:.2f} s "
            f"would be needed for the requested band."
        )

    floor_hz = integration_floor_hz(shaft_hz)
    x_disp = acceleration_to_displacement_um(
        x_filt_src, sampling_rate_hz,
        lower_hz=band["lower_hz"], upper_hz=band["upper_hz"], floor_hz=floor_hz,
    )
    y_disp = acceleration_to_displacement_um(
        y_filt_src, sampling_rate_hz,
        lower_hz=band["lower_hz"], upper_hz=band["upper_hz"], floor_hz=floor_hz,
    )

    unfiltered_x = unfiltered_y = None
    if include_unfiltered:
        unfiltered_x = acceleration_to_displacement_um(
            x_filt_src, sampling_rate_hz, lower_hz=None, upper_hz=None, floor_hz=floor_hz
        )
        unfiltered_y = acceleration_to_displacement_um(
            y_filt_src, sampling_rate_hz, lower_hz=None, upper_hz=None, floor_hz=floor_hz
        )
        warnings.append(
            f"Unfiltered overlay is high-pass limited at {floor_hz:.1f} Hz; double integration "
            "below that is numerically unreliable."
        )

    # Display segment: the MIDDLE of the reconstruction, away from both boundaries.
    display_samples = min(
        filter_samples, max(8, int(round(display_revolutions * sampling_rate_hz / shaft_hz)))
    )
    display_start = (filter_samples - display_samples) // 2
    sl = slice(display_start, display_start + display_samples)

    time_axis = (np.arange(filter_samples) / sampling_rate_hz)[sl]
    time_axis = time_axis - time_axis[0]
    revolution = time_axis * shaft_hz

    x_out = _decimate(x_disp[sl], MAX_ORBIT_POINTS)
    y_out = _decimate(y_disp[sl], MAX_ORBIT_POINTS)
    t_out = _decimate(time_axis, MAX_ORBIT_POINTS)
    rev_out = _decimate(revolution, MAX_ORBIT_POINTS)

    peak_disp = float(max(np.max(np.abs(x_out)), np.max(np.abs(y_out)))) if x_out.size else 0.0

    return {
        "x_data": x_out.tolist(),
        "y_data": y_out.tolist(),
        "elapsed_s": t_out.tolist(),
        "revolution": rev_out.tolist(),
        "unfiltered_x": _decimate(unfiltered_x[sl], MAX_ORBIT_POINTS).tolist() if unfiltered_x is not None else None,
        "unfiltered_y": _decimate(unfiltered_y[sl], MAX_ORBIT_POINTS).tolist() if unfiltered_y is not None else None,
        "point_count": int(x_out.size),
        "centre_hz": centre_hz,
        "harmonic": harmonic,
        "lower_hz": band["lower_hz"],
        "upper_hz": band["upper_hz"],
        "frequency_resolution_hz": band["frequency_resolution_hz"],
        "requested_half_bandwidth_hz": band["requested_half_bandwidth_hz"],
        "effective_half_bandwidth_hz": band["effective_half_bandwidth_hz"],
        "effective_bandwidth_percent": band["effective_bandwidth_percent"],
        "bandwidth_sufficient": band["bandwidth_sufficient"],
        "required_duration_s": band["required_duration_s"],
        "integration_floor_hz": floor_hz,
        "filter_revolutions": filter_revs,
        "available_revolutions": available_revs,
        "display_revolutions": display_revolutions,
        "filter_duration_s": filter_samples / sampling_rate_hz,
        "display_duration_s": display_samples / sampling_rate_hz,
        "record_duration_s": total_samples / sampling_rate_hz,
        "peak_displacement_um": peak_disp,
        "phase_reference": PHASE_REFERENCE_TIME,
        "keyphasor_available": False,
        "warnings": warnings,
    }
