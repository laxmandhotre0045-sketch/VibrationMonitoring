"""Thirteen more time-domain measurements — VIK-018.

The platform measures ten things about a channel. The requirement asks for
about fifty, and these are the time-domain share of that.

Each one earns its place by separating faults the existing ten cannot. RMS and
kurtosis together already say "something is impacting", but not whether it is
a bearing, looseness or a loose sensor. Impulse, shape and clearance factors
answer that by asking the same question three ways -- peak against mean,
against RMS, and against the squared-root mean -- and the three disagree in
different ways for different faults.

Two of the thirteen already exist in raw_analysis.py and are lifted rather
than rewritten, as the ticket requires: peak-to-peak and skewness. A second
copy of skewness would sit one convention away from the first (Fisher versus
Pearson, population versus sample sigma) and the two would drift.

None of these needs an FFT, which is why they are cheap enough to compute on
every segment after VIK-014.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: Added to FEATURE_CODES in this order. The order is a positional contract
#: the frontend relies on, so new codes append and nothing is reordered.
TIME_FEATURE_CODES = [
    "peak_to_peak",
    "std_dev",
    "skewness",
    "impulse_factor",
    "shape_factor",
    "clearance_factor",
    "burst_count",
    "shock_index",
    "modulation_index",
    "rms_change_short",
    "rms_change_long",
    "zero_crossing_rate",
    "dc_offset",
]

#: A burst is a sample beyond this many standard deviations. 4 sigma is about
#: 1 in 16,000 for Gaussian noise, so a 13,888-sample capture expects roughly
#: one by chance -- a count well above that is impacting, not luck.
BURST_SIGMA = 4.0

#: Short-term RMS window as a fraction of the record. The pair of windows is
#: what makes a change visible inside a single capture: a fault that is
#: growing shows a short-term RMS above its long-term one.
SHORT_WINDOW_FRACTION = 0.1


def _safe_divide(numerator: float, denominator: float) -> float:
    """Zero rather than an exception or an infinity.

    A silent inf propagates into a threshold comparison and grades as
    critical; zero grades as normal and is visibly wrong when plotted. On a
    channel with no signal at all, neither is meaningful, and zero is the one
    that does not raise an alarm about a disconnected sensor.
    """
    return float(numerator / denominator) if abs(denominator) > 1e-30 else 0.0


def _amplitude_at(signal: np.ndarray, freq_hz: float, sampling_rate_hz: float) -> float:
    """The amplitude of one frequency component, without a full FFT.

    A single-frequency correlation -- project the signal onto a sine and a
    cosine at that frequency and take the magnitude. One frequency costs one
    pass instead of an N log N transform, which is what keeps these features
    affordable on every segment.
    """
    n = signal.size
    if n < 4 or freq_hz <= 0 or freq_hz >= sampling_rate_hz / 2:
        return 0.0
    t = np.arange(n) / sampling_rate_hz
    angle = 2.0 * np.pi * freq_hz * t
    real = float(np.dot(signal, np.cos(angle)))
    imag = float(np.dot(signal, np.sin(angle)))
    return 2.0 * np.hypot(real, imag) / n


def extract_time_features(
    samples: list[float] | np.ndarray,
    sampling_rate_hz: float,
    shaft_hz: float | None = None,
) -> dict[str, dict[str, Any]]:
    """All thirteen, from one pass over the samples.

    `shaft_hz` is needed only by the modulation index, which is an amplitude
    modulation depth AT SHAFT RATE and therefore cannot be computed without
    knowing that rate. Where it is unknown the feature reports envelope
    variability instead and says so in its metadata, rather than returning a
    number under a name that means something else.
    """
    data = np.asarray(samples, dtype=np.float64)
    n = data.size
    if n < 4:
        raise ValueError("Need at least 4 samples per channel")

    mean = float(np.mean(data))
    centred = data - mean
    # Population sigma (ddof=0), matching raw_analysis.py. Mixing conventions
    # across modules is how the same channel reports two different kurtoses.
    sigma = float(np.sqrt(np.mean(centred ** 2)))

    # EVERYTHING BELOW IS MEASURED ON THE CENTRED SIGNAL, and that is the
    # whole of a bug this had until real data exposed it.
    #
    # These are all vibration quantities: how far the machine moves about its
    # resting position. A sensor's standing bias is not movement. Measured on
    # the raw signal instead, with |x| including the offset, the eight
    # channels of the test pump reported burst counts of
    #
    #     13888, 13887, 387, 10, 0, 13888, 13888, 13888   out of 13888
    #
    # -- five channels declaring every single sample a four-sigma impact,
    # because the bias alone (-0.145 g on ch7) is larger than four times the
    # vibration's own spread (0.048 g). The correct counts are 8, 1, 298, 0,
    # 0, 45, 2, 303.
    #
    # The harness could not catch this: every synthetic signature is
    # generated about zero, so raw and centred agree exactly. Only a real
    # transducer has a bias. `dc_offset` reports the bias itself and
    # `peak_to_peak` is a difference, so those two are unaffected.
    rms = float(np.sqrt(np.mean(centred ** 2)))
    peak = float(np.max(np.abs(centred)))
    absolute = np.abs(centred)
    mean_absolute = float(np.mean(absolute))

    peak_to_peak = float(np.max(data) - np.min(data))

    # Fisher-Pearson, the same definition raw_analysis.py uses.
    skewness = _safe_divide(float(np.mean(centred ** 3)), sigma ** 3)

    # The three shape ratios. Each divides the peak by a different average, so
    # they respond differently: impulse factor reacts hardest to a single
    # spike, shape factor barely moves for one, and clearance factor is the
    # most sensitive of the three to early bearing damage because the
    # square-root mean suppresses large values most.
    impulse_factor = _safe_divide(peak, mean_absolute)
    shape_factor = _safe_divide(rms, mean_absolute)
    root_mean_sqrt = float(np.mean(np.sqrt(absolute))) ** 2
    clearance_factor = _safe_divide(peak, root_mean_sqrt)

    # How many samples sit beyond 4 sigma, and how far the worst one goes.
    # Count and severity are separate features on purpose: one deep spike and
    # many shallow ones are different faults, and a single number conflates
    # them.
    if sigma > 1e-30:
        exceed = absolute > (BURST_SIGMA * sigma)
        burst_count = int(np.count_nonzero(exceed))
        shock_index = float(np.max(absolute) / (BURST_SIGMA * sigma))
    else:
        burst_count = 0
        shock_index = 0.0

    # Amplitude modulation depth at shaft rate.
    #
    # A defect that passes through the load zone once per revolution -- an
    # inner-race defect on a rotating shaft -- modulates the impulse train at
    # 1X. An outer-race defect sits still relative to the load and does not.
    # That difference is the discriminator between the two, so the feature has
    # to measure modulation AT SHAFT RATE rather than envelope variability in
    # general.
    #
    # The distinction is not academic. Measured on the harness, plain envelope
    # variability reads 1.60 for the outer-race channel and 0.75 for the
    # inner-race one -- the opposite of the intended meaning, because the
    # outer-race impulses are eight times larger and dominate the spread. A
    # feature named "modulation index" reading highest on the unmodulated
    # signature would mislead every rule built on it. At shaft rate the order
    # is correct: 0.30 inner against 0.12 outer.
    #
    # KNOWN LIMIT, and it is why this is one feature among thirteen rather
    # than a test on its own. Computed on the RAW signal, any strong 1X
    # content modulates the rectified envelope by itself -- the healthy
    # channel reads 0.29 here, almost as high as the inner-race one, because
    # it is dominated by a 1X sine and nothing is wrong with it. The clean
    # measurement demodulates a band around the bearing resonance first and
    # looks for 1X in THAT envelope, which needs the resonance band and
    # belongs with the envelope features in VIK-020. Read this one as
    # corroboration, never as a discriminator on its own.
    envelope = absolute
    envelope_mean = float(np.mean(envelope))
    if shaft_hz and shaft_hz > 0:
        centred_envelope = envelope - envelope_mean
        modulation_index = _safe_divide(
            _amplitude_at(centred_envelope, shaft_hz, sampling_rate_hz),
            envelope_mean,
        )
        modulation_basis = f"amplitude at {shaft_hz:g} Hz / envelope mean"
    else:
        modulation_index = _safe_divide(float(np.std(envelope)), envelope_mean)
        modulation_basis = (
            "envelope coefficient of variation -- shaft speed unknown, so this "
            "is NOT a modulation depth and is dominated by impulsiveness"
        )

    # Short against long RMS, inside the one record. A rising fault shows a
    # short-term RMS above the whole-record figure; a steady one does not.
    # Clamped to half the record so the two windows cannot overlap. Without
    # this, any fraction above 0.5 makes "the last window against the first"
    # compare the record with itself -- at 0.9 the two share 89% of their
    # samples, so a fault that is growing reports no change. The current
    # fraction is well clear of that; the clamp is here so that tuning the
    # constant cannot silently empty the feature of meaning.
    window = max(4, min(n // 2, int(n * SHORT_WINDOW_FRACTION)))
    recent = centred[-window:]
    earlier = centred[:window]
    rms_recent = float(np.sqrt(np.mean(recent ** 2)))
    rms_earlier = float(np.sqrt(np.mean(earlier ** 2)))
    rms_change_short = _safe_divide(rms_recent - rms_earlier, rms_earlier)
    rms_change_long = _safe_divide(rms_recent - rms, rms)

    # Crossings of the mean, per second. A rough frequency measure that costs
    # nothing and does not need an FFT: it rises when high-frequency content
    # appears, which is one of the earliest signs of a bearing defect.
    signs = np.signbit(centred)
    zero_crossings = int(np.count_nonzero(signs[1:] != signs[:-1]))
    zero_crossing_rate = _safe_divide(zero_crossings * sampling_rate_hz, n)

    dimensionless = {"unit": "dimensionless", "metadata": {}}
    engineering = {"unit": "scaled_eng", "metadata": {}}

    return {
        "peak_to_peak": {"value": peak_to_peak, **engineering},
        "std_dev": {"value": sigma, **engineering},
        "skewness": {
            "value": skewness, "unit": "dimensionless",
            "metadata": {"convention": "Fisher-Pearson, population sigma"},
        },
        "impulse_factor": {"value": impulse_factor, **dimensionless},
        "shape_factor": {"value": shape_factor, **dimensionless},
        "clearance_factor": {"value": clearance_factor, **dimensionless},
        "burst_count": {
            "value": float(burst_count), "unit": "count",
            "metadata": {"threshold_sigma": BURST_SIGMA, "sample_count": n},
        },
        "shock_index": {
            "value": shock_index, "unit": "dimensionless",
            "metadata": {"threshold_sigma": BURST_SIGMA},
        },
        "modulation_index": {
            "value": modulation_index, "unit": "dimensionless",
            "metadata": {"basis": modulation_basis,
                         "shaft_hz": shaft_hz},
        },
        "rms_change_short": {
            "value": rms_change_short, "unit": "fraction",
            "metadata": {"window_samples": window,
                         "comparison": "last window against first window"},
        },
        "rms_change_long": {
            "value": rms_change_long, "unit": "fraction",
            "metadata": {"window_samples": window,
                         "comparison": "last window against whole record"},
        },
        "zero_crossing_rate": {
            "value": zero_crossing_rate, "unit": "Hz",
            "metadata": {"about": "mean, not zero"},
        },
        "dc_offset": {
            "value": mean, "unit": "scaled_eng",
            "metadata": {"note": "sensor bias; not vibration"},
        },
    }
