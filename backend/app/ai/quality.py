"""Whether a capture can be trusted — VIK-022.

Eight checks on one channel's samples, returning High, Medium, Low or
Invalid and naming whatever failed. The requirement makes "confidence
reduced due to poor signal quality" a hard rule rather than a nicety, so
this also returns the factor every engine downstream multiplies its own
confidence by.

**Every threshold here was measured on this gateway before it was written
down.** Twelve captures, eight channels, 13,888 samples each:

    quantisation step   0.0015 g on every channel
    AC RMS              0.0020 to 0.0198 g   (median 0.0043)
    DC bias             -0.148 to +0.025 g   (median -0.022)
    largest excursion   0.234 g, against an ADC range of +/-50 g
    bias drift in-record  0.03 to 0.22 x the channel's own RMS
    RMS first half vs second  0.97 to 1.06

Two of those deserve pointing out, because they are what the checks are
calibrated against rather than guesses:

**Nothing is anywhere near clipping.** The largest excursion uses 0.5% of
the converter's range. A clipping check tuned by intuition would never fire;
one tuned to this hardware has to look for the flat top, not the level.

**Several channels are barely above their own quantisation.** Expressed in
ADC counts, the vibration on ch5 spans 1.4 counts and ch6 spans 1.5. Below
about two counts a channel is reporting the converter's rounding rather
than the machine, and no amount of analysis downstream recovers that. This
is a real finding on live data, not a hypothetical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

# --------------------------------------------------------------- levels --

HIGH = "high"
MEDIUM = "medium"
LOW = "low"
INVALID = "invalid"

#: Worst first. A capture takes the worst level any check gives it.
_SEVERITY = {HIGH: 0, MEDIUM: 1, LOW: 2, INVALID: 3}

#: What an engine downstream multiplies its own confidence by. Invalid is
#: zero rather than small: a capture that cannot be measured must not produce
#: a quiet finding, it must produce none.
CONFIDENCE_FACTOR = {HIGH: 1.0, MEDIUM: 0.8, LOW: 0.5, INVALID: 0.0}

# ---------------------------------------------------------- thresholds --

#: Fraction of samples sitting at the extreme value before a channel counts
#: as clipped. A real converter rail produces an exactly repeated value, so
#: this looks for the flat top rather than for a high level -- the signal
#: here uses 0.5% of the range and a level-based test would never fire.
CLIP_SAMPLE_FRACTION = 0.001

#: Consecutive samples at the extreme deviation that make it a rail rather
#: than a coincidence.
#:
#: The first version of this comment justified the number with the wrong
#: measurement -- runs of any repeated value, which reach 26 on healthy data
#: because the vibration spans a couple of ADC counts. What this check
#: counts is runs AT THE EXTREME, and across 160 real channel-records that
#: is 1 in the median case and never exceeds 5. A genuine clipped channel
#: produced runs of 72 in the same units.
#:
#: 20 is four times the worst healthy value and a fraction of a real rail.
CLIP_RUN_LENGTH = 20

#: How far the flat top must sit from the resting position, in converter
#: counts, before it is a rail rather than quantisation. A channel spanning
#: one or two counts repeats its extreme value constantly and has nothing
#: wrong with its gain -- it has nothing to measure. Four counts separates
#: the two cleanly and is still far below any real rail.
CLIP_MIN_STEPS_FROM_REST = 4.0

#: Peak as a fraction of the converter's range before the input is close
#: enough to the rail that the next gust clips it.
SATURATION_FRACTION = 0.80

#: Vibration, in ADC counts, below which a channel is reporting rounding.
#: Two counts is the floor: at one count the only values available are the
#: step and zero. Measured, ch5 spans 1.4 counts and ch6 spans 1.5.
MIN_RESOLUTION_COUNTS = 2.0
POOR_RESOLUTION_COUNTS = 4.0

#: How far the bias may move within one record, as a multiple of the
#: channel's own RMS. Measured drift is 0.03 to 0.22, so 1.0 is a real
#: movement rather than the ordinary wander of a charge amplifier.
BIAS_DRIFT_RMS_MULTIPLE = 1.0

#: DC offset as a fraction of the converter's range before it is abnormal.
#: An IEPE channel sits on a bias current and a few percent is normal; a
#: large one means a failing sensor or a cable fault.
DC_OFFSET_FRACTION = 0.05

#: How much the level may change between the halves of one record before the
#: machine was not in one state for the whole capture. Measured ratios are
#: 0.97 to 1.06.
SPEED_RMS_RATIO = 2.0

#: How much the dominant frequency may move between the halves of a record,
#: as a fraction, before the speed is unstable.
SPEED_DRIFT_FRACTION = 0.10

#: Shaft revolutions each half of the record must hold before the halves can
#: be compared at all. Below this the comparison measures the record length
#: rather than the machine: across 160 real channel-records of steady running
#: at 1.7 revolutions a half, the level ratio between halves reached 3.0 and
#: the crossing rate moved by 150%.
MIN_REVOLUTIONS_PER_HALF = 10.0

#: Crest factor and kurtosis beyond which a channel looks like it is
#: rattling rather than measuring. A loose accelerometer leaves the casing
#: and strikes it again, which gives very high, very short spikes.
LOOSE_CREST_FACTOR = 12.0
LOOSE_KURTOSIS = 20.0

#: ...and how many of those spikes there have to be.
#:
#: The third condition, and the one that took a test to find. A single knock
#: -- someone bumping the machine while the capture runs -- produces a crest
#: factor of 40 AND a kurtosis of 51, clearing both bars on its own. So does
#: a loose sensor. What separates them is that rattling repeats: a loose
#: transducer strikes the casing many times in a record, a knock once.
#:
#: Without this, an engineer is sent to tighten a bolt because someone
#: leaned on the pump.
LOOSE_MIN_EXCURSIONS = 5

#: Excursions are counted at this many standard deviations. Well above the
#: 4 sigma the burst-count feature uses, because this is looking for the
#: extreme spikes of an impact rather than for ordinary impulsiveness.
LOOSE_EXCURSION_SIGMA = 8.0

#: Distinct sample values below which a channel has too little signal to
#: analyse, whatever its amplitude.
#:
#: This is the check that describes this gateway. The pump's eight channels
#: contain between twelve and seventy-three distinct values across a whole
#: record, so almost everything in the spectrum is the converter rounding
#: up and down. The noise-floor check asks whether the signal beats the
#: rounding; this asks whether there is enough of it to do arithmetic on,
#: which is why a capture can pass one and fail the other.
MIN_DISTINCT_VALUES = 40

#: How far the measured shaft speed may sit from the machine's rated speed
#: before the speed is treated as wrong rather than merely different. Wide,
#: because a VFD machine legitimately runs away from nameplate -- this is
#: meant to catch a speed that cannot be right, not one that is unusual.
RPM_DISAGREEMENT_FRACTION = 0.5

#: Gap between consecutive captures, as a multiple of the median gap,
#: above which readings went missing in transit.
PACKET_GAP_MULTIPLE = 3.0


@dataclass
class Check:
    """One test, its result, and why.

    `applicable` is a third outcome, and it is not a detail. A check that
    could not be run is not a check that passed: reporting "speed steady" on
    a record too short to judge steadiness is the same mistake as reporting
    "normal" for a feature nobody graded.
    """
    name: str
    passed: bool
    level: str
    value: float
    threshold: float
    reason: str
    applicable: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.name, "passed": self.passed, "level": self.level,
                "value": self.value, "threshold": self.threshold,
                "reason": self.reason, "applicable": self.applicable}


@dataclass
class QualityAssessment:
    """What a capture's samples are worth."""
    level: str = HIGH
    checks: list[Check] = field(default_factory=list)

    @property
    def failed(self) -> list[str]:
        return [c.name for c in self.checks if c.applicable and not c.passed]

    @property
    def not_assessed(self) -> list[str]:
        """Checks that could not be run -- distinct from checks that passed."""
        return [c.name for c in self.checks if not c.applicable]

    @property
    def reasons(self) -> list[str]:
        return [c.reason for c in self.checks if c.applicable and not c.passed]

    @property
    def confidence_factor(self) -> float:
        """What a downstream engine multiplies its own confidence by."""
        return CONFIDENCE_FACTOR[self.level]

    @property
    def usable(self) -> bool:
        return self.level != INVALID

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "confidence_factor": self.confidence_factor,
            "failed_checks": self.failed,
            "not_assessed": self.not_assessed,
            "reasons": self.reasons,
            "checks": [c.as_dict() for c in self.checks],
        }


