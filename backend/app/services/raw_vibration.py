"""
Raw 25 kSPS vibration snapshots: validate, store verbatim, read back in windows.

WHY THIS IS SEPARATE FROM /ingest/measurements
----------------------------------------------
That endpoint runs the full derived-artefact pipeline — five plots per channel plus
ten features over thirty-two segments per channel — on every burst. At 25 kSPS across
eight channels that is ~200,000 values and thousands of FFT/Hilbert passes per one-second
snapshot, which cannot keep pace with a device posting once a second. It is also exactly
what a raw path must not do.

So this module stores the samples EXACTLY as received and computes nothing: no FFT, RMS,
peak, crest, kurtosis, filtering, smoothing, normalisation, averaging, downsampling,
interpolation or resampling. Analysis happens later, on demand, from the stored raw data.

STORAGE
-------
Reuses `measurement_upload_data.parsed_data` (JSONB) — the representation the whole
project already uses for sample arrays — so no new table is required and every existing
reader keeps working. The uploaded CSV is retained byte-for-byte alongside it.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

from app.services.pdf_parser import parse_measurement_text

#: The acquisition rate this path is built for.
DEFAULT_SAMPLE_RATE_HZ = 25_000.0

#: 25 kSPS x 8 channels x 1 s = 200k values. Ten seconds is a sane ceiling for one POST.
MAX_SAMPLES_PER_SNAPSHOT = 250_000

#: Devices emit float32-ish timestamps; 40 us steps must not be rejected over 1e-9 noise.
TIMESTAMP_TOLERANCE_RATIO = 0.05

#: Default page size for dashboard reads — one second at 25 kSPS.
DEFAULT_WINDOW = 25_000
MAX_WINDOW = 50_000


#: Devices write their time column in whatever unit their clock uses, and the
#: unit is not declared anywhere in the CSV. A step of 0.02 is 20 ms if the
#: column is seconds and 20 us if it is milliseconds — a 1000x difference in
#: every frequency the analysis then reports. The declared sample rate is what
#: settles which reading is right.
TIMEBASE_UNITS: tuple[tuple[str, float], ...] = (
    ("s", 1.0),
    ("ms", 1e-3),
    ("us", 1e-6),
    ("ns", 1e-9),
)

#: A candidate unit is accepted only if it puts the implied rate within this
#: factor of the declared rate. The units are 1000x apart, so a tolerance this
#: wide cannot confuse two of them, while still absorbing a device whose clock
#: runs a per cent or two off nominal.
TIMEBASE_MATCH_TOLERANCE = 0.25

#: Above this, a normalised start time is an absolute epoch rather than an
#: elapsed offset — 1e6 s is about eleven days, far longer than any capture.
EPOCH_THRESHOLD_S = 1e6


def normalize_timebase(
    timestamps: Sequence[float],
    declared_rate_hz: float,
) -> tuple[list[float], dict[str, Any]]:
    """
    Return the time column as elapsed seconds from the start of the capture.

    Two corrections, both needed before a waveform can be plotted against time:

    1. **Unit.** The column may be seconds, milliseconds, microseconds or
       nanoseconds. The unit whose implied sample rate lands closest to
       `declared_rate_hz` wins; if none lands close enough the column is left in
       seconds and `resolved` is False, because guessing would be worse than
       reporting the mismatch.
    2. **Origin.** A device clock usually writes absolute epoch time, so the
       first sample carries a value like 1.787e12. Subtracting it makes the axis
       start at zero and read as elapsed time, which is what a time waveform
       needs. The absolute origin is preserved in `start_epoch_s` rather than
       discarded.

    Sample VALUES are never touched — only the time column. Already-normalised
    input (elapsed seconds starting at zero) passes through unchanged, so this
    is safe to apply more than once.
    """
    n = len(timestamps)
    if n < 2:
        return list(timestamps), {
            "unit": "s",
            "scale": 1.0,
            "resolved": False,
            "start_epoch_s": None,
            "observed_rate_hz": 0.0,
            "declared_rate_hz": float(declared_rate_hz),
        }

    span = float(timestamps[-1]) - float(timestamps[0])
    mean_step_raw = span / (n - 1)

    unit, scale, resolved = "s", 1.0, False
    if mean_step_raw > 0 and declared_rate_hz > 0:
        best_error = None
        for candidate_unit, candidate_scale in TIMEBASE_UNITS:
            implied_rate = 1.0 / (mean_step_raw * candidate_scale)
            # Compare as a ratio, not a difference: the candidates span twelve
            # orders of magnitude, so an absolute error would always pick the
            # largest unit.
            error = abs(math.log10(implied_rate / declared_rate_hz))
            if best_error is None or error < best_error:
                best_error, unit, scale = error, candidate_unit, candidate_scale
        resolved = best_error is not None and best_error <= abs(
            math.log10(1.0 + TIMEBASE_MATCH_TOLERANCE)
        )

    if not resolved:
        # Leave the column alone rather than rescaling on a weak guess. The
        # caller surfaces this as a warning.
        unit, scale = "s", 1.0

    origin = float(timestamps[0]) * scale
    normalized = [(float(t) * scale) - origin for t in timestamps]

    observed_rate = 1.0 / (mean_step_raw * scale) if mean_step_raw > 0 else 0.0

    return normalized, {
        "unit": unit,
        "scale": scale,
        "resolved": resolved,
        # Only meaningful when the device wrote wall-clock time.
        "start_epoch_s": origin if origin >= EPOCH_THRESHOLD_S else None,
        "observed_rate_hz": observed_rate,
        "declared_rate_hz": float(declared_rate_hz),
    }


class RawValidationError(ValueError):
    """Raised when an uploaded snapshot is not usable raw data."""


def parse_raw_csv(text: str, expected_channels: int | None = None) -> dict[str, Any]:
    """
    Parse `timestamp_,ch0..chN` into the project's standard parsed structure.

    Delegates to the existing CSV parser so the manual-upload path and this one cannot
    drift apart. Values are passed through untouched.
    """
    if not text or not text.strip():
        raise RawValidationError("CSV is empty")

    try:
        parsed = parse_measurement_text(text, expected_channels or 8)
    except ValueError as exc:
        raise RawValidationError(str(exc)) from exc

    channel_count = int(parsed["channel_count"])
    sample_count = int(parsed["sample_count"])

    if channel_count < 1:
        raise RawValidationError("No channel columns found — expected ch0, ch1, …")
    if expected_channels is not None and channel_count != expected_channels:
        raise RawValidationError(
            f"Expected exactly {expected_channels} channels but found {channel_count}"
        )
    if sample_count < 2:
        raise RawValidationError("At least two samples are required")
    if sample_count > MAX_SAMPLES_PER_SNAPSHOT:
        raise RawValidationError(
            f"{sample_count} samples exceeds the {MAX_SAMPLES_PER_SNAPSHOT} per-snapshot limit — "
            "split the capture into shorter windows"
        )

    for name, values in parsed["channels"].items():
        if len(values) != sample_count:
            raise RawValidationError(f"Channel {name} has {len(values)} samples, expected {sample_count}")
        for v in values:
            if not math.isfinite(v):
                raise RawValidationError(f"Channel {name} contains a non-finite value")

    return parsed


def inspect_timestamps(
    timestamps: Sequence[float],
    expected_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> dict[str, Any]:
    """
    Describe the time axis and check it against the expected acquisition rate.

    Returns the observed rate and step rather than only a pass/fail, so the caller can
    report what was actually received. Floating-point jitter well under one step is
    accepted; a genuinely different rate is not.
    """
    n = len(timestamps)
    if n < 2:
        raise RawValidationError("At least two samples are required to establish a time axis")

    for t in timestamps:
        if not math.isfinite(t):
            raise RawValidationError("Timestamp column contains a non-finite value")

    expected_step = 1.0 / expected_rate_hz
    steps = [timestamps[i + 1] - timestamps[i] for i in range(n - 1)]
    if any(s <= 0 for s in steps):
        raise RawValidationError("Timestamps must increase monotonically")

    mean_step = sum(steps) / len(steps)
    max_deviation = max(abs(s - mean_step) for s in steps)
    observed_rate = 1.0 / mean_step if mean_step > 0 else 0.0

    tolerance = expected_step * TIMESTAMP_TOLERANCE_RATIO
    rate_matches = abs(mean_step - expected_step) <= tolerance
    uniform = max_deviation <= tolerance

    return {
        "sample_count": n,
        "start_time": float(timestamps[0]),
        "end_time": float(timestamps[-1]),
        "duration_s": float(timestamps[-1] - timestamps[0]),
        "mean_step_s": float(mean_step),
        "max_step_deviation_s": float(max_deviation),
        "observed_rate_hz": float(observed_rate),
        "expected_rate_hz": float(expected_rate_hz),
        "rate_matches": bool(rate_matches),
        "uniform": bool(uniform),
    }


def window_samples(
    parsed: dict[str, Any],
    *,
    offset: int = 0,
    limit: int = DEFAULT_WINDOW,
    channels: Sequence[int] | None = None,
) -> dict[str, Any]:
    """
    Slice a stored snapshot for the dashboard.

    Windowing only — never decimation. The values returned inside the window are the
    stored values, so what the chart draws is what the device measured.
    """
    timestamps: list[float] = parsed.get("timestamps") or []
    stored: dict[str, list[float]] = parsed.get("channels") or {}
    total = len(timestamps)

    offset = max(0, min(offset, total))
    limit = max(1, min(limit, MAX_WINDOW))
    end = min(offset + limit, total)

    available = sorted(int(k[2:]) for k in stored if k.startswith("ch") and k[2:].isdigit())
    selected = [c for c in (channels if channels is not None else available) if c in available]
    if not selected:
        selected = available

    rows: list[dict[str, float]] = []
    for i in range(offset, end):
        row: dict[str, float] = {"timestamp_": float(timestamps[i])}
        for c in selected:
            row[f"ch{c}"] = float(stored[f"ch{c}"][i])
        rows.append(row)

    return {
        "samples": rows,
        "returned": len(rows),
        "offset": offset,
        "total_samples": total,
        "channels": selected,
        "has_more": end < total,
    }
