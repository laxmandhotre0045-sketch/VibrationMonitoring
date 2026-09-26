"""What normal looks like, learned from history — VIK-025.

A "baseline" today is a saved file: one capture somebody nominated as good.
Everything is then compared against that single reading, which means the
comparison inherits whatever was happening during those three tenths of a
second. This builds one from the capture history instead.

**Robust statistics, and not as a stylistic preference.** A baseline is
built from captures nobody inspected one by one, so it will contain bad
ones. Measured on this platform's own stored history, the quality engine
already rates every capture Low and finds resolution failures on five of
eight channels -- and that is the *good* data. A mean moves with every bad
capture that gets in; a median moves only if most of them are bad.

The difference is not academic. One capture taken while somebody hammered
nearby, in a window of twenty, shifts a mean by a fifth of the hammer blow
and a median by nothing at all.

**It refuses rather than producing a weak baseline.** The ticket is explicit
and it is the important half: a baseline built from four captures is worse
than no baseline, because the system then trusts it. Everything downstream
reads `available` and gets an honest no.

**Quality gates what goes in.** VIK-022 grades every capture, and a capture
it called Invalid must not become part of what the machine is expected to
look like. That is the "confidence reduced due to poor signal quality" rule
applied at its source rather than at the end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Sequence

import numpy as np

#: Captures needed before a baseline is offered at all.
#:
#: The requirement asks for two to four weeks of running data. That is the
#: right answer for a baseline anyone acts on, and it is a lifecycle
#: question (VIK-026) rather than an arithmetic one. This is the arithmetic
#: floor: below about a dozen samples a median and a MAD are themselves
#: noisy, and a spread estimated from eight numbers is not a spread.
MIN_SAMPLES = 12

#: ...and the count above which the statistics are steady enough that a
#: threshold expressed in sigma means what it says.
PREFERRED_SAMPLES = 30

#: MAD to standard-deviation scaling for normally distributed data. Makes a
#: robust sigma comparable to the ordinary one, so "three sigma" keeps its
#: usual meaning without inheriting a standard deviation's sensitivity to a
#: single bad capture.
MAD_TO_SIGMA = 1.4826

#: EWMA weight for the newest sample. 0.2 gives a half-life of about three
#: captures, so it tracks a drift the median deliberately ignores -- the two
#: are reported side by side precisely so a drift is visible as the gap
#: between them.
EWMA_ALPHA = 0.2

#: Quality levels a capture may have and still contribute to normal.
#: "invalid" is excluded outright: a clipped or dead channel is not a
#: description of the machine. "low" is admitted because on this hardware
#: every capture is Low -- excluding it would mean never building a baseline
#: at all -- but it is counted and reported.
ACCEPTABLE_QUALITY = ("high", "medium", "low", "unknown")
EXCLUDED_QUALITY = ("invalid",)

#: Distinct values needed before a spread can be estimated at all.
#:
#: Not the same question as the sample count, and the difference is the
#: failure this platform already has on disk. Nine of the stored "captures"
#: are one synthetic test file uploaded nine times: nine rows, one distinct
#: value, an RMS of 0.29962 against a real machine level of 0.0122. Counted
#: as nine independent samples they look like evidence.
#:
#: Three is the floor because two distinct values give a spread with no way
#: to tell a range from an outlier. Genuine repeats are expected and fine --
#: a quantisation-limited channel returns the same reading often, and that
#: is a real measurement that happens to land on the same step -- so this
#: bites only when almost everything is identical.
MIN_DISTINCT_VALUES = 3

#: How far the top of the window may sit above its middle, in robust sigmas,
#: before the window holds more than one population.
#:
#: The median and the MAD shrug off a contaminated minority -- that is what
#: they are for -- but the percentiles cannot, because the percentiles ARE
#: the distribution. If a twentieth of the window came from somewhere else,
#: p95 reports where that somewhere else is.
#:
#: Which is exactly what happens here. Nine of this platform's stored
#: captures are a synthetic test file, reading an RMS of 0.29962 against a
#: real machine level of 0.01225. The median is untouched at 0.01225 and the
#: robust sigma at 0.00442 -- and p95 comes back 0.29962, sixty sigma out.
#:
#: For a well-behaved distribution p95 sits about 1.6 sigma above the median.
#: Six is far enough to allow a genuinely skewed feature and near enough to
#: catch a foreign population.
CONTAMINATION_SIGMAS = 6.0


#: How close two measured converter steps must be to count as the same
#: setting. They are measured from samples, and the stored CSV rounds, so
#: two captures at 100 mV/g can differ in the last digit. One percent
#: separates that from a real change: the smallest switch anyone would make
#: is 100 to 500, which is a factor of five.
STEP_TOLERANCE = 0.01


def _same_step(a: Optional[float], b: Optional[float]) -> bool:
    """Whether two captures were quantised at the same setting.

    Two unknowns count as the same, so captures from before the step was
    recorded still form a baseline together. A known and an unknown do not:
    that pair cannot be shown to match, and a comparison that might be
    measuring a settings change is not one to act on.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if a <= 0 or b <= 0:
        return False
    return abs(a - b) / max(a, b) <= STEP_TOLERANCE