def _worst(a: str, b: str) -> str:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def _passed(name: str, value: float, threshold: float, reason: str) -> Check:
    return Check(name, True, HIGH, float(value), float(threshold), reason)


def _not_applicable(name: str, reason: str) -> Check:
    """Could not be run.

    `passed` is False, because it did not pass -- it did not happen.
    `applicable` is what keeps it out of the failure list and out of the
    level. Setting passed=True instead would have made the two fields say
    the same thing, and a reader could then drop either one without any
    test noticing.
    """
    return Check(name, False, HIGH, 0.0, 0.0, reason, applicable=False)


# ----------------------------------------------------------- the checks --

def _check_missing_data(x: np.ndarray, expected: Optional[int]) -> Check:
    """Samples that are not there, or not numbers.

    First, because everything after it divides by something derived from the
    samples. A capture with holes in it is not a poor measurement, it is not
    a measurement.
    """
    if x.size == 0:
        return Check("missing_data", False, INVALID, 0.0, 0.0,
                     "The channel has no samples at all.")
    bad = int(np.count_nonzero(~np.isfinite(x)))
    if bad:
        return Check("missing_data", False, INVALID, bad / x.size, 0.0,
                     f"{bad} of {x.size} samples are not finite numbers, so "
                     f"nothing can be computed from this channel.")
    if expected and x.size < expected:
        short = 1.0 - x.size / expected
        level = INVALID if short > 0.5 else LOW
        return Check("missing_data", False, level, short, 0.0,
                     f"{x.size} samples arrived where {expected} were "
                     f"expected -- {short * 100:.0f}% of the record is "
                     f"missing, so its time axis is wrong.")
    return _passed("missing_data", 0.0, 0.0, "Every expected sample is present.")


