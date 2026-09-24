"""Thirteen frequency-domain measurements — VIK-019.

These take an already-computed spectrum rather than samples. That is the
ticket's "one spectrum per segment and fan out", enforced by the signature
instead of by discipline: a function handed `freqs` and `amplitudes` cannot
compute a second FFT even if someone wants it to.

What each one is for, in one line, because a feature nobody can interpret is a
column nobody reads:

  A shaft fault puts energy on exact multiples of running speed. A bearing
  fault puts it on a non-integer multiple, and modulates it. A worn or
  cavitating machine raises the whole floor rather than any one line. So the
  features split three ways: how much energy sits on harmonics, how much sits
  in sidebands around something, and how much is spread across everything.

The shaft speed has to come in from outside. Every "order" here is relative to
it, and an order computed against a wrong shaft speed is wrong by the same
factor everywhere -- which is what VIK-036 is about.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

#: Appended to FEATURE_CODES after the time-domain block. Order is a
#: positional contract; new codes go on the end.
FREQUENCY_FEATURE_CODES = [
    "dominant_frequency",
    "dominant_prominence",
    "harmonic_count",
    "harmonic_energy_ratio",
    "sideband_spacing",
    "sideband_energy_ratio",
    "spectral_centroid",
    "spectral_spread",
    "spectral_entropy",
    "broadband_noise",
    "haystack_score",
    "narrowband_ratio",
    "peak_drift",
]

#: How many shaft orders to look for when counting harmonics. Ten covers the
#: long families that looseness and severe misalignment produce without
#: reaching so high that noise starts counting as a harmonic.
MAX_HARMONIC = 10

#: A line counts as present at this multiple of the median line. Derived, not
#: tuned: for N lines of Rayleigh noise the largest sits about 3.4x the median
#: and reaches 4.7x in the worst of 200 simulated runs, so 6 is clear of
#: chance without demanding a dominant peak.
PRESENCE_RATIO = 6.0

#: Ignore everything below this many hertz. Integration drift and DC dominate
#: the bottom of every spectrum and would swamp a centroid.
DC_GUARD_HZ = 2.0

#: A sideband must sit at least this many lines away from its carrier.
#:
#: Every window leaks: a strong tone puts skirts on the bins either side of
#: it, symmetrically, which is exactly the shape a sideband search looks for.
#: Without this the search returns one line of spacing on every signature
#: with a strong peak -- measured, it reported 3 Hz (one bin) for six of the
#: eight harness signatures, including both healthy ones. Three lines clears
#: a Hann window's main lobe, which is four bins wide.
MIN_SIDEBAND_LINES = 3

#: Modulation produces pairs at the modulating frequency and at its
#: multiples, and the fundamental is NOT reliably the strongest -- on a
#: bearing the second pair routinely exceeds the first. The fundamental is
#: therefore identified by the family being CONTIGUOUS: pairs at 1x, 2x ...
#: up to the strongest one, with none missing. See _family_fundamental.

#: A sideband pair must stand this far above the floor -- higher than the bar
#: for a line being merely present. Sidebands are read as evidence of a
#: specific mechanism, so a pair that is barely distinguishable from noise
#: should name nothing. At the general 6x bar the looseness signature
#: reported a 0.38X spacing, which corresponds to no mechanism and came from
#: window skirt.
SIDEBAND_PRESENCE_RATIO = 12.0

#: How far a sideband must rise above the background a few lines either side.
#: Distinguishes a real line from window skirt without demanding a strict
#: local maximum, which a sideband on a resonance slope can never be.
SIDEBAND_LOCAL_RISE = 2.0


def _safe_divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if abs(denominator) > 1e-30 else 0.0


def _nearest_index(freqs: np.ndarray, target_hz: float) -> int:
    return int(np.argmin(np.abs(freqs - target_hz)))


def _stands_above_its_surroundings(amps: np.ndarray, idx: int,
                                   gap: int = 2, reach: int = 5) -> bool:
    """True when this line rises above the background either side of it.

    Not a strict local maximum. A bearing sideband sits on the SLOPE of the
    resonance hump it modulates, so one of its immediate neighbours is always
    higher and a strict test rejects it -- measured, that turned a correct
    87.5 Hz BPFO spacing into 178 Hz, which is twice BPFO and names nothing.

    Window skirt, on the other hand, is part of the tone beside it and does
    not rise above its own surroundings. So the comparison skips the
    immediately adjacent bins (the skirt itself) and looks at the background a
    few lines out on both sides.
    """
    lo_start, lo_end = idx - gap - reach, idx - gap
    hi_start, hi_end = idx + gap + 1, idx + gap + reach + 1
    if lo_start < 0 or hi_end > amps.size:
        return False
    background = float(np.mean(np.concatenate([
        amps[lo_start:lo_end], amps[hi_start:hi_end],
    ])))
    return bool(amps[idx] > SIDEBAND_LOCAL_RISE * background)


def _peak_amplitude_at(freqs: np.ndarray, amps: np.ndarray, target_hz: float,
                       tolerance_hz: float) -> float:
    """Amplitude at one frequency, but only if a peak sits there."""
    if target_hz <= 0 or freqs.size == 0:
        return 0.0
    idx = _nearest_index(freqs, target_hz)
    if abs(float(freqs[idx]) - target_hz) > tolerance_hz:
        return 0.0
    return (float(amps[idx])
            if _stands_above_its_surroundings(amps, idx) else 0.0)


def _amplitude_at(freqs: np.ndarray, amps: np.ndarray, target_hz: float,
                  tolerance_hz: float) -> float:
    """Amplitude at one frequency, or 0.0 if no line is close enough.

    The tolerance is the line spacing: two frequencies closer together than
    that are the same measurement, and pretending otherwise invents precision
    the transform does not have.
    """
    if target_hz <= 0 or freqs.size == 0:
        return 0.0
    idx = _nearest_index(freqs, target_hz)
    if abs(float(freqs[idx]) - target_hz) > tolerance_hz:
        return 0.0
    return float(amps[idx])


def extract_frequency_features(
    freqs: np.ndarray,
    amplitudes: np.ndarray,
    *,
    shaft_hz: Optional[float] = None,
    previous_dominant_hz: Optional[float] = None,
) -> dict[str, dict[str, Any]]:
    """Thirteen features from one spectrum.

    `previous_dominant_hz` is the same channel's dominant frequency in the
    previous capture. Peak drift cannot be computed from a single spectrum --
    drift is a change between two -- so it reports 0.0 and says so rather than
    inventing a comparison.
    """
    freqs = np.asarray(freqs, dtype=np.float64)
    amplitudes = np.asarray(amplitudes, dtype=np.float64)

    usable = freqs > DC_GUARD_HZ
    f = freqs[usable]
    a = amplitudes[usable]
    if f.size < 4:
        return _empty(shaft_hz)

    resolution_hz = float(f[1] - f[0]) if f.size > 1 else 1.0
    tolerance_hz = max(resolution_hz, 1.0)
    median_line = float(np.median(a)) or 1e-30
    total_energy = float(np.sum(a ** 2)) or 1e-30

    # --- the loudest line, and whether it means anything --------------
    peak_idx = int(np.argmax(a))
    dominant_frequency = float(f[peak_idx])
    dominant_prominence = float(a[peak_idx]) / median_line

    # --- harmonics: energy on exact multiples of shaft speed ----------
    # A shaft-related fault -- unbalance, misalignment, looseness -- puts its
    # energy on integer orders. A bearing fault does not, because its rate is
    # not an integer multiple of anything.
    harmonic_count = 0
    harmonic_energy = 0.0
    if shaft_hz and shaft_hz > 0:
        for order in range(1, MAX_HARMONIC + 1):
            amplitude = _amplitude_at(f, a, order * shaft_hz, tolerance_hz)
            if amplitude > PRESENCE_RATIO * median_line:
                harmonic_count += 1
                harmonic_energy += amplitude ** 2
    harmonic_energy_ratio = _safe_divide(harmonic_energy, total_energy)

    # --- sidebands: what the dominant line is modulated by ------------
    # Modulation puts a pair of lines either side of a carrier, spaced by the
    # modulating frequency. The spacing names the cause: shaft rate means the
    # defect passes through the load zone once a revolution.
    sideband_spacing, sideband_energy = _find_sidebands(
        f, a, dominant_frequency, median_line, tolerance_hz, shaft_hz,
        resolution_hz,
    )
    sideband_energy_ratio = _safe_divide(sideband_energy, total_energy)

    # --- shape of the whole spectrum ----------------------------------
    power = a ** 2
    power_sum = float(np.sum(power)) or 1e-30
    probability = power / power_sum

    # Centroid: the spectrum's centre of mass. Rises as a machine develops
    # high-frequency content, which is one of the earliest bearing signs.
    spectral_centroid = float(np.sum(f * probability))
    spectral_spread = float(np.sqrt(np.sum(((f - spectral_centroid) ** 2) * probability)))

    # Entropy: how evenly the energy is spread, 0 (one line) to 1 (flat).
    # A tonal fault lowers it; a broadband one raises it. This is what
    # separates "something is ringing" from "everything got noisier".
    nonzero = probability[probability > 0]
    entropy = float(-np.sum(nonzero * np.log(nonzero)))
    spectral_entropy = _safe_divide(entropy, float(np.log(nonzero.size or 1)))

    # --- how much is floor rather than lines --------------------------
    broadband_noise = median_line
    # Haystack: a raised, rounded hump rather than discrete lines. Late-stage
    # bearing damage and cavitation both produce it, as the individual
    # impacts stop being distinguishable.
    mean_line = float(np.mean(a))
    haystack_score = _safe_divide(median_line, mean_line)
    # Narrowband: the share of energy in lines that stand out at all. High
    # means discrete tones, low means a floor.
    prominent = a[a > PRESENCE_RATIO * median_line]
    narrowband_ratio = _safe_divide(float(np.sum(prominent ** 2)), total_energy)

    # --- drift, which needs two captures ------------------------------
    if previous_dominant_hz and previous_dominant_hz > 0:
        peak_drift = _safe_divide(
            dominant_frequency - previous_dominant_hz, previous_dominant_hz
        )
        drift_basis = f"against {previous_dominant_hz:g} Hz in the previous capture"
    else:
        peak_drift = 0.0
        drift_basis = (
            "no previous capture supplied, so no drift could be measured -- "
            "0.0 here means unknown, not unchanged"
        )

    return {
        "dominant_frequency": {
            "value": dominant_frequency, "unit": "Hz",
            "metadata": {"order": (_safe_divide(dominant_frequency, shaft_hz)
                                   if shaft_hz else None)},
        },
        "dominant_prominence": {
            "value": dominant_prominence, "unit": "dimensionless",
            "metadata": {"basis": "peak amplitude / median line",
                         "note": "below about 6 there is no tone, only the "
                                 "tallest part of the noise"},
        },
        "harmonic_count": {
            "value": float(harmonic_count), "unit": "count",
            "metadata": {"searched_orders": MAX_HARMONIC, "shaft_hz": shaft_hz},
        },
        "harmonic_energy_ratio": {
            "value": harmonic_energy_ratio, "unit": "fraction",
            "metadata": {"shaft_hz": shaft_hz},
        },
        "sideband_spacing": {
            "value": sideband_spacing, "unit": "Hz",
            "metadata": {"carrier_hz": dominant_frequency,
                         "order": (_safe_divide(sideband_spacing, shaft_hz)
                                   if shaft_hz else None)},
        },
        "sideband_energy_ratio": {
            "value": sideband_energy_ratio, "unit": "fraction", "metadata": {},
        },
        "spectral_centroid": {"value": spectral_centroid, "unit": "Hz", "metadata": {}},
        "spectral_spread": {"value": spectral_spread, "unit": "Hz", "metadata": {}},
        "spectral_entropy": {
            "value": spectral_entropy, "unit": "dimensionless",
            "metadata": {"scale": "0 = one line, 1 = flat"},
        },
        "broadband_noise": {
            "value": broadband_noise, "unit": "scaled_eng",
            "metadata": {"basis": "median line amplitude"},
        },
        "haystack_score": {
            "value": haystack_score, "unit": "dimensionless",
            "metadata": {"basis": "median / mean line; near 1 means a floor "
                                  "rather than discrete lines"},
        },
        "narrowband_ratio": {
            "value": narrowband_ratio, "unit": "fraction",
            "metadata": {"threshold_ratio": PRESENCE_RATIO},
        },
        "peak_drift": {
            "value": peak_drift, "unit": "fraction",
            "metadata": {"basis": drift_basis},
        },
    }


def _find_sidebands(f, a, carrier_hz, median_line, tolerance_hz, shaft_hz,
                    resolution_hz):
    """Spacing of the strongest symmetric pair around the carrier, and its energy.

    Symmetric on purpose. A single line near the carrier is just another line;
    modulation always produces a matched pair, one above and one below, and
    requiring both is what stops a neighbouring unrelated tone being read as
    a sideband.
    """
    if carrier_hz <= 0:
        return 0.0, 0.0

    # Shaft rate first if known -- it is the spacing that actually means
    # something -- then a general search for the strongest pair.
    candidates = []
    if shaft_hz and shaft_hz > 0:
        candidates.append(shaft_hz)
    # Every line spacing, not an arbitrary grid over the range.
    #
    # Stepping in 40 even increments cannot land on the actual spacing: it
    # reported 95.2 Hz for a BPFO of 89.25 and 21.9 Hz for a shaft rate of 25,
    # both off by the grid rather than by the signal. A sideband can only sit
    # on a line, so the candidates are the lines.
    minimum = MIN_SIDEBAND_LINES * tolerance_hz
    span = min(carrier_hz * 0.5, 500.0)
    if span > minimum:
        candidates.extend(np.arange(minimum, span, resolution_hz).tolist())

    minimum_spacing = MIN_SIDEBAND_LINES * tolerance_hz
    found: list[tuple[float, float]] = []
    for spacing in candidates:
        if spacing < minimum_spacing:
            # Includes a shaft rate that happens to be inside the skirt: at a
            # slow shaft on a coarse spectrum, 1X sidebands are simply not
            # resolvable, and reporting them anyway would be invention.
            continue
        lower = _peak_amplitude_at(f, a, carrier_hz - spacing, tolerance_hz)
        upper = _peak_amplitude_at(f, a, carrier_hz + spacing, tolerance_hz)
        floor = SIDEBAND_PRESENCE_RATIO * median_line
        if lower <= floor or upper <= floor:
            continue
        found.append((float(spacing), lower ** 2 + upper ** 2))

    if not found:
        return 0.0, 0.0

    # The FUNDAMENTAL spacing, not the strongest pair.
    #
    # Modulation produces a family: pairs at the modulating frequency and at
    # its multiples. Any of them can be the loudest, and taking the loudest
    # reports a multiple. Measured on the outer-race signature that returned
    # 181 Hz -- twice BPFO -- which reads as order 7.24 and matches no bearing
    # anyone would recognise, while the fundamental 89 Hz is 3.57X and names
    # the defect outright.
    #
    # An earlier version chose the smallest spacing whose pair carried at
    # least a quarter of the strongest pair's energy. That fails in exactly
    # the case it was written for: where a second-order pair is much louder
    # than the fundamental -- four times, in the constructed test -- the
    # fundamental falls below the fraction and is discarded, and the function
    # reports the multiple again.
    #
    # Contiguity is the property that actually identifies a fundamental. If
    # the spacing is s, there are pairs at s, 2s, ... up to the strongest one.
    # No relative-energy assumption is needed.
    distinct = _collapse_to_distinct_spacings(found, tolerance_hz)
    strongest_spacing = max(distinct, key=lambda pair: pair[1])[0]
    best_spacing = _family_fundamental(
        [s for s, _ in distinct], strongest_spacing, tolerance_hz
    )

    # There used to be a "snap to shaft rate when within one line of it" step
    # here, added when the family rule read 21.88 Hz for a 25 Hz shaft. It is
    # gone because it can no longer fire, and a branch that cannot fire is a
    # branch nobody maintains: the shaft rate is the first candidate searched,
    # so an exact shaft-rate spacing is already in `found` whether or not it
    # lands on a line, and the local-rise guard now rejects the skirt pair one
    # bin in that produced the 21.88 in the first place. Mutation testing
    # confirmed it: deleting the snap changed no measured result.

    best_energy = max(e for s, e in found
                      if abs(s - best_spacing) <= tolerance_hz)
    return best_spacing, best_energy


def _collapse_to_distinct_spacings(found: list[tuple[float, float]],
                                   tolerance_hz: float) -> list[tuple[float, float]]:
    """One entry per real spacing, keeping the strongest pair of each.

    Two spacings closer together than the line spacing are the same
    measurement. They both turn up because a strong sideband leaks onto the
    bins beside it, and both of those clear the amplitude floor -- so the
    outer-race family arrives as 87.5 AND 90.62, 175 AND 178.12 AND 181.25,
    and so on. Left uncollapsed, a skirt bin can win the search: on the
    constructed two-pair spectrum the answer came back as 96.875 for a
    modulating frequency of 100, off by exactly one line and traceable to
    nothing in the machine.
    """
    if not found:
        return []
    clusters: list[list[tuple[float, float]]] = [[]]
    previous = None
    for spacing, energy in sorted(found):
        if previous is not None and spacing - previous > tolerance_hz:
            clusters.append([])
        clusters[-1].append((spacing, energy))
        previous = spacing
    return [max(group, key=lambda pair: pair[1]) for group in clusters if group]


def _family_fundamental(spacings: list[float], strongest: float,
                        tolerance_hz: float) -> float:
    """The smallest spacing the strongest pair is a contiguous multiple of.

    Walks candidates from smallest up and takes the first where the strongest
    spacing is an integer multiple of it AND every intermediate multiple has
    a pair of its own.

    Each member is compared by the fundamental it implies -- the member
    divided by its order -- rather than by its distance from the multiple.
    The distance grows with the order and the implied fundamental does not:
    every line is rounded to its own nearest bin, so the eighth member of a
    40 Hz family can sit six hertz from 8 x 40 while implying a fundamental
    within one hertz of 40. Measured against the multiple, that family's
    fundamental is rejected and a member of it is reported instead.

    There is deliberately no cap on the order. An earlier version stopped at
    six, which breaks the same case from the other side: given an eight-member
    family whose loudest pair is the eighth, the cap rejects the fundamental
    and returns twice it at order four -- a multiple, reported as the
    spacing, which is the failure this function exists to prevent.
    Contiguity is the guard. A spurious small divisor of a large spacing
    almost never has every intermediate member, and one that does is a real
    comb whose fundamental it is.

    The trailing return is unreachable rather than a policy: `strongest` is
    itself one of `spacings` and always satisfies the test at order 1.
    """
    def implies(candidate: float, step: int) -> bool:
        """Is there a pair whose order-`step` reading agrees with `candidate`?"""
        return any(abs(s / step - candidate) <= tolerance_hz for s in spacings)

    for candidate in sorted(spacings):
        if candidate <= 0:
            continue
        order = int(round(strongest / candidate))
        if order < 1 or abs(strongest / order - candidate) > tolerance_hz:
            continue
        if all(implies(candidate, step) for step in range(1, order + 1)):
            return float(candidate)
    return float(strongest)


def _empty(shaft_hz: Optional[float]) -> dict[str, dict[str, Any]]:
    """A spectrum too short to describe. Zeros with a reason, never omissions:
    a missing key breaks a caller, a zero with a note does not."""
    note = {"note": "spectrum too short to measure"}
    units = {
        "dominant_frequency": "Hz", "dominant_prominence": "dimensionless",
        "harmonic_count": "count", "harmonic_energy_ratio": "fraction",
        "sideband_spacing": "Hz", "sideband_energy_ratio": "fraction",
        "spectral_centroid": "Hz", "spectral_spread": "Hz",
        "spectral_entropy": "dimensionless", "broadband_noise": "scaled_eng",
        "haystack_score": "dimensionless", "narrowband_ratio": "fraction",
        "peak_drift": "fraction",
    }
    return {code: {"value": 0.0, "unit": units[code], "metadata": dict(note)}
            for code in FREQUENCY_FEATURE_CODES}
