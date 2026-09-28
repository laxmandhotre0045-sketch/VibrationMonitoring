"""What the signal is doing, before anything decides what it means — VIK-051.

A fault name is a conclusion. A symptom is an observation: a harmonic
series is present, there are sidebands 24.7 Hz either side of this peak,
energy sits in the bearing band, the waveform is impacting. The rules turn
symptoms into names, and this is the layer that produces them.

**Each symptom carries the evidence that triggered it, not a flag.** The
ticket is explicit and it is the whole value of the phase: "harmonic series
present: true" is unarguable in the worst sense -- nobody can check it,
nobody can overrule it, and when it is wrong there is no way to find out
why. "Six harmonics of 24.7 Hz, the fourth strongest at 12% of 1x" is a
statement an analyst can look at the spectrum and disagree with.

**Symptoms are separate from the rule table on purpose.** The rules in
`vibcore.signatures` ask "is there a peak at this order", which is the right
question for naming a fault and the wrong one for describing a signal. A
harmonic series is a property of a spectrum whatever machine produced it,
and recording it separately means a capture that matches no rule still has
something said about it -- which, on a machine whose spectrum cannot resolve
its own bearing frequencies, is the only thing there is to say.

Nothing here decides severity or names a fault. It observes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

from vibcore.signatures import SpectralPeak

#: How close an order must sit to a whole number to count as a harmonic.
#: Matches the engine's own synchronous tolerance, so a peak the rules call
#: synchronous is one the symptoms call a harmonic.
HARMONIC_TOLERANCE = 0.05

#: Harmonics needed before a series is worth reporting. Two is a peak and
#: its octave, which almost every rotating machine has; four is a series.
MIN_HARMONICS = 4

#: Highest order that can count as a harmonic of running speed.
#:
#: Without a ceiling this reported "1x, 5x, 713x, 877x" on a real capture.
#: The tolerance is a fraction of an order, so at 713x it spans 1.3 Hz out
#: of 18 kHz and essentially any peak up there satisfies it by chance. Past
#: about twenty orders "harmonic of running speed" also stops being a
#: diagnostic claim -- mesh frequencies and bearing bands live up there and
#: have their own rules.
MAX_HARMONIC_ORDER = 20

#: How evenly spaced two gaps must be to count as the same sideband family,
#: as a fraction of the spacing. Sidebands come from modulation, so they sit
#: at a genuinely constant interval -- but a 3.6 Hz bin on this gateway is a
#: coarse ruler, and a tolerance tighter than the bin finds nothing.
SIDEBAND_TOLERANCE = 0.15

#: Sidebands needed to call it a family. One pair either side of a carrier#: How many steps of the sideband spacing must fit below the carrier.
#:
#: A carrier only three steps up cannot be told from the third harmonic of
#: the spacing, because the downward walk that separates modulation from a
#: harmonic series has almost no room to run. Gear mesh, blade pass and
#: bearing frequencies -- the carriers that actually get modulated -- all sit
#: far higher than this.
MIN_CARRIER_DEPTH = 6


#: is a family; a single flanking peak is a peak.
MIN_SIDEBANDS = 2

#: How far past its threshold one measure must go to count on its own.
#:
#: Crest factor and kurtosis measure the same physical property from
#: different directions, so on a genuinely impacting signal both rise. The
#: first version fired when either did, and 4.0 crest is a low enough bar
#: that ordinary captures clear it -- the symptom appeared on every channel
#: examined, including a pure unbalance signature, which makes it worth
#: nothing to whoever reads it.
#:
#: Requiring both instead would miss a real impact whose kurtosis sits just
#: under its threshold. So: both together, or one clearly past the line.
IMPACTING_STRONG_MULTIPLE = 1.5

#: Crest factor above which a waveform is impacting rather than vibrating.
#: A sinusoid is 1.41; bearing and gear defects strike rather than sway, and
#: the practice threshold for "impulsive" sits around 4.
IMPACTING_CREST = 4.0

#: Kurtosis above which the same conclusion is reached from the distribution
#: rather than from the extremes. Gaussian noise is 3.
IMPACTING_KURTOSIS = 4.5

#: Order below which a peak is subharmonic. Just under 1 rather than 1, so
#: a 1x line that landed a bin low is not read as a rub.
SUBHARMONIC_CEILING = 0.9

#: Subharmonic peaks must carry this share of the largest peak before they
#: are reported. Spectra have low-frequency clutter -- mounting resonance,
#: flow noise -- and reporting all of it as a rub would bury the real ones.
SUBHARMONIC_SHARE = 0.10


@dataclass
class Symptom:
    """One thing observed in the signal, and what makes it observable."""
    key: str
    name: str
    #: Plain sentences naming the numbers behind the observation. An analyst
    #: reads these against the spectrum and agrees or does not.
    evidence: list[str] = field(default_factory=list)
    #: Machine-readable version of the same thing.
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name,
                "evidence": self.evidence, "detail": self.detail}


def _synchronous_index(order: float) -> Optional[int]:
    nearest = round(order)
    if nearest < 1:
        return None
    return nearest if abs(order - nearest) <= HARMONIC_TOLERANCE else None


def harmonic_series(peaks: Sequence[SpectralPeak]) -> Optional[Symptom]:
    """A *consecutive* run of whole multiples of running speed.

    A long harmonic series is the signature of something striking once per
    revolution -- looseness, a rub, a crack -- rather than something out of
    balance, which puts its energy at 1x and very little elsewhere.

    **Consecutive is the word that matters, and it was missing.** Counting
    any peak whose order lands near a whole number reported "1x, 5x, 713x,
    877x" as four harmonics on a real capture. Scattered integers are not a
    series: what makes a series diagnostic is that the energy marches up in
    steps, because that is what a clipped or struck waveform produces. So
    the run is measured, not the count, and it has to start at 1x or 2x --
    a run beginning at 6x is some other mechanism's fundamental.
    """
    found: dict[int, SpectralPeak] = {}
    for peak in peaks:
        if peak.order is None:
            continue
        index = _synchronous_index(peak.order)
        if index is None or index > MAX_HARMONIC_ORDER:
            continue
        if index not in found or peak.amplitude > found[index].amplitude:
            found[index] = peak

    if len(found) < MIN_HARMONICS:
        return None

    # The longest unbroken run, and where it starts.
    best_start, best_length = None, 0
    for start in sorted(found):
        if start - 1 in found:
            continue                      # not the beginning of a run
        length = 0
        while start + length in found:
            length += 1
        if length > best_length:
            best_start, best_length = start, length

    if best_length < MIN_HARMONICS or best_start is None or best_start > 2:
        return None

    orders = list(range(best_start, best_start + best_length))
    found = {k: v for k, v in found.items() if k in orders}
    strongest = max(p.amplitude for p in found.values())
    evidence = [
        f"{best_length} consecutive harmonics of running speed, "
        f"{best_start}x through {orders[-1]}x."
    ]
    for index in orders[:4]:
        peak = found[index]
        share = peak.amplitude / strongest if strongest else 0.0
        evidence.append(
            f"{index}x at {peak.frequency_hz:.2f} Hz, {share:.0%} of the "
            f"largest harmonic.")

    return Symptom(
        key="harmonic_series", name="Harmonic series",
        evidence=evidence,
        detail={"count": best_length, "orders": orders,
                "starts_at": best_start, "highest_order": orders[-1]})


def sidebands(peaks: Sequence[SpectralPeak],
              shaft_hz: Optional[float] = None) -> Optional[Symptom]:
    """A local cluster of evenly spaced peaks around a high-order carrier.

    Modulation: something is varying once per revolution of something else.
    Around a gear mesh that is a tooth defect; around a bearing frequency it
    is a defect passing in and out of the load zone.

    **Telling this apart from a harmonic series is the whole difficulty**, and
    it took two wrong attempts. Asking only for evenly spaced neighbours
    fires on every harmonic series, because a harmonic series is evenly
    spaced. Asking for peaks on both sides fires too, because a series is
    symmetric around every one of its middle harmonics -- 2x and 4x straddle
    3x exactly as sidebands straddle a carrier.

    What actually separates them is how far the pattern extends downward. A
    harmonic series fills its grid continuously from the fundamental up, so
    from any peak in it you can walk down in steps of the spacing and keep
    finding peaks until you reach the fundamental. Sidebands are local: a few
    lines either side of a carrier at some high order, and nothing in the
    wide gap between them and the bottom of the spectrum. So the test is
    that the downward walk must *stop early* -- and a carrier at 3x with a
    spacing of 1x has nowhere to stop, which is why a genuine sideband
    carrier is always well above its spacing.

    The carrier is also required to be the strongest line in its own cluster,
    which is what modulation does: the energy sits at the thing being
    modulated, not at the lines it throws off.
    """
    ordered = sorted(peaks, key=lambda p: p.frequency_hz)
    if len(ordered) < 3:
        return None

    frequencies = [p.frequency_hz for p in ordered]
    by_frequency = {p.frequency_hz: p for p in ordered}

    def peak_near(target: float, tolerance: float) -> Optional[SpectralPeak]:
        for f in frequencies:
            if abs(f - target) <= tolerance:
                return by_frequency[f]
        return None

    best: Optional[dict[str, Any]] = None
    for carrier in ordered:
        for other in ordered:
            spacing = other.frequency_hz - carrier.frequency_hz
            if spacing <= 0:
                continue
            tolerance = max(spacing * SIDEBAND_TOLERANCE, 1e-6)

            # How many steps of `spacing` fit below the carrier. This is the
            # depth of the grid a harmonic series would have to fill.
            depth = int(carrier.frequency_hz / spacing)
            if depth < MIN_CARRIER_DEPTH:
                continue

            below = 0
            while below < depth:
                found = peak_near(
                    carrier.frequency_hz - spacing * (below + 1), tolerance)
                if found is None:
                    break
                below += 1

            # The downward walk reached the bottom of the grid: this is a
            # harmonic series seen from one of its middle harmonics.
            if below >= depth - 1:
                continue
            if below == 0:      # nothing on the low side is not modulation
                continue

            above, cluster = 0, [carrier]
            while above < depth:
                found = peak_near(
                    carrier.frequency_hz + spacing * (above + 1), tolerance)
                if found is None:
                    break
                cluster.append(found)
                above += 1

            count = below + above
            if count < MIN_SIDEBANDS:
                continue
            for step in range(1, below + 1):
                found = peak_near(carrier.frequency_hz - spacing * step,
                                  tolerance)
                if found is not None:
                    cluster.append(found)

            # Modulation puts the energy at the carrier.
            if any(p.amplitude > carrier.amplitude
                   for p in cluster if p is not carrier):
                continue

            if best is None or (count, carrier.amplitude) > (best["count"],
                                                            best["amplitude"]):
                best = {"carrier": carrier, "spacing": spacing,
                        "count": count, "below": below, "above": above,
                        "amplitude": carrier.amplitude}

    if best is None:
        return None

    carrier, spacing = best["carrier"], best["spacing"]
    evidence = [
        f"{best['count']} peaks spaced {spacing:.2f} Hz around a carrier at "
        f"{carrier.frequency_hz:.2f} Hz"
        + (f" ({carrier.order:.2f}x)" if carrier.order is not None else "")
        + f" -- {best['below']} below it and {best['above']} above, with "
        f"nothing further down. A harmonic series would continue to the "
        f"bottom; this does not, so it is modulation."
    ]
    if shaft_hz and abs(spacing - shaft_hz) <= shaft_hz * SIDEBAND_TOLERANCE:
        evidence.append(
            f"The spacing matches running speed ({shaft_hz:.2f} Hz), so "
            f"whatever is modulating turns with the shaft.")

    return Symptom(
        key="sidebands", name="Sidebands",
        evidence=evidence,
        detail={"carrier_hz": round(carrier.frequency_hz, 3),
                "carrier_order": (round(carrier.order, 3)
                                  if carrier.order is not None else None),
                "spacing_hz": round(spacing, 3), "count": best["count"],
                "below": best["below"], "above": best["above"]})


def subharmonics(peaks: Sequence[SpectralPeak]) -> Optional[Symptom]:
    """Energy below running speed.

    A machine has nothing that turns slower than its own shaft unless
    something is rubbing, a journal bearing is whirling, or a belt is
    involved. Half-order energy in particular is the classic looseness and
    rub signature.
    """
    if not peaks:
        return None
    strongest = max(p.amplitude for p in peaks)
    if strongest <= 0:
        return None

    below = [p for p in peaks
             if p.order is not None and 0 < p.order < SUBHARMONIC_CEILING
             and p.amplitude >= strongest * SUBHARMONIC_SHARE]
    if not below:
        return None

    below.sort(key=lambda p: -p.amplitude)
    evidence = [
        f"{len(below)} peak(s) below running speed carrying at least "
        f"{SUBHARMONIC_SHARE:.0%} of the largest peak."
    ]
    for peak in below[:3]:
        evidence.append(
            f"{peak.order:.2f}x at {peak.frequency_hz:.2f} Hz, "
            f"{peak.amplitude / strongest:.0%} of the largest.")

    half_order = any(abs(p.order - 0.5) <= 0.05 for p in below)
    if half_order:
        evidence.append(
            "One sits at half running speed, which is the classic looseness "
            "and rub signature.")

    return Symptom(
        key="subharmonics", name="Sub-synchronous energy",
        evidence=evidence,
        detail={"count": len(below), "half_order": half_order,
                "lowest_order": round(min(p.order for p in below), 3)})


def bearing_band_energy(features: dict[str, float]) -> Optional[Symptom]:
    """Energy at the bearing defect frequencies, from the envelope features.

    Read from what VIK-020 already computed rather than recomputed here: a
    second measurement of the same thing is a second chance to disagree with
    what is on the capture's own record.
    """
    bands = {name: features.get(f"{name}_band_energy")
             for name in ("bpfo", "bpfi", "bsf", "ftf")}
    present = {k: v for k, v in bands.items() if v}
    if not present:
        return None

    # Share of the bearing bands, not of the envelope RMS.
    #
    # Dividing a band *energy* by an envelope *amplitude* is dimensionally
    # meaningless, and on a real capture it printed "243378% of the
    # envelope" -- a number that tells a reader nothing except that the
    # platform is not checking its own arithmetic. Against the sum of the
    # four bands the figure is a genuine proportion, and it answers the
    # question actually being asked: which defect frequency dominates.
    total = sum(present.values())
    evidence = []
    for name, value in sorted(present.items(), key=lambda kv: -kv[1]):
        share = (value / total) if total else None
        evidence.append(
            f"{name.upper()} band carries {value:.3e}"
            + (f", {share:.0%} of the energy across the four bearing bands."
               if share is not None else "."))

    harmonic = features.get("bearing_harmonic_energy")
    if harmonic:
        evidence.append(
            f"Bearing-frequency harmonics carry {harmonic:.3e}; a defect "
            f"strikes repeatedly, so its harmonics matter as much as its "
            f"fundamental.")

    return Symptom(
        key="bearing_band_energy", name="Bearing band energy",
        evidence=evidence,
        detail={name: round(value, 9) for name, value in present.items()})


def impacting(features: dict[str, float]) -> Optional[Symptom]:
    """Whether the waveform strikes rather than sways.

    Crest factor and kurtosis say the same thing from different directions
    -- one from the extremes, one from the shape of the distribution -- so
    on a real impact both rise, and either one alone is weak evidence.

    **Both must be present before anything is claimed.** A missing kurtosis
    is not a kurtosis of zero, and a symptom computed from one of the two
    would read on screen exactly like one computed from both.
    """
    crest = features.get("crest_factor")
    kurtosis = features.get("kurtosis")

    # Neither is claimed from a half-filled feature set. This is the
    # platform's rule about unknowns, applied to two numbers.
    if crest is None or kurtosis is None:
        return None

    evidence, triggers = [], []
    if crest and crest >= IMPACTING_CREST:
        triggers.append("crest_factor")
        evidence.append(
            f"Crest factor {crest:.2f}, against {IMPACTING_CREST:.1f} for an "
            f"impulsive signal and 1.41 for a pure sinusoid.")
    if kurtosis and kurtosis >= IMPACTING_KURTOSIS:
        triggers.append("kurtosis")
        evidence.append(
            f"Kurtosis {kurtosis:.2f}, against 3.0 for ordinary noise -- the "
            f"waveform has longer tails than random vibration produces.")

    strong = (crest >= IMPACTING_CREST * IMPACTING_STRONG_MULTIPLE
              or kurtosis >= IMPACTING_KURTOSIS * IMPACTING_STRONG_MULTIPLE)
    if len(triggers) < 2 and not (triggers and strong):
        return None

    if len(triggers) == 2:
        evidence.append(
            "Both measures agree, which is stronger evidence than either "
            "alone: they are computed differently and fail differently.")
    else:
        evidence.append(
            f"Only one of the two measures is raised, but it is more than "
            f"{IMPACTING_STRONG_MULTIPLE:g} times its threshold, which is "
            f"past where the other being ordinary can explain it away.")

    return Symptom(key="impacting", name="Impacting",
                   evidence=evidence,
                   detail={"triggers": triggers, "both_agree":
                           len(triggers) == 2,
                           "crest_factor": crest, "kurtosis": kurtosis})


def detect(
    peaks: Sequence[SpectralPeak],
    features: Optional[dict[str, float]] = None,
    shaft_hz: Optional[float] = None,
) -> list[Symptom]:
    """Everything observable about this signal, each with its evidence."""
    values = features or {}
    found = [
        harmonic_series(peaks),
        sidebands(peaks, shaft_hz),
        subharmonics(peaks),
        bearing_band_energy(values),
        impacting(values),
    ]
    return [symptom for symptom in found if symptom is not None]