def _check_clipping(x: np.ndarray, full_scale_g: float,
                    step_g: Optional[float]) -> Check:
    """The converter or the amplifier hitting a rail.

    Looks for the flat top, not for a high level. On this hardware the
    largest excursion uses 0.5% of the converter's range, so a level-based
    test would never fire -- while a channel whose amplifier has failed can
    sit on a rail at any level at all.

    **Both ends are examined separately.** An earlier version took the
    largest absolute deviation from rest and looked for a flat top there,
    which silently misses one-sided clipping whenever the clipped side is
    the nearer one -- and clipping is frequently one-sided, because a
    failing supply rail goes in one direction. On a channel resting at
    -0.145 g, clipped on its positive side, the furthest point from rest is
    the perfectly healthy negative peak, and the check found nothing.

    The other correction this needed: a channel whose vibration spans one
    or two quantisation steps also has a repeated extreme in long runs,
    because those are the only values it has. That was reported as clipping,
    which sends someone to check the input gain when the sensor is not
    moving. A rail is far from rest; quantisation is a step or two away.
    """
    resting = float(np.mean(x))
    worst: tuple[float, int, float] = (0.0, 0, 0.0)   # fraction, run, value

    for value in (float(np.max(x)), float(np.min(x))):
        distance = abs(value - resting)
        if step_g and step_g > 0 and distance < CLIP_MIN_STEPS_FROM_REST * step_g:
            continue                       # quantisation, not a rail
        at_rail = np.isclose(x, value, rtol=1e-9, atol=0.0)
        fraction = float(np.mean(at_rail))
        run = _longest_run(at_rail)
        if run > worst[1]:
            worst = (fraction, run, value)

    fraction, longest, value = worst

    if fraction > CLIP_SAMPLE_FRACTION and longest >= CLIP_RUN_LENGTH:
        return Check("clipping", False, INVALID, fraction, CLIP_SAMPLE_FRACTION,
                     f"{fraction * 100:.1f}% of samples sit at exactly "
                     f"{value:.4f}, in runs of up to {longest}. The input is "
                     f"clipped: the peaks have been cut off, and every "
                     f"amplitude, crest factor and harmonic from this channel "
                     f"is understated.")
    if longest >= CLIP_RUN_LENGTH:
        return Check("clipping", False, LOW, float(longest), CLIP_RUN_LENGTH,
                     f"{longest} consecutive samples sit at exactly "
                     f"{value:.4f}. That is a flat top, not a peak.")
    return _passed("clipping", fraction, CLIP_SAMPLE_FRACTION,
                   f"No flat tops at either end; the record spans "
                   f"{float(np.min(x)):.4f} to {float(np.max(x)):.4f}.")


def _check_saturation(x: np.ndarray, full_scale_g: float) -> Check:
    """Close enough to the rail that the next gust clips.

    Distinct from clipping: nothing is cut off yet, but the headroom is gone
    and the capture after this one may be worthless.
    """
    if full_scale_g <= 0:
        return _passed("saturation", 0.0, 0.0,
                       "No converter range declared, so headroom is unknown.")
    peak = float(np.max(np.abs(x)))
    used = peak / full_scale_g
    if used > SATURATION_FRACTION:
        return Check("saturation", False, LOW, used, SATURATION_FRACTION,
                     f"The peak uses {used * 100:.0f}% of the converter's "
                     f"+/-{full_scale_g:g} g range. There is almost no "
                     f"headroom left, so the next larger event will clip.")
    return _passed("saturation", used, SATURATION_FRACTION,
                   f"The peak uses {used * 100:.1f}% of the converter's range.")