@dataclass(frozen=True)
class AcquisitionShape:
    """How a capture was taken: the sample rate and the record length.

    Half the features depend on this rather than on the machine. Measured on
    one identical signal at the two shapes this gateway has actually used,
    the zero-crossing rate and the spectral centroid both nearly halve --
    the bandwidth halved, so everything measured across the spectrum halved
    with it. Against a baseline learned from the other shape that reads
    seven sigma out, for a change in a setting.
    """
    sample_rate_hz: Optional[float] = None
    sample_count: Optional[int] = None
    #: What the converter was quantised in, in g -- the third setting in
    #: this group and the one that moves when a channel is switched between
    #: 100 and 500 mV/g. At 100 the step is 0.0015 g and this pump's quietest
    #: channel spans one and a half of them; at 500 it is 0.0003 g and the
    #: same channel spans eight. Kurtosis and crest factor are describing
    #: rounding in the first case and the machine in the second, so a
    #: baseline learned at one step means nothing at the other.
    #:
    #: Measured from the samples rather than taken from the declaration,
    #: because the two disagree on this gateway and only one of them is what
    #: the device did.
    step_g: Optional[float] = None

    @property
    def known(self) -> bool:
        return bool(self.sample_rate_hz and self.sample_count)

    @property
    def duration_s(self) -> Optional[float]:
        if not self.known:
            return None
        return self.sample_count / self.sample_rate_hz

    def describe(self) -> str:
        if not self.known:
            return "an unrecorded acquisition shape"
        return (f"{self.duration_s:.3g} s at "
                f"{self.sample_rate_hz / 1000:.3g} kSPS "
                f"({self.sample_count} samples)")


@dataclass
class BaselineStats:
    """What one feature on one channel normally does."""
    sensor_id: str
    channel: int
    feature_code: str
    median: float = 0.0
    mad: float = 0.0
    robust_sigma: float = 0.0
    p05: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    ewma: Optional[float] = None
    sample_count: int = 0
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    excluded_count: int = 0
    distinct_count: int = 0
    #: The acquisition shape every capture in this baseline shared.
    shape: AcquisitionShape = field(default_factory=AcquisitionShape)
    #: Captures dropped because they were taken at a different shape.
    other_shape_count: int = 0
    #: Captures dropped because the converter was at a different setting.
    other_step_count: int = 0
    #: True when the top of the window does not belong with its middle. The
    #: median and spread are still usable; the percentiles are not.
    mixed_population: bool = False
    available: bool = False
    confidence: float = 0.0
    reason: Optional[str] = None
    confidence_note: Optional[str] = None

    def comparable_with(self, shape: "AcquisitionShape") -> bool:
        """Whether a capture of this shape may be judged against this baseline.

        False when either shape is unknown. Not because an unknown shape is
        probably different, but because it cannot be shown to be the same --
        and a comparison that might be measuring a settings change is not a
        comparison anyone should act on.
        """
        if not self.shape.known or not shape.known:
            return False
        if not _same_step(self.shape.step_g, shape.step_g):
            return False
        return (self.shape.sample_rate_hz == shape.sample_rate_hz
                and self.shape.sample_count == shape.sample_count)

    def z_score(self, value: float) -> Optional[float]:
        """How unusual a reading is, in robust sigmas.

        None when there is no usable baseline or no spread to measure
        against -- not zero, which would read as "perfectly normal" for a
        machine nobody has a normal for.
        """
        if not self.available or self.robust_sigma <= 0:
            return None
        return (value - self.median) / self.robust_sigma

    def as_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id, "channel": self.channel,
            "feature_code": self.feature_code,
            "median": self.median, "mad": self.mad,
            "robust_sigma": self.robust_sigma,
            "p05": self.p05, "p50": self.p50, "p95": self.p95,
            "ewma": self.ewma, "sample_count": self.sample_count,
            "excluded_count": self.excluded_count,
            "distinct_count": self.distinct_count,
            "acquisition_sample_rate_hz": self.shape.sample_rate_hz,
            "acquisition_sample_count": self.shape.sample_count,
            "other_shape_count": self.other_shape_count,
            "other_step_count": self.other_step_count,
            "acquisition_step_g": self.shape.step_g,
            "mixed_population": self.mixed_population,
            "available": self.available, "confidence": self.confidence,
            "reason": self.reason,
            "window_start": self.window_start, "window_end": self.window_end,
        }


