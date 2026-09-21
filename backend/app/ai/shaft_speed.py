"""How fast the shaft is actually turning — VIK-036 and VIK-037.

Every "order" in this platform is a frequency divided by the shaft speed.
3.57 orders names an outer-race defect; 2.00 names misalignment; 1.00 names
unbalance. Get the divisor wrong and every one of those names is wrong, by
exactly the same factor, everywhere, with nothing on screen to say so.

The estimator this replaces takes the tallest peak between 5 and 120 Hz. On
the test pump, measured against a nameplate of 1480 rpm:

    ch0  97.21 Hz   3.94x too high
    ch1 100.81 Hz   4.09x
    ch2  50.40 Hz   2.04x
    ch3  97.21 Hz   3.94x
    ch4  97.21 Hz   3.94x
    ch5  97.21 Hz   3.94x
    ch6  97.21 Hz   3.94x
    ch7  50.40 Hz   2.04x

Eight channels out of eight. Not one returned 24.67 Hz. The roadmap records
this as a problem on one channel; on real running data it is every channel.

The reason is not a bad threshold. **The tallest peak is not the shaft.** A
healthy machine's largest line is often 2x (misalignment), and on this pump
the 4x line near 98.7 Hz shares its bin with 2x mains at 100 Hz, so it wins
outright. No amount of tuning a peak-picker fixes that, because the
information needed to choose between 1x and 4x is not in the spectrum: both
are real peaks. It is on the nameplate.

So the order of authority here is: what was measured, then what the machine
is rated at, then what the spectrum suggests *within the speeds this machine
can actually run at*, and only then a bare guess -- which is reported as a
guess. `source` on the result says which one answered, because a wrong order
should be traceable to the record that caused it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

#: Widest band a shaft speed could be in, for the last-resort estimate.
#: Unchanged from the estimator this replaces, so the fallback behaves as
#: before rather than becoming a second thing to reason about.
ESTIMATE_MIN_HZ = 5.0
ESTIMATE_MAX_HZ = 120.0

#: How far a spectrum peak may sit from the nameplate speed and still be
#: called the same thing, as a fraction. Induction motors slip: a 1500 rpm
#: synchronous machine runs at 1440-1490 under load, which is up to 4% low,
#: and a nameplate usually quotes the loaded figure already. 8% covers slip
#: in both directions without reaching the next order.
NAMEPLATE_TOLERANCE = 0.08

#: Orders to test when asking "is this peak a multiple of the real speed?".
#: A peak-picker that lands on 4x is the observed failure, and 1/2 order
#: appears on looseness, so the list runs below 1 as well as above.
CANDIDATE_MULTIPLES = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)


@dataclass
class ShaftSpeed:
    """A shaft speed and how much it should be trusted."""
    hz: Optional[float] = None
    #: "measured" | "nameplate" | "nameplate_confirmed" | "spectrum_in_range"
    #: | "spectrum_unconstrained" | "none"
    source: str = "none"
    confidence: float = 0.0
    #: What the spectrum alone would have said. Kept even when the nameplate
    #: wins, because the disagreement is itself a finding: a machine running
    #: well away from its nameplate is either loaded oddly or slipping.
    spectrum_hz: Optional[float] = None
    note: Optional[str] = None

    @property
    def usable(self) -> bool:
        """True when an order computed from this means something."""
        return self.hz is not None and self.hz > 0 and self.confidence >= 0.5

    @property
    def rpm(self) -> Optional[float]:
        return self.hz * 60.0 if self.hz else None


def _peak_in_band(freqs: np.ndarray, spectrum: np.ndarray,
                  low_hz: float, high_hz: float) -> Optional[float]:
    mask = (freqs >= low_hz) & (freqs <= high_hz)
    if not np.any(mask):
        return None
    band_freqs, band_spec = freqs[mask], spectrum[mask]
    return float(band_freqs[int(np.argmax(band_spec))])


def _nearest_multiple(peak_hz: float, base_hz: float,
                      resolution_hz: float = 0.0) -> tuple[float, float, bool]:
    """Which multiple of base_hz the peak is closest to, its relative error,
    and whether that counts as a match.

    A match is judged against whichever is larger: the slip tolerance, or one
    line of the spectrum. A peak cannot be located better than one line, and
    at low orders that dominates -- half order on this pump is 12.33 Hz and
    the nearest line at 3.6 Hz spacing is 10.8, which is 12% away purely from
    quantisation. Judged on percentage alone, a real half-order line is
    rejected and the module falls back to a weaker answer for a reason that
    has nothing to do with the machine.
    """
    best_order, best_error, best_ok = 1.0, float("inf"), False
    for order in CANDIDATE_MULTIPLES:
        target = base_hz * order
        if target <= 0:
            continue
        absolute = abs(peak_hz - target)
        error = absolute / target
        if error < best_error:
            allowed = max(NAMEPLATE_TOLERANCE * target, resolution_hz)
            best_order, best_error, best_ok = order, error, absolute <= allowed
    return best_order, best_error, best_ok


def resolve_shaft_speed(
    freqs: Optional[np.ndarray] = None,
    spectrum: Optional[np.ndarray] = None,
    *,
    measured_rpm: Optional[float] = None,
    nameplate_rpm: Optional[float] = None,
    operating_rpm_min: Optional[float] = None,
    operating_rpm_max: Optional[float] = None,
) -> ShaftSpeed:
    """Decide the shaft speed for one capture.

    Everything is optional, and with nothing supplied the answer is an honest
    "unknown" rather than a number. A feature that needs a shaft speed reads
    `usable` and says so when it is false -- exactly as the unit path does --
    because an order against a guessed speed is a plausible wrong answer, and
    those get acted on.
    """
    result = ShaftSpeed()

    # What the spectrum thinks, always computed. It is the cross-check on the
    # nameplate even when it does not win.
    if freqs is not None and spectrum is not None and len(freqs) > 1:
        freqs = np.asarray(freqs, dtype=float)
        spectrum = np.asarray(spectrum, dtype=float)
        result.spectrum_hz = _peak_in_band(freqs, spectrum,
                                           ESTIMATE_MIN_HZ, ESTIMATE_MAX_HZ)

    # 1. A tacho reading. First-hand and current; nothing beats it.
    if measured_rpm and measured_rpm > 0:
        result.hz = float(measured_rpm) / 60.0
        result.source = "measured"
        result.confidence = 1.0
        result.note = f"Tacho reported {measured_rpm:g} rpm with this capture."
        return result

    # 2. The nameplate, checked against the spectrum where there is one.
    if nameplate_rpm and nameplate_rpm > 0:
        nameplate_hz = float(nameplate_rpm) / 60.0
        result.hz = nameplate_hz
        result.source = "nameplate"
        result.confidence = 0.75
        result.note = (
            f"No tacho, so the nameplate {nameplate_rpm:g} rpm is used. An "
            f"induction machine runs a few percent below its nameplate under "
            f"load, so orders may be out by that much."
        )

        if result.spectrum_hz:
            resolution_hz = (float(freqs[1] - freqs[0])
                             if freqs is not None and len(freqs) > 1 else 0.0)
            order, error, matched = _nearest_multiple(
                result.spectrum_hz, nameplate_hz, resolution_hz)
            if matched:
                if order == 1.0:
                    result.source = "nameplate_confirmed"
                    result.confidence = 0.95
                    result.note = (
                        f"The nameplate {nameplate_rpm:g} rpm and the largest "
                        f"line in the spectrum ({result.spectrum_hz:.2f} Hz) "
                        f"agree to within {error * 100:.1f}%."
                    )
                else:
                    # The important case, and the whole reason this module
                    # exists: the peak is real, and it is not 1x.
                    result.source = "nameplate_confirmed"
                    result.confidence = 0.9
                    result.note = (
                        f"The largest line is {result.spectrum_hz:.2f} Hz, "
                        f"which is {order:g}x the nameplate speed, not 1x. "
                        f"Taking the peak as the shaft rate would have put "
                        f"every order out by {order:g} times. The nameplate "
                        f"{nameplate_rpm:g} rpm is used."
                    )
            else:
                result.note = (
                    f"The largest line ({result.spectrum_hz:.2f} Hz) is not "
                    f"within {NAMEPLATE_TOLERANCE * 100:.0f}% of any common "
                    f"multiple of the nameplate {nameplate_rpm:g} rpm. The "
                    f"nameplate is still used, but either the machine is not "
                    f"running at its rated speed or this channel is dominated "
                    f"by something that is not the shaft."
                )
                result.confidence = 0.6
        return result

    # 3. The spectrum, but only inside speeds this machine can actually run at.
    #    A range narrows the search enough that the tallest line inside it is
    #    far more likely to be 1x than the tallest line in a 5-120 Hz band.
    if operating_rpm_min and operating_rpm_max and 0 < operating_rpm_min <= operating_rpm_max:
        low_hz, high_hz = operating_rpm_min / 60.0, operating_rpm_max / 60.0
        inside = (_peak_in_band(freqs, spectrum, low_hz, high_hz)
                  if freqs is not None and spectrum is not None else None)
        if inside:
            result.hz = inside
            result.source = "spectrum_in_range"
            result.confidence = 0.7
            result.note = (
                f"No nameplate, so the largest line between "
                f"{operating_rpm_min:g} and {operating_rpm_max:g} rpm "
                f"({low_hz:.2f}-{high_hz:.2f} Hz) is used."
            )
            return result

        # No line inside the range. Not a failure: a narrow operating band is
        # often narrower than the spectrum's line spacing. This pump runs
        # 1440-1500 rpm, a window of 1.0 Hz, against lines 3.6 Hz apart -- so
        # there is frequently no bin in it at all. Falling through to the
        # unconstrained peak here would discard real machine knowledge in
        # favour of the very guess that reads 4x on every channel, so the
        # middle of the declared range is used instead.
        result.hz = (low_hz + high_hz) / 2.0
        result.source = "operating_range"
        result.confidence = 0.65
        result.note = (
            f"No nameplate, and no spectrum line falls between "
            f"{operating_rpm_min:g} and {operating_rpm_max:g} rpm -- that "
            f"window is {high_hz - low_hz:.2f} Hz wide and the spectrum "
            f"cannot resolve inside it. The middle of the declared range is "
            f"used, which is machine knowledge rather than a guess at a peak."
        )
        return result

    # 4. The bare peak. Returned, because something is better than nothing for
    #    a plot axis -- but at a confidence that reads as not usable, so no
    #    engine computes an order from it without saying so.
    if result.spectrum_hz:
        result.hz = result.spectrum_hz
        result.source = "spectrum_unconstrained"
        result.confidence = 0.3
        result.note = (
            f"No tacho, no nameplate and no operating range, so this is the "
            f"largest line between {ESTIMATE_MIN_HZ:g} and {ESTIMATE_MAX_HZ:g} "
            f"Hz. On the test pump that method returned 2x or 4x the true "
            f"speed on all eight channels, so orders derived from it are not "
            f"trustworthy and are marked unusable."
        )
        return result

    result.note = (
        "No tacho, no nameplate, no operating range and no spectrum. The "
        "shaft speed is unknown, and every feature that needs one reports "
        "that rather than a number."
    )
    return result