def _check_noise_floor(x: np.ndarray, step_g: Optional[float]) -> Check:
    """Whether the vibration is bigger than the converter's rounding.

    The check that fires on this machine's real data. Expressed in ADC
    counts, ch5's vibration spans 1.4 counts and ch6's 1.5. A channel with
    one or two values available to it is reporting the step size, and every
    feature computed from it -- kurtosis, crest, spectral shape -- is
    describing the converter.
    """
    spread = float(np.std(x))
    if spread <= 0:
        return Check("noise_floor", False, INVALID, 0.0, 0.0,
                     "The channel does not move at all: every sample is "
                     "identical. The sensor is dead, disconnected, or its "
                     "input is shorted.")
    if not step_g or step_g <= 0:
        return _passed("noise_floor", spread, 0.0,
                       f"RMS {spread:.5f}; no converter step declared, so "
                       f"resolution could not be checked.")

    counts = spread / step_g
    if counts < MIN_RESOLUTION_COUNTS:
        return Check("noise_floor", False, LOW, counts, MIN_RESOLUTION_COUNTS,
                     f"The vibration spans {counts:.1f} converter counts "
                     f"({spread:.5f} g against a step of {step_g:.5f}). The "
                     f"channel is reporting rounding rather than the machine, "
                     f"and no analysis downstream recovers that.")
    if counts < POOR_RESOLUTION_COUNTS:
        return Check("noise_floor", False, MEDIUM, counts, POOR_RESOLUTION_COUNTS,
                     f"The vibration spans only {counts:.1f} converter counts, "
                     f"so shape measurements from this channel are coarse.")
    return _passed("noise_floor", counts, POOR_RESOLUTION_COUNTS,
                   f"The vibration spans {counts:.0f} converter counts.")


def _check_bias_drift(x: np.ndarray) -> Check:
    """The resting position moving during the record.

    An IEPE sensor settles over seconds after power-up, and a failing cable
    wanders. Either makes the first half of a capture a different
    measurement from the second. Measured drift on this gateway is 0.03 to
    0.22 times the channel's own RMS, so a full multiple is real movement.
    """
    half = x.size // 2
    if half < 2:
        return _passed("bias_drift", 0.0, 0.0, "Too few samples to compare halves.")
    spread = float(np.std(x)) or 1e-12
    drift = abs(float(np.mean(x[half:])) - float(np.mean(x[:half])))
    relative = drift / spread
    if relative > BIAS_DRIFT_RMS_MULTIPLE:
        return Check("bias_drift", False, LOW, relative, BIAS_DRIFT_RMS_MULTIPLE,
                     f"The resting position moved {drift:.5f} g between the "
                     f"first and second half of the record -- {relative:.1f} "
                     f"times the vibration itself. The sensor is still "
                     f"settling or its cable is faulty, and the two halves are "
                     f"not the same measurement.")
    return _passed("bias_drift", relative, BIAS_DRIFT_RMS_MULTIPLE,
                   f"The resting position moved {relative:.2f} times the "
                   f"vibration across the record.")


def _check_dc_offset(x: np.ndarray, full_scale_g: float) -> Check:
    """A resting position far from zero.

    Not itself an error -- every IEPE channel sits on a bias -- but a large
    one eats headroom and usually means a failing sensor. ch7 on this
    gateway sits at -0.145 g where the others are within 0.045.
    """
    offset = float(np.mean(x))
    if full_scale_g <= 0:
        return _passed("dc_offset", offset, 0.0,
                       f"Resting position {offset:+.4f} g; no range declared.")
    fraction = abs(offset) / full_scale_g
    if fraction > DC_OFFSET_FRACTION:
        return Check("dc_offset", False, MEDIUM, fraction, DC_OFFSET_FRACTION,
                     f"The channel rests at {offset:+.4f} g, which is "
                     f"{fraction * 100:.0f}% of the converter's range. That "
                     f"eats headroom and usually means a failing sensor or "
                     f"cable.")
    return _passed("dc_offset", fraction, DC_OFFSET_FRACTION,
                   f"The channel rests at {offset:+.4f} g.")