@dataclass
class Observation:
    """One capture's value for one feature, and whether it may be used."""
    value: float
    observed_at: datetime
    quality_level: str = "high"
    shape: AcquisitionShape = field(default_factory=AcquisitionShape)

    @property
    def usable(self) -> bool:
        return (np.isfinite(self.value)
                and self.quality_level not in EXCLUDED_QUALITY)


@dataclass
class BaselineWindow:
    """The observations a baseline was built from, and what was left out."""
    used: list[Observation] = field(default_factory=list)
    excluded: list[Observation] = field(default_factory=list)


def _select(observations: Sequence[Observation]) -> BaselineWindow:
    window = BaselineWindow()
    for observation in observations:
        (window.used if observation.usable else window.excluded).append(observation)
    return window


def _confidence(sample_count: int, excluded: int) -> float:
    """How much a baseline built from this many captures is worth.

    Rises with the count and falls with the share that had to be thrown
    away: a window where a third of the captures were unusable describes a
    machine, or an installation, that is not being measured reliably.
    """
    if sample_count < MIN_SAMPLES:
        return 0.0
    fullness = min(1.0, sample_count / PREFERRED_SAMPLES)
    total = sample_count + excluded
    kept = sample_count / total if total else 1.0
    return round(min(1.0, 0.5 + 0.5 * fullness) * kept, 3)


