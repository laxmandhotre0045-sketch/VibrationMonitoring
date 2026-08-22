"""
1x amplitude migration: how the once-per-revolution casing response moves in the
Vertical-vs-Horizontal amplitude plane across captures.

WHAT THIS IS — AND IS NOT
-------------------------
One point per capture: X = 1x amplitude of the vertical channel, Y = 1x amplitude of the
horizontal channel. Both are magnitudes, so the plot lives in the positive quadrant by
construction and no sign is ever manufactured.

This is NOT a shaft-centreline plot. The sensors are AC accelerometers on the casing;
static shaft position, journal position, attitude angle, eccentricity ratio and bearing
clearance all require DC-capable proximity probes measuring shaft-to-bearing gap, which
this system does not have. Nothing here computes or reports those quantities.

CAPTURE-SPECIFIC 1x
-------------------
Every capture uses its OWN estimated shaft frequency. A fixed bin would turn ordinary
speed drift into fake amplitude migration as the real 1x wandered across bins.

REUSE
-----
The complex FFT comes from `vibration_vector.compute_vector_blocks` (one block spanning
the whole record) and the acceleration-to-displacement conversion from
`casing_orbit.displacement_um_from_acceleration_g`. Both are already validated; nothing
is reimplemented here.

PHASE
-----
Cross-channel phase is meaningful because the channels are sampled on one clock, but
there is no keyphasor, so only the DIFFERENCE is reported and it is never called
absolute shaft phase.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np

from app.services.casing_orbit import displacement_um_from_acceleration_g
from app.services.vibration_vector import compute_vector_blocks, wrap_degrees

AMPLITUDE_UNIT = "um"
SOURCE_UNIT = "g"

SPEED_SOURCE_ESTIMATED = "estimated"
SPEED_SOURCE_OVERRIDE = "override"

QUALITY_VALID = "valid"
QUALITY_INVALID = "invalid"
QUALITY_UNCERTAIN = "uncertain"

#: A 1x sitting closer than this fraction of a bin to its neighbour is flagged: at coarse
#: resolution the true 1x may not be separable from adjacent content.
BIN_UNCERTAINTY_FRACTION = 0.5

#: Below this the reading is reported as near the processing/noise floor rather than
#: presented as a confident response level. Never a health verdict.
LOW_SIGNAL_UM = 1e-4


def extract_one_x(
    samples: Sequence[float],
    sampling_rate_hz: float,
    shaft_hz: float,
) -> dict[str, Any]:
    """
    Complex 1x component of one channel over the whole capture.

    Delegates to the validated vector path with a single block spanning the record, so
    amplitude scaling, windowing and phase convention match the vibration vector plot
    exactly.
    """
    data = np.asarray(samples, dtype=np.float64)
    n = data.size
    result = compute_vector_blocks(
        data,
        sampling_rate_hz,
        shaft_hz,
        block_size=n,
        overlap=0.0,
    )
    block = result["blocks"][0]
    return {
        "amplitude_g": float(block["amplitude"]),
        "phase_deg": float(block["phase_deg"]),
        "bin_hz": float(result["bin_hz"]),
        "bin_index": int(result["bin_index"]),
        "frequency_resolution_hz": float(result["frequency_resolution_hz"]),
    }


def response_ellipse(ax: float, ay: float, relative_phase_deg: float) -> dict[str, Any]:
    """
    Geometry of the 1x response ellipse traced by

        X(t) = ax*cos(wt),  Y(t) = ay*cos(wt + d)

    Writing p(t) = u*cos(wt) + v*sin(wt) with u = [ax, ay*cos d] and
    v = [0, ay*sin d], the ellipse is the image of the unit circle under M = [u v].
    Its semi-axes are therefore exactly the singular values of M, and the orientation is
    the direction of the leading left singular vector. No pixel measurement, no fitting.
    """
    delta = math.radians(relative_phase_deg)
    # Y(t) = ay*cos(wt + d) = ay*cos d * cos(wt) - ay*sin d * sin(wt), so
    #   u = [ax, ay*cos d]   (the cos(wt) coefficients)
    #   v = [0,  -ay*sin d]  (the sin(wt) coefficients)
    # and M holds u and v as its COLUMNS.
    m = np.array(
        [
            [ax, 0.0],
            [ay * math.cos(delta), -ay * math.sin(delta)],
        ],
        dtype=np.float64,
    )

    try:
        u_mat, singular, _ = np.linalg.svd(m)
    except np.linalg.LinAlgError:
        return {
            "major_axis": 0.0,
            "minor_axis": 0.0,
            "orientation_deg": 0.0,
            "ellipticity": 0.0,
        }

    major = float(singular[0])
    minor = float(singular[1])
    direction = u_mat[:, 0]
    orientation = math.degrees(math.atan2(float(direction[1]), float(direction[0])))
    # Orientation is an axis, not a vector: fold to (-90, 90].
    if orientation > 90.0:
        orientation -= 180.0
    elif orientation <= -90.0:
        orientation += 180.0

    return {
        "major_axis": major,
        "minor_axis": minor,
        "orientation_deg": orientation,
        "ellipticity": float(minor / major) if major > 1e-30 else 0.0,
    }


def build_migration_point(
    *,
    upload_id: Any,
    captured_at: Any,
    sequence: int,
    samples_x: Sequence[float] | None,
    samples_y: Sequence[float] | None,
    sampling_rate_hz: float,
    shaft_hz: float | None,
    speed_source: str,
    x_channel: int,
    y_channel: int,
) -> dict[str, Any]:
    """One capture -> one migration point. Never raises; bad captures come back invalid."""
    base: dict[str, Any] = {
        "upload_id": upload_id,
        "captured_at": captured_at,
        "sequence": sequence,
        "x_channel": x_channel,
        "y_channel": y_channel,
        "x_amplitude": 0.0,
        "y_amplitude": 0.0,
        "x_amplitude_g": 0.0,
        "y_amplitude_g": 0.0,
        "shaft_frequency_hz": shaft_hz,
        "shaft_rpm": (shaft_hz * 60.0) if shaft_hz else None,
        "speed_source": speed_source,
        "x_phase_deg": None,
        "y_phase_deg": None,
        "relative_phase_deg": None,
        "vector_amplitude": 0.0,
        "vh_ratio": None,
        "bin_hz": None,
        "frequency_resolution_hz": None,
        "quality": QUALITY_INVALID,
        "warnings": [],
        "ellipse": None,
    }

    if samples_x is None or samples_y is None:
        base["warnings"].append("Channel missing from this capture.")
        return base
    if not shaft_hz or not math.isfinite(shaft_hz) or shaft_hz <= 0:
        base["warnings"].append("No usable shaft-frequency estimate for this capture.")
        return base

    size = min(len(samples_x), len(samples_y))
    if size < 16:
        base["warnings"].append("Too few samples for a 1x estimate.")
        return base
    if len(samples_x) != len(samples_y):
        base["warnings"].append("X and Y lengths differed; truncated to the common length.")

    try:
        x_res = extract_one_x(samples_x[:size], sampling_rate_hz, shaft_hz)
        y_res = extract_one_x(samples_y[:size], sampling_rate_hz, shaft_hz)
    except Exception as exc:  # noqa: BLE001 - a bad capture must not sink the series
        base["warnings"].append(f"1x extraction failed: {exc}")
        return base

    bin_hz = x_res["bin_hz"]
    resolution = x_res["frequency_resolution_hz"]

    # Convert at the BIN frequency actually used, not the requested one.
    x_um = displacement_um_from_acceleration_g(x_res["amplitude_g"], bin_hz)
    y_um = displacement_um_from_acceleration_g(y_res["amplitude_g"], bin_hz)
    if not (math.isfinite(x_um) and math.isfinite(y_um)):
        base["warnings"].append("Non-finite displacement; capture excluded.")
        return base

    relative = wrap_degrees(y_res["phase_deg"] - x_res["phase_deg"])
    vector = math.hypot(x_um, y_um)

    quality = QUALITY_VALID
    warnings = list(base["warnings"])

    if resolution > 0 and abs(bin_hz - shaft_hz) > resolution * BIN_UNCERTAINTY_FRACTION:
        quality = QUALITY_UNCERTAIN
        warnings.append(
            f"1x frequency uncertain: estimate {shaft_hz:.2f} Hz sits {abs(bin_hz - shaft_hz):.2f} Hz "
            f"from the nearest bin ({bin_hz:.2f} Hz, resolution {resolution:.2f} Hz)."
        )
    if vector < LOW_SIGNAL_UM:
        quality = QUALITY_UNCERTAIN if quality == QUALITY_VALID else quality
        warnings.append("Low measured response — near the processing/noise floor.")

    base.update(
        {
            "x_amplitude": x_um,
            "y_amplitude": y_um,
            "x_amplitude_g": x_res["amplitude_g"],
            "y_amplitude_g": y_res["amplitude_g"],
            "x_phase_deg": x_res["phase_deg"],
            "y_phase_deg": y_res["phase_deg"],
            "relative_phase_deg": relative,
            "vector_amplitude": vector,
            "vh_ratio": (x_um / y_um) if y_um > 1e-30 else None,
            "bin_hz": bin_hz,
            "frequency_resolution_hz": resolution,
            "quality": quality,
            "warnings": warnings,
            "ellipse": response_ellipse(x_um, y_um, relative),
        }
    )
    return base


def summarise_migration(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Range and latest-capture figures for the axis bounds and the summary card."""
    valid = [p for p in points if p["quality"] != QUALITY_INVALID]
    if not valid:
        return {
            "valid_count": 0,
            "x_max": 0.0,
            "y_max": 0.0,
            "latest": None,
            "shaft_hz_min": None,
            "shaft_hz_max": None,
        }

    shaft = [p["shaft_frequency_hz"] for p in valid if p["shaft_frequency_hz"]]
    return {
        "valid_count": len(valid),
        "x_max": max(p["x_amplitude"] for p in valid),
        "y_max": max(p["y_amplitude"] for p in valid),
        "latest": valid[-1],
        "shaft_hz_min": min(shaft) if shaft else None,
        "shaft_hz_max": max(shaft) if shaft else None,
    }