def _check_unstable_speed(x: np.ndarray, sampling_rate_hz: float,
                          shaft_hz: Optional[float]) -> Check:
    """Whether the machine held one state for the whole capture.

    A capture taken through a speed change is not one measurement, and every
    order computed from it is smeared across the change.

    **It refuses to run on a short record, and that is the substance of this
    check.** The test compares the halves of the capture, so each half must
    be long enough for its own level to mean something. At this machine's
    0.28 s and 24.67 Hz a half holds 1.7 shaft revolutions -- and measured
    across 160 real channel-records, on a pump running perfectly steadily
    throughout, the level ratio between halves reached 3.0 and the crossing
    rate moved by 150%. Those numbers are the record length, not the machine,
    and a first attempt at this check duly reported half the channels as
    unstable.

    Ten revolutions a half is the bar. Below it the honest answer is that
    steadiness was not assessed -- which is also a concrete argument for a
    longer capture, since at one second this machine gives 12 a half and the
    check becomes usable.
    """
    half = x.size // 2
    if half < 16:
        return _not_applicable("unstable_speed",
                               "Too few samples to compare the halves.")
    if not shaft_hz or shaft_hz <= 0:
        return _not_applicable(
            "unstable_speed",
            "Steadiness is a question about revolutions and the shaft speed "
            "is unknown, so it was not assessed.")

    per_half = (half / sampling_rate_hz) * shaft_hz
    if per_half < MIN_REVOLUTIONS_PER_HALF:
        needed = MIN_REVOLUTIONS_PER_HALF * 2 / shaft_hz
        return _not_applicable(
            "unstable_speed",
            f"Each half of this record holds {per_half:.1f} shaft revolutions "
            f"and {MIN_REVOLUTIONS_PER_HALF:g} are needed before a difference "
            f"between them means anything. At this length the level between "
            f"halves varies up to 3-fold on steady running, from record "
            f"length alone. Steadiness was not assessed; a {needed:.1f} s "
            f"capture would settle it.")

    first, second = x[:half], x[half:]
    a, b = float(np.std(first)) or 1e-12, float(np.std(second)) or 1e-12
    ratio = max(a, b) / min(a, b)

    rate_a = _crossing_rate(first, sampling_rate_hz)
    rate_b = _crossing_rate(second, sampling_rate_hz)
    mean_rate = (rate_a + rate_b) / 2 or 1e-12
    shift = abs(rate_a - rate_b) / mean_rate

    if ratio > SPEED_RMS_RATIO:
        return Check("unstable_speed", False, LOW, ratio, SPEED_RMS_RATIO,
                     f"The level changed {ratio:.1f}-fold between the first "
                     f"and second half of the record. The machine did not "
                     f"hold one state, so any order computed from this "
                     f"capture is smeared across the change.")
    if shift > SPEED_DRIFT_FRACTION:
        return Check("unstable_speed", False, MEDIUM, shift,
                     SPEED_DRIFT_FRACTION,
                     f"The signal's crossing rate moved {shift * 100:.0f}% "
                     f"between the halves of the record ({rate_a:.0f} to "
                     f"{rate_b:.0f} Hz), which is what a changing speed looks "
                     f"like.")
    return _passed("unstable_speed", max(ratio - 1, shift),
                   SPEED_DRIFT_FRACTION,
                   "Level and crossing rate both held across the record.")


def _check_loose_sensor(x: np.ndarray) -> Check:
    """A transducer that is rattling rather than measuring.

    A properly mounted accelerometer follows the casing. A loose one leaves
    it and strikes it again, which produces very high, very short spikes,
    repeatedly.

    All three conditions are required, and the third is the one that took a
    test to find. A single knock -- someone leaning on the machine mid
    capture -- gives a crest factor of 40 and a kurtosis of 51, clearing
    both of the first two bars on its own. Only the repetition separates a
    loose mounting from a bump.

    The two conditions before it matter too, in the other direction: a
    bearing defect gives high kurtosis with an ordinary crest factor, and
    calling that a mounting problem would send someone to tighten a bolt
    while the bearing fails -- and suppress the very finding it should
    support.
    """
    spread = float(np.std(x))
    if not np.isfinite(spread):
        return _not_applicable(
            "loose_sensor",
            "The channel's spread is not a finite number, so mounting could "
            "not be judged.")
    if spread <= 0:
        return _passed("loose_sensor", 0.0, 0.0, "No movement to judge.")

    centred = x - float(np.mean(x))
    crest = float(np.max(np.abs(centred))) / spread
    # Normalised before raising to the fourth power. On a channel carrying
    # values near the float limit, centred ** 4 overflows to infinity and
    # the kurtosis comes back NaN -- which compares false against every
    # threshold, so the check would quietly pass on the most obviously
    # broken input there is.
    kurtosis = float(np.mean(np.square(np.square(centred / spread))) - 3.0)
    if not np.isfinite(crest) or not np.isfinite(kurtosis):
        return _not_applicable(
            "loose_sensor",
            "The channel's values are too extreme to compute a crest factor "
            "from, so mounting could not be judged.")

    excursions = int(np.count_nonzero(
        np.abs(centred) > LOOSE_EXCURSION_SIGMA * spread))

    if (crest > LOOSE_CREST_FACTOR and kurtosis > LOOSE_KURTOSIS
            and excursions >= LOOSE_MIN_EXCURSIONS):
        return Check("loose_sensor", False, LOW, float(excursions),
                     float(LOOSE_MIN_EXCURSIONS),
                     f"{excursions} spikes beyond "
                     f"{LOOSE_EXCURSION_SIGMA:g} sigma, crest factor "
                     f"{crest:.1f}, kurtosis {kurtosis:.0f}. Very large, very "
                     f"short impacts, repeated through the record: that is a "
                     f"transducer leaving the casing and striking it again. "
                     f"It mimics a bearing fault closely enough to be reported "
                     f"as one, so check the mounting before reading anything "
                     f"else from this channel.")

    if crest > LOOSE_CREST_FACTOR and kurtosis > LOOSE_KURTOSIS:
        return _passed("loose_sensor", float(excursions),
                       float(LOOSE_MIN_EXCURSIONS),
                       f"Crest factor {crest:.1f} and kurtosis {kurtosis:.0f} "
                       f"are both high, but only {excursions} spike(s) beyond "
                       f"{LOOSE_EXCURSION_SIGMA:g} sigma -- a single impact, "
                       f"not a rattle.")

    return _passed("loose_sensor", crest, LOOSE_CREST_FACTOR,
                   f"Crest factor {crest:.1f}, kurtosis {kurtosis:.1f}.")


