"""The ISO 10816-3 zone, and every table that could apply — VIK-056.

An ISO zone is the one number a maintenance engineer already knows how to
read. A fault name is our opinion; Zone C is a published standard saying
this machine is unsatisfactory for long-term operation, and it travels
outside this platform in a way our own scores do not.

**The ticket's hard requirement is about ambiguity, and it is the whole
design.** The zone depends on which of the standard's four machine groups
the machine belongs to and whether its foundation is rigid or flexible.
Those come from nameplate data nobody has necessarily entered. Picking a
group when the record does not determine one produces a zone that looks
exactly like a measured one and is a guess -- and the guess moves the
answer: 4.5 mm/s is Zone B on a Group 1 rigid foundation and Zone C on a
Group 3 flexible one, which is the difference between "carry on" and "plan
a repair".

So this returns every table that could apply, each with its own zone, and
says what is missing that would narrow it.

**With one piece of good news the ticket does not ask for.** When every
applicable table lands on the same zone, the ambiguity does not matter and
saying so is far more useful than a shrug. A machine at 1.2 mm/s is Zone A
or B under all eight combinations of group and foundation -- nobody needs
to find the nameplate to act on that. The uncertainty only has to be
surfaced when it actually changes the answer.

**The velocity is integrated here rather than measured.** ISO 10816 is
written in broadband velocity RMS from 10 to 1000 Hz, and this platform
measures acceleration. Integration is a division by frequency, which
amplifies whatever noise sits at the bottom of the spectrum -- which is
why the standard's band starts at 10 Hz and why this refuses to extrapolate
below the first bin the capture actually resolves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np

from vibcore.iso10816 import group_definitions, infer_machine_group, severity_zone

#: The standard's evaluation band. Below 10 Hz integration noise dominates;
#: above 1000 Hz the standard does not claim to say anything, and bearing
#: and gear energy up there would swamp a number meant to describe the
#: machine as a whole.
ISO_BAND_HZ = (10.0, 1000.0)

#: Equivalent noise bandwidth of the window the spectra are built with,
#: in bins. Hann is 1.5; a rectangular window would be 1.0.
#:
#: This correction is not optional and it is easy to miss. The spectra here
#: are amplitude-corrected -- scaled so a pure tone reads its true peak
#: height in the bin it lands in -- which is what a chart and a
#: single-frequency feature need. But a window spreads one tone across about
#: three bins, and summing those bins in quadrature then counts the same
#: energy three times over at the corrected height. The overstatement is
#: exactly the window's noise bandwidth: a 1 g tone integrates to 54.8 mm/s
#: uncorrected against 44.7 mm/s by hand, and 54.8 / sqrt(1.5) = 44.7.
#:
#: A 22% error would move a machine from Zone B into Zone C on its own.
WINDOW_NOISE_BANDWIDTH_BINS = 1.5

#: The groups this platform will consider when the machine record does not
#: determine one. 1-4 are the standard's own.
ALL_GROUPS = (1, 2, 3, 4)
ALL_FOUNDATIONS = ("rigid", "flexible")

#: Free-text foundation descriptions seen in the equipment record, mapped
#: to the standard's two. Anything not listed is treated as unknown rather
#: than guessed -- "concrete" is rigid, but "steel" alone could be either a
#: rigid baseplate or a flexible frame.
FOUNDATION_WORDS = {
    "rigid": "rigid", "concrete": "rigid", "grouted": "rigid",
    "foundation block": "rigid", "solid": "rigid", "bedplate": "rigid",
    "flexible": "flexible", "spring": "flexible", "isolated": "flexible",
    "skid": "flexible", "frame": "flexible", "anti-vibration": "flexible",
}

ZONES = ("A", "B", "C", "D")

#: Distinct sample values a record must contain before an amplitude taken
#: from it means anything.
#:
#: This gateway's captures span thirteen. A 16-bit converter over +/-5 V at
#: 100 mV/g steps about 0.0015 g, and the pump's whole signal is a couple of
#: dozen steps wide -- so most of what the spectrum contains is the
#: converter rounding, not the machine.
#:
#: The consequence for this module is specific and was found by running it:
#: the real capture integrated to 0.027 mm/s and graded **Zone A, typical of
#: newly commissioned machines**. A running pump reads one to three mm/s.
#: The reading was two orders of magnitude low because there was almost no
#: signal to read, and the standard's best zone is exactly how "we cannot
#: see anything" comes out when nobody checks. Somebody would have taken
#: that as a clean bill of health.
MIN_DISTINCT_VALUES = 40

#: Below this, no ISO zone is reported whatever the tables say. A stopped
#: machine also grades Zone A, and for the same wrong reason.
MIN_GRADEABLE_MM_S = 0.25


def broadband_velocity_rms(
    frequencies: Sequence[float],
    magnitudes_g: Sequence[float],
    band_hz: tuple[float, float] = ISO_BAND_HZ,
    window_noise_bandwidth_bins: float = WINDOW_NOISE_BANDWIDTH_BINS,
) -> Optional[dict[str, Any]]:
    """Velocity RMS in mm/s over the standard's band, from an acceleration
    spectrum.

    Each bin is integrated on its own -- ``v = a / (2*pi*f)`` -- and the
    result combined in quadrature, which is Parseval's theorem and the
    reason this can be done in the frequency domain at all. Doing it here
    rather than by integrating the waveform avoids the DC drift that makes
    time-domain integration of an accelerometer signal notoriously
    unreliable.

    Returns ``None`` when the capture does not reach the band, rather than a
    number computed from the part of it that does. A velocity RMS over 40 to
    1000 Hz is not the quantity the standard's limits refer to, and nothing
    downstream would be able to tell the difference.
    """
    freqs = np.asarray(frequencies, dtype=float)
    mags = np.asarray(magnitudes_g, dtype=float)
    if freqs.size < 2 or freqs.size != mags.size:
        return None

    low, high = band_hz
    resolution = float(freqs[1] - freqs[0])
    top = float(freqs[-1])

    # The first bin above DC. If the capture cannot resolve down to 10 Hz,
    # the band it would report is not the band the standard means.
    if resolution > low:
        return {
            "velocity_rms_mm_s": None,
            "missing": [f"a record long enough to resolve {low:.0f} Hz "
                        f"(this one resolves {resolution:.2f} Hz per bin, so "
                        f"its first usable line is above the bottom of the "
                        f"standard's band)"],
            "band_hz": [low, high], "bins_used": 0,
        }

    ceiling = min(high, top)
    mask = (freqs >= low) & (freqs <= ceiling)
    if not mask.any():
        return {"velocity_rms_mm_s": None,
                "missing": ["a spectrum covering the 10-1000 Hz band"],
                "band_hz": [low, high], "bins_used": 0}

    # 9806.65 mm/s^2 per g. Amplitudes are 0-peak, so /sqrt(2) for RMS, and
    # the total is divided by the window's noise bandwidth because these
    # magnitudes are amplitude-corrected -- see the constant above.
    velocity_peak = mags[mask] * 9806.65 / (2.0 * np.pi * freqs[mask])
    power = float(np.sum((velocity_peak / np.sqrt(2.0)) ** 2))
    rms = float(np.sqrt(power / max(window_noise_bandwidth_bins, 1e-9)))

    missing: list[str] = []
    first_bin = float(freqs[mask][0])
    if first_bin > low + resolution:
        missing.append(
            f"content between {low:.0f} and {first_bin:.1f} Hz (this record "
            f"resolves {resolution:.2f} Hz per bin, so the bottom of the "
            f"standard's band falls between lines)")
    if top < high:
        missing.append(
            f"spectrum content above {top:.0f} Hz (the standard's band runs "
            f"to {high:.0f} Hz; this capture stops short, so the figure is a "
            f"lower bound)")

    return {"velocity_rms_mm_s": round(rms, 4), "missing": missing,
            "band_hz": [round(first_bin, 1), round(ceiling, 1)],
            "bins_used": int(mask.sum()),
            "truncated_above_hz": round(top, 1) if top < high else None}


def signal_floor_reason(
    velocity_rms_mm_s: Optional[float],
    distinct_values: Optional[int] = None,
) -> Optional[str]:
    """Why this capture cannot carry an ISO grade, or None if it can.

    Checked before the tables, because every check after this one assumes
    the velocity describes the machine. When it describes the converter
    instead, the zone it produces is arithmetic on noise.
    """
    if distinct_values is not None and distinct_values < MIN_DISTINCT_VALUES:
        return (
            f"The capture contains only {distinct_values} distinct sample "
            f"values, against the {MIN_DISTINCT_VALUES} this grading needs. "
            f"Nearly all of what the spectrum contains is the converter "
            f"rounding rather than the machine, so any amplitude taken from "
            f"it -- and therefore any zone -- would be arithmetic on noise. "
            f"Raising the channel gain, or correcting the accelerometer "
            f"sensitivity the PLC is applying, is what fixes this.")

    if (velocity_rms_mm_s is not None
            and velocity_rms_mm_s < MIN_GRADEABLE_MM_S):
        return (
            f"The broadband velocity is {velocity_rms_mm_s:.3f} mm/s, below "
            f"the {MIN_GRADEABLE_MM_S} mm/s floor for a grade. A running "
            f"machine reads one to three; this reads like a machine that is "
            f"stopped, or one whose signal is not reaching the instrument. "
            f"Either way it is not Zone A -- the standard's best zone and "
            f"an absent signal produce the same number, and they are "
            f"opposite findings.")
    return None


def foundation_of(description: Optional[str]) -> Optional[str]:
    """The standard's foundation class, or None when the record does not say.

    None rather than a default. A default here is a silent choice between
    two tables whose boundaries differ by about 60%.
    """
    if not description:
        return None
    text = description.strip().lower()
    for word, kind in FOUNDATION_WORDS.items():
        if word in text:
            return kind
    return None


@dataclass
class IsoVerdict:
    """The zone, or every zone it could be and what would settle it."""
    velocity_rms_mm_s: Optional[float] = None
    band_hz: Optional[list[float]] = None
    #: One entry per applicable table, each a full grading.
    candidates: list[dict[str, Any]] = field(default_factory=list)
    #: Set only when every candidate agrees.
    zone: Optional[str] = None
    #: The span across candidates when they do not.
    zone_range: Optional[list[str]] = None
    #: Facts that would narrow the tables to one.
    missing: list[str] = field(default_factory=list)
    determined: bool = False
    reason: str = ""

    @property
    def usable(self) -> bool:
        """Whether a zone can be stated at all.

        True when the candidates agree even though the group does not -- the
        point of the module. False when there is no velocity, or the
        applicable tables disagree.
        """
        return self.zone is not None

    @property
    def worst_zone(self) -> Optional[str]:
        """The most severe zone any applicable table gives.

        What a conservative reader wants when the tables disagree: not an
        answer, but the worst case the uncertainty admits.
        """
        zones = [c["zone"] for c in self.candidates]
        return max(zones, key=ZONES.index) if zones else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "usable": self.usable, "zone": self.zone,
            "zone_range": self.zone_range, "worst_zone": self.worst_zone,
            "velocity_rms_mm_s": self.velocity_rms_mm_s,
            "band_hz": self.band_hz, "determined": self.determined,
            "candidates": self.candidates, "missing": self.missing,
            "reason": self.reason,
        }


def _candidates_for(power_kw: Optional[float], machine_type: Optional[str],
                    integrated_driver: bool,
                    shaft_height_mm: Optional[float]) -> tuple[list[int], list[str]]:
    """Which groups could apply, and what is missing if more than one does."""
    inferred = infer_machine_group(power_kw, machine_type, integrated_driver,
                                   shaft_height_mm)
    if inferred is not None:
        return [inferred], []

    missing: list[str] = []
    if not machine_type:
        missing.append("the machine type (a pump is Group 3 or 4 whatever "
                       "its size, so this alone often settles it)")
    if power_kw is None:
        missing.append("the rated power in kW (above 300 kW is Group 1, "
                       "15-300 kW is Group 2)")
    if power_kw is not None and power_kw <= 15:
        missing.append(
            f"a standard that covers this machine -- at {power_kw:g} kW it "
            f"is below the 15 kW floor of ISO 10816-3 Groups 1-4, and the "
            f"zones below are shown only as the nearest available reference")
    if shaft_height_mm is None and power_kw is None:
        missing.append("the shaft height in mm (the fallback for electrical "
                       "machines when power is not recorded)")
    return list(ALL_GROUPS), missing


def grade(
    *,
    velocity_rms_mm_s: Optional[float],
    machine_type: Optional[str] = None,
    power_kw: Optional[float] = None,
    foundation: Optional[str] = None,
    integrated_driver: bool = False,
    shaft_height_mm: Optional[float] = None,
    band_hz: Optional[list[float]] = None,
    velocity_missing: Optional[list[str]] = None,
    distinct_values: Optional[int] = None,
) -> IsoVerdict:
    """Grade a velocity reading against every ISO table that could apply.

    `foundation` is the equipment record's free-text description; it is
    classified here, and when it cannot be, both foundations are graded.
    """
    verdict = IsoVerdict(velocity_rms_mm_s=velocity_rms_mm_s,
                         band_hz=band_hz)
    verdict.missing.extend(velocity_missing or [])

    if velocity_rms_mm_s is None:
        verdict.reason = (
            "No broadband velocity could be computed for this capture, so "
            "there is nothing to grade. An ISO zone is a statement about a "
            "velocity measurement; without one there is no zone, which is "
            "not the same as Zone A.")
        return verdict

    # Before the tables, because everything past here assumes the velocity
    # describes the machine rather than the instrument's own floor.
    blocked = signal_floor_reason(velocity_rms_mm_s, distinct_values)
    if blocked:
        verdict.reason = blocked
        verdict.missing.append(
            "a capture with enough signal in it to grade")
        return verdict

    groups, group_missing = _candidates_for(power_kw, machine_type,
                                            integrated_driver, shaft_height_mm)
    verdict.missing.extend(group_missing)

    classified = foundation_of(foundation)
    foundations = [classified] if classified else list(ALL_FOUNDATIONS)
    if not classified:
        verdict.missing.append(
            "whether the foundation is rigid or flexible" +
            (f" (the record says {foundation!r}, which does not map to "
             f"either)" if foundation else " (the record does not say)"))

    definitions = group_definitions()
    for group in groups:
        for base in foundations:
            try:
                result = severity_zone(velocity_rms_mm_s, group, base)
            except ValueError:
                continue
            entry = result.as_dict()
            entry["group_description"] = (
                definitions.get(str(group), {}).get("description"))
            entry["group_name"] = result.group_name
            verdict.candidates.append(entry)

    if not verdict.candidates:
        verdict.reason = (
            "No ISO 10816-3 table applies to this machine. The standard's "
            "groups start at 15 kW, and nothing in the record places this "
            "machine in one of them.")
        return verdict

    zones = sorted({c["zone"] for c in verdict.candidates}, key=ZONES.index)
    verdict.determined = len(verdict.candidates) == 1

    if len(zones) == 1:
        verdict.zone = zones[0]
        first = verdict.candidates[0]
        if verdict.determined:
            verdict.reason = (
                f"{velocity_rms_mm_s:.2f} mm/s RMS puts this machine in Zone "
                f"{verdict.zone} of ISO 10816-3 for {first['group_name']} on "
                f"a {first['foundation']} foundation. {first['zone_meaning']}")
        else:
            verdict.reason = (
                f"The machine record does not determine which ISO table "
                f"applies, but at {velocity_rms_mm_s:.2f} mm/s RMS all "
                f"{len(verdict.candidates)} that could apply give Zone "
                f"{verdict.zone}, so the missing details do not change the "
                f"answer. {first['zone_meaning']}")
        return verdict

    verdict.zone_range = [zones[0], zones[-1]]
    spread = "; ".join(
        f"{c['group_name']} on a {c['foundation']} foundation: Zone "
        f"{c['zone']}" for c in verdict.candidates)
    verdict.reason = (
        f"At {velocity_rms_mm_s:.2f} mm/s RMS this machine grades anywhere "
        f"from Zone {zones[0]} to Zone {zones[-1]} depending on which ISO "
        f"table applies, and the record does not say which. {spread}. No "
        f"single zone is reported because choosing one would be a guess "
        f"that looks like a measurement -- the worst case among these is "
        f"Zone {zones[-1]}.")
    return verdict


def grade_spectrum(
    frequencies: Sequence[float],
    magnitudes_g: Sequence[float],
    samples: Optional[Sequence[float]] = None,
    **machine: Any,
) -> IsoVerdict:
    """Integrate an acceleration spectrum and grade it. The usual entry.

    `samples` is the waveform the spectrum came from. It is used for one
    thing -- counting how many distinct values the converter produced --
    and passing it is what stops a capture made entirely of quantisation
    noise grading as a newly commissioned machine.
    """
    distinct = None
    if samples is not None and len(samples) > 0:
        distinct = int(np.unique(np.asarray(samples, dtype=float)).size)

    velocity = broadband_velocity_rms(frequencies, magnitudes_g)
    if velocity is None:
        return grade(velocity_rms_mm_s=None, distinct_values=distinct,
                     **machine)
    return grade(velocity_rms_mm_s=velocity["velocity_rms_mm_s"],
                 band_hz=velocity["band_hz"],
                 velocity_missing=velocity["missing"],
                 distinct_values=distinct, **machine)