def build_baseline(
    sensor_id: str,
    channel: int,
    feature_code: str,
    observations: Sequence[Observation],
    *,
    min_samples: int = MIN_SAMPLES,
) -> BaselineStats:
    """One feature's learned normal, or an honest refusal.

    Never raises and never returns a half-formed baseline with
    `available` true. A caller that ignores `available` and reads the median
    anyway gets 0.0, which is visibly wrong rather than plausibly wrong.
    """
    stats = BaselineStats(sensor_id=str(sensor_id), channel=int(channel),
                          feature_code=feature_code)

    window = _select(observations)
    stats.excluded_count = len(window.excluded)

    if len(window.used) < min_samples:
        stats.reason = (
            f"{len(window.used)} usable captures, and {min_samples} are needed "
            f"before a median and a spread mean anything. "
            f"{stats.excluded_count} were excluded for quality. No baseline "
            f"is offered: one built from this few is worse than none, because "
            f"the system would then trust it."
        )
        return stats

    ordered = sorted(window.used, key=lambda o: o.observed_at)

    # A baseline covers ONE acquisition shape. Where the window straddles a
    # settings change, the most recent shape wins and the rest are dropped:
    # mixing them would learn a normal that is half one configuration and
    # half another, and then find every capture anomalous.
    newest = ordered[-1].shape
    if newest.known:
        matching = [o for o in ordered
                    if o.shape.sample_rate_hz == newest.sample_rate_hz
                    and o.shape.sample_count == newest.sample_count]
        stats.other_shape_count = len(ordered) - len(matching)

        # And the converter setting, which is the third thing in this group.
        # Switching a channel from 100 mV/g to 500 changes the step from
        # 0.0015 g to 0.0003 g; anything measuring the shape of the signal
        # moves with it, because a signal resolved in one and a half steps
        # has its shape defined by rounding and the same signal in
        # forty-seven steps does not.
        with_step = [o for o in matching
                     if _same_step(o.shape.step_g, newest.step_g)]
        stats.other_step_count = len(matching) - len(with_step)
        ordered = with_step
        stats.shape = newest
        if len(ordered) < min_samples:
            stats.reason = (
                f"{len(ordered)} captures at {newest.describe()}, and "
                f"{min_samples} are needed. {stats.other_shape_count} more "
                f"were taken at a different acquisition shape and "
                f"{stats.other_step_count} at a different converter setting; "
                f"neither can be mixed in, because half the features here "
                f"move by a quarter or more when the sample rate, the record "
                f"length or the resolution changes, and a baseline spanning "
                f"both would find every capture anomalous."
            )
            stats.sample_count = 0
            return stats

    values = np.asarray([o.value for o in ordered], dtype=float)

    # How many of those captures are actually different from each other.
    # Repeated uploads of one file are one measurement however many rows
    # they produce, and this platform has nine such rows on disk.
    stats.distinct_count = int(np.unique(values).size)
    if stats.distinct_count < MIN_DISTINCT_VALUES:
        stats.reason = (
            f"{len(window.used)} captures but only {stats.distinct_count} "
            f"distinct value(s) among them. That is one measurement repeated, "
            f"not a history: a spread cannot be estimated from it, and a "
            f"baseline built on it would look confident because of how many "
            f"rows there are. No baseline is offered."
        )
        return stats

    stats.sample_count = int(values.size)
    stats.window_start = ordered[0].observed_at
    stats.window_end = ordered[-1].observed_at
    if stats.other_shape_count:
        stats.confidence_note = (
            f"{stats.other_shape_count} capture(s) in the window were taken "
            f"at a different acquisition shape and were left out.")

    stats.median = float(np.median(values))
    # The median of the absolute deviations from the median -- not the mean
    # of them, which would reintroduce exactly the sensitivity this avoids.
    stats.mad = float(np.median(np.abs(values - stats.median)))
    stats.robust_sigma = float(stats.mad * MAD_TO_SIGMA)
    stats.p05 = float(np.percentile(values, 5))
    stats.p50 = float(np.percentile(values, 50))
    stats.p95 = float(np.percentile(values, 95))

    # Oldest first, so the weight lands on the newest capture.
    ewma = float(values[0])
    for value in values[1:]:
        ewma = EWMA_ALPHA * float(value) + (1 - EWMA_ALPHA) * ewma
    stats.ewma = ewma

    stats.available = True
    stats.confidence = _confidence(stats.sample_count, stats.excluded_count)

    # Does the top of this window belong with its middle?
    if stats.robust_sigma > 0:
        reach = (stats.p95 - stats.median) / stats.robust_sigma
        if reach > CONTAMINATION_SIGMAS:
            stats.mixed_population = True
            stats.reason = (
                f"The middle of this window is steady -- median "
                f"{stats.median:g}, spread {stats.robust_sigma:g} -- but its "
                f"top fifth reaches {stats.p95:g}, which is {reach:.0f} sigma "
                f"out. That is not a tail, it is a second population: the "
                f"window contains captures from something other than this "
                f"machine in this state. The median and spread are still "
                f"usable; the percentiles describe the intruder. Narrow the "
                f"window or remove the captures that do not belong."
            )
            # Confidence is cut because the window is not what it claims to
            # be, even though the robust statistics survived it.
            stats.confidence = round(stats.confidence * 0.5, 3)

    if stats.robust_sigma <= 0:
        # More than half the captures returned the same number, so the median
        # absolute deviation is zero even though the values are not all
        # identical. Real for a quantisation-limited channel, and it makes a
        # z-score undefined rather than infinite -- which is why z_score
        # returns None instead of dividing.
        stats.reason = (
            f"Most of the {stats.sample_count} captures returned "
            f"{stats.median:g} ({stats.distinct_count} distinct values in "
            f"all), so this feature has no usable spread to compare against. "
            f"The baseline is available but no z-score can be computed from "
            f"it."
        )
    elif stats.sample_count < PREFERRED_SAMPLES:
        stats.reason = (
            f"Built from {stats.sample_count} captures; {PREFERRED_SAMPLES} "
            f"would make the spread steady enough for a threshold in sigma to "
            f"mean what it says."
        )
    return stats


def build_all(
    sensor_id: str,
    observations_by_key: dict[tuple[int, str], Sequence[Observation]],
    *,
    min_samples: int = MIN_SAMPLES,
) -> dict[tuple[int, str], BaselineStats]:
    """Every (channel, feature) pair, including the ones that refuse.

    The refusals are returned rather than dropped. A caller needs to be able
    to say "this feature has no baseline yet" and why, which it cannot do
    from an absent key.
    """
    return {
        key: build_baseline(sensor_id, key[0], key[1], observations,
                            min_samples=min_samples)
        for key, observations in observations_by_key.items()
    }