# ------------------------------------------------------------- helpers --

def _longest_run(flags: np.ndarray) -> int:
    """Longest unbroken stretch of True."""
    if flags.size == 0 or not flags.any():
        return 0
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return int(best)


def _crossing_rate(x: np.ndarray, sampling_rate_hz: float) -> float:
    if x.size < 2 or sampling_rate_hz <= 0:
        return 0.0
    signs = np.signbit(x - float(np.mean(x)))
    return float(np.count_nonzero(signs[1:] != signs[:-1]) * sampling_rate_hz / x.size)


# ---------------------------------------------------------------- entry --

def assess_channel(
    samples: list[float] | np.ndarray,
    sampling_rate_hz: float,
    *,
    expected_samples: Optional[int] = None,
    full_scale_g: float = 0.0,
    quantisation_step_g: Optional[float] = None,
    shaft_hz: Optional[float] = None,
    rated_rpm: Optional[float] = None,
    declared_state: Optional[str] = None,
    temperature_c: Optional[float] = None,
) -> QualityAssessment:
    """Run every section 21.1 check on one channel.

    `full_scale_g` and `quantisation_step_g` describe the converter. Both are
    optional and the checks that need them say so rather than guessing: a
    clipping threshold invented without knowing the range is a threshold
    about nothing.
    """
    x = np.asarray(samples, dtype=np.float64)

    missing = _check_missing_data(x, expected_samples)
    if not missing.passed and missing.level == INVALID:
        # Nothing after this can run on samples that are not there.
        return QualityAssessment(level=INVALID, checks=[missing])

    # Overflow and invalid results are expected here and are handled: every
    # check that can produce one tests its own result for finiteness and
    # reports "could not be judged" rather than a number. Numpy's warning
    # would be noise on input this code already knows how to refuse -- a
    # channel reading 1e308 overflows inside np.std before any of it runs.
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        checks = _run_checks(missing, x, sampling_rate_hz, full_scale_g,
                             quantisation_step_g, shaft_hz,
                             rated_rpm=rated_rpm,
                             declared_state=declared_state,
                             temperature_c=temperature_c)

    level = HIGH
    for check in checks:
        if check.applicable and not check.passed:
            level = _worst(level, check.level)
    return QualityAssessment(level=level, checks=checks)


def _check_low_signal(x: np.ndarray, full_scale_g: float) -> Check:
    """Whether there is enough signal to analyse at all — section 21.1.

    Two ways to have too little, and they need different words. A channel
    can be finely resolved and tiny, or coarsely resolved and reasonably
    large; the second is this gateway. Counting distinct values catches it
    where an amplitude threshold does not, because the amplitude looks fine
    until you notice it is made of thirteen numbers.
    """
    distinct = int(np.unique(x).size)
    if distinct < MIN_DISTINCT_VALUES:
        return Check(
            "low_signal", False, LOW, float(distinct),
            float(MIN_DISTINCT_VALUES),
            f"The channel contains only {distinct} distinct sample values "
            f"across the whole record, against the {MIN_DISTINCT_VALUES} "
            f"needed. Nearly everything in the spectrum is the converter "
            f"rounding rather than the machine, so amplitudes taken from it "
            f"are arithmetic on noise. Raising the channel gain, or "
            f"correcting the sensitivity the PLC applies, is what fixes it.")

    # Deliberately not also testing amplitude against the converter range.
    # A first version did, at 0.1% of full scale, and graded a perfectly
    # healthy 0.036 g signal as poor -- because this hardware's range is
    # +/-50 g, so healthy is 0.07% of it. The threshold was a guess and the
    # test it failed was right.
    #
    # Nothing is lost by dropping it: a signal small against its range is
    # small against its *step* too, and that is what shows up here as few
    # distinct values. This counts the consequence rather than guessing at
    # the cause.
    used = (float(np.std(x)) / full_scale_g) if full_scale_g > 0 else 0.0
    return _passed("low_signal", float(distinct), float(MIN_DISTINCT_VALUES),
                   f"{distinct} distinct sample values"
                   + (f", using {used * 100:.2f}% of the converter range."
                      if full_scale_g > 0 else "."))


def _check_wrong_rpm(shaft_hz: Optional[float],
                     rated_rpm: Optional[float]) -> Check:
    """Whether the measured speed can be right for this machine.

    Not whether it is unusual -- a variable-speed drive legitimately runs
    far from nameplate. This catches a speed that cannot be true, which
    usually means the shaft estimate locked onto the wrong peak, and every
    order in the diagnosis is then wrong by the ratio.
    """
    if shaft_hz is None or not rated_rpm:
        return _not_applicable(
            "wrong_rpm",
            "Either no shaft speed was established or the machine has no "
            "rated speed on record, so the two cannot be compared. Not the "
            "same as the speed being right.")

    measured_rpm = shaft_hz * 60.0
    drift = abs(measured_rpm - rated_rpm) / rated_rpm
    if drift > RPM_DISAGREEMENT_FRACTION:
        return Check(
            "wrong_rpm", False, LOW, drift, RPM_DISAGREEMENT_FRACTION,
            f"The measured speed is {measured_rpm:.0f} rpm against a rated "
            f"{rated_rpm:.0f} -- {drift:.0%} away. A gap this size usually "
            f"means the shaft estimate locked onto the wrong peak, and if "
            f"it did then every order in the diagnosis is wrong by that "
            f"ratio.")
    return _passed("wrong_rpm", drift, RPM_DISAGREEMENT_FRACTION,
                   f"Measured {measured_rpm:.0f} rpm against a rated "
                   f"{rated_rpm:.0f}.")


def _check_wrong_machine_state(x: np.ndarray, declared_state: Optional[str],
                               full_scale_g: float) -> Check:
    """Whether the machine is doing what the record says it is.

    A capture tagged "running" from a stopped machine poisons the baseline
    it feeds, and nothing downstream can tell afterwards.
    """
    if not declared_state:
        return _not_applicable(
            "wrong_machine_state",
            "No machine state was supplied with this capture, so there is "
            "nothing to check the vibration against.")

    level = float(np.std(x))
    # "Turning at all", from the platform's own off-level, rather than a
    # fraction of a converter range that is five hundred times the signal.
    running = level > 2e-4
    claims_running = declared_state.strip().lower() not in (
        "off", "stopped", "idle", "shutdown")

    if claims_running and not running:
        return Check(
            "wrong_machine_state", False, LOW, level, 0.0,
            f"The capture is tagged {declared_state!r} but the vibration is "
            f"{level:.6g} g -- the machine was not turning. A stopped "
            f"capture fed into a running baseline drags it down and nothing "
            f"downstream can tell afterwards.")
    if not claims_running and running:
        return Check(
            "wrong_machine_state", False, MEDIUM, level, 0.0,
            f"The capture is tagged {declared_state!r} but there is "
            f"{level:.6g} g of vibration, so something was turning.")
    return _passed("wrong_machine_state", level, 0.0,
                   f"Vibration agrees with the declared state "
                   f"{declared_state!r}.")


def _check_sensor_temperature(temperature_c: Optional[float]) -> Check:
    """Section 21.1 asks for it and nothing here measures one.

    Reported as not assessed rather than omitted. A check that silently
    does not exist is indistinguishable from a check that passed, and the
    whole point of this module is that those are different.
    """
    if temperature_c is None:
        return _not_applicable(
            "sensor_temperature",
            "No temperature is measured anywhere on this platform -- the "
            "gateway does not send one -- so an abnormal sensor temperature "
            "cannot be detected. Listed rather than dropped, because a "
            "check that is silently absent reads as a check that passed.")
    if temperature_c > 80.0 or temperature_c < -20.0:
        return Check("sensor_temperature", False, MEDIUM, temperature_c, 80.0,
                     f"The sensor reports {temperature_c:.0f} C, outside the "
                     f"range an accelerometer's calibration holds over.")
    return _passed("sensor_temperature", temperature_c, 80.0,
                   f"Sensor at {temperature_c:.0f} C.")


def _run_checks(missing, x, sampling_rate_hz, full_scale_g,
                quantisation_step_g, shaft_hz, rated_rpm=None,
                declared_state=None, temperature_c=None) -> list[Check]:
    return [
        missing,
        _check_clipping(x, full_scale_g, quantisation_step_g),
        _check_saturation(x, full_scale_g),
        _check_low_signal(x, full_scale_g),
        _check_noise_floor(x, quantisation_step_g),
        _check_bias_drift(x),
        _check_dc_offset(x, full_scale_g),
        _check_unstable_speed(x, sampling_rate_hz, shaft_hz),
        _check_loose_sensor(x),
        _check_wrong_rpm(shaft_hz, rated_rpm),
        _check_wrong_machine_state(x, declared_state, full_scale_g),
        _check_sensor_temperature(temperature_c),
    ]


def check_delivery(gaps_seconds: Optional[list[float]] = None,
                   expected_gap_seconds: Optional[float] = None
                   ) -> list[Check]:
    """Packet loss and communication issues — section 21.1.

    Neither is a property of a channel's samples, which is why both were
    missing: every other check takes a sample array. They are properties of
    how the captures arrived, so they are assessed once per capture from
    the gaps between arrival times.

    A gateway that goes quiet produces no capture at all, so the evidence
    is always in the record of what did arrive. This one has gone silent
    for days at a time and nothing anywhere noticed.
    """
    if not gaps_seconds:
        return [
            _not_applicable(
                "packet_loss",
                "Only one capture is on record for this machine, so there "
                "are no gaps between arrivals to judge."),
            _not_applicable(
                "communication",
                "Not enough arrival history to tell a quiet machine from a "
                "quiet link."),
        ]

    ordered = sorted(float(g) for g in gaps_seconds if g is not None and g > 0)
    if not ordered:
        return [_not_applicable("packet_loss", "No usable arrival gaps."),
                _not_applicable("communication", "No usable arrival gaps.")]

    median = ordered[len(ordered) // 2]
    expected = expected_gap_seconds or median
    worst = ordered[-1]

    checks = []
    missed = sum(1 for g in ordered if g > expected * PACKET_GAP_MULTIPLE)
    if missed:
        checks.append(Check(
            "packet_loss", False, MEDIUM, float(missed), 0.0,
            f"{missed} gap(s) between captures are more than "
            f"{PACKET_GAP_MULTIPLE:g} times the usual {expected:.0f} s. "
            f"Readings went missing in transit, so any trend across those "
            f"gaps has holes the arithmetic cannot see."))
    else:
        checks.append(_passed(
            "packet_loss", 0.0, 0.0,
            f"Captures arrive about every {expected:.0f} s with no gap "
            f"beyond {PACKET_GAP_MULTIPLE:g} times that."))

    # A link that has stopped entirely, as opposed to one dropping the odd
    # reading. Judged against the machine's own cadence, because a gateway
    # sending hourly and one sending every two minutes fail differently.
    silence = worst / expected if expected > 0 else 0.0
    if silence > 20.0:
        checks.append(Check(
            "communication", False, LOW, worst, expected * 20.0,
            f"The longest silence is {worst / 3600.0:.1f} hours against a "
            f"usual {expected:.0f} s between captures. The link was down "
            f"rather than dropping readings, and nothing on this machine "
            f"was being watched for that period."))
    else:
        checks.append(_passed(
            "communication", worst, expected * 20.0,
            f"The longest silence is {worst:.0f} s, within normal variation "
            f"of the {expected:.0f} s cadence."))
    return checks


def assess_capture(
    channels: dict[str, list[float]],
    sampling_rate_hz: float,
    per_channel_overrides: Optional[dict[int, dict[str, Any]]] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Every channel, plus the capture's own level.

    The capture takes its worst channel. One unusable channel out of eight
    does not make the other seven unusable, so the per-channel assessments
    are kept and an engine reading one channel reads that channel's level --
    but a summary that reported the best of eight would be useless.

    `per_channel_overrides` replaces named keyword arguments for one channel.
    It exists because the converter settings are genuinely per channel: a
    gateway may run 500 mV/g on two channels and 100 on the rest, which
    changes both the range and the step size on those channels only. Applying
    one channel's figures to all eight makes the resolution check wrong by
    the ratio between them -- five times, on this hardware.
    """
    overrides = per_channel_overrides or {}
    per_channel: dict[int, QualityAssessment] = {}
    for name, samples in channels.items():
        try:
            index = int(str(name).lstrip("ch"))
        except ValueError:
            continue
        settings = {k: v for k, v in
                    {**kwargs, **overrides.get(index, {})}.items()
                    if k not in ("arrival_gaps_seconds",
                                 "expected_gap_seconds")}
        per_channel[index] = assess_channel(samples, sampling_rate_hz, **settings)

    level = HIGH
    for assessment in per_channel.values():
        level = _worst(level, assessment.level)

    # Delivery is about the capture, not any one channel, so it is assessed
    # once and folded into the capture's level.
    delivery = check_delivery(kwargs.get("arrival_gaps_seconds"),
                              kwargs.get("expected_gap_seconds"))
    for check in delivery:
        if check.applicable and not check.passed:
            level = _worst(level, check.level)

    return {
        "level": level,
        "confidence_factor": CONFIDENCE_FACTOR[level],
        "channels": {i: a.as_dict() for i, a in sorted(per_channel.items())},
        "delivery": [c.as_dict() for c in delivery],
        "failed_checks": sorted(
            {c for a in per_channel.values() for c in a.failed}
            | {c.name for c in delivery if c.applicable and not c.passed}),
        "not_assessed": sorted(
            {c for a in per_channel.values() for c in a.not_assessed}
            | {c.name for c in delivery if not c.applicable}),
    }
