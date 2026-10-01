"""Remaining useful life, and the far commoner answer — section 13.

The requirement opens with the condition rather than the calculation: "RUL
should be provided only when enough historical trend data is available."
That is the whole design. Extrapolating a failure date from a short record
is arithmetic anybody can do and nobody should trust, and it is the single
most dangerous number this platform could produce -- wrong one way and a
machine fails unattended, wrong the other and a healthy line is stopped.

**So this refuses by default and has to be argued into answering.** Four
gates, and all four must pass: enough readings, over enough time, with a
trend that is actually rising, and a fit good enough that the extrapolation
means something. On this gateway the first two fail by a wide margin -- 162
captures across five days against the thirty days and twenty points the
shortest credible estimate needs -- so the honest output is section 13's own
words, with the numbers behind them.

**A range, never a date.** "45 to 70 days" is a statement about
uncertainty; "57 days" is a statement about confidence nobody has. The
width comes from the scatter around the fit, so a noisy trend produces a
wide range rather than a confident-looking one.

**The assumption is reported because it changes the answer.** A feature
climbing linearly and one climbing exponentially can look identical over a
short window and differ by months at the threshold. Both are fitted, the
better is used, and which one it was travels with the estimate -- an
engineer who disagrees with the assumption can then say so.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

#: Days of history before an extrapolation is worth making. Below this the
#: window is shorter than the ordinary variation of a running machine, so
#: the slope is measuring weather rather than wear.
MIN_HISTORY_DAYS = 30.0

#: Readings needed over that span. Twenty is the point at which a slope has
#: enough support that one outlier cannot set it.
MIN_POINTS = 20

#: How well the fit must describe the data before it may be extrapolated.
#: Below this the trend is not a trend, it is scatter with a direction.
MIN_FIT_QUALITY = 0.50

#: The trend must climb by at least this fraction of the threshold across
#: the window. A flat feature has no failure date, however long it is
#: watched, and dividing by a near-zero slope produces a confident-looking
#: number in the thousands of days.
MIN_RISE_FRACTION = 0.05

#: How much better the exponential fit must be before it is preferred.
#:
#: Almost nothing, and deliberately. A clean exponential climb over a
#: few months is fitted well by a straight line too -- 0.97 against 0.99 in
#: testing -- so a margin of any size picks "linear" and reports a
#: degradation that is accelerating as one that is not. That is the
#: dangerous direction to be wrong in: an accelerating fault reaches the
#: threshold sooner than the straight line says. The small margin that
#: remains is only to stop noise flipping the choice at random.
EXPONENTIAL_PREFERENCE_MARGIN = 0.01

#: Range width, relative to its own midpoint, above which the estimate
#: cannot be called high confidence however well the line fits. A fit can
#: describe a noisy trend faithfully and still place the threshold
#: anywhere across a month, and calling that "high" reads as precision
#: nobody has.
WIDE_RANGE_FRACTION = 0.35
VERY_WIDE_RANGE_FRACTION = 0.75

#: Beyond this the estimate stops being useful and starts being noise --
#: the extrapolation is far outside the window that supported it.
MAX_HORIZON_DAYS = 730.0

#: Inputs section 13.1 asks for that this platform cannot supply.
UNAVAILABLE_INPUTS = {
    "temperature_trend": (
        "No temperature is measured anywhere on this platform -- the "
        "gateway does not send one -- so thermal degradation cannot "
        "contribute to the estimate."),
}


@dataclass
class RulVerdict:
    """Section 13.2's outputs, including the one that matters most."""
    available: bool = False
    days_low: Optional[float] = None
    days_high: Optional[float] = None
    confidence: str = "none"          # none | low | medium | high
    degradation_rate: Optional[float] = None   # units per day
    direction: str = "unknown"        # rising | steady | falling | unknown
    assumption: Optional[str] = None  # linear | exponential
    reliable: bool = False
    fit_quality: Optional[float] = None
    #: Width of the range as a fraction of its own midpoint. What an
    #: engineer actually plans around.
    range_width: Optional[float] = None
    points: int = 0
    span_days: Optional[float] = None
    #: Inputs section 13.1 lists that were not available.
    missing_inputs: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available, "days_low": self.days_low,
            "days_high": self.days_high, "confidence": self.confidence,
            "degradation_rate": self.degradation_rate,
            "direction": self.direction, "assumption": self.assumption,
            "reliable": self.reliable, "fit_quality": self.fit_quality,
            "range_width": self.range_width,
            "points": self.points, "span_days": self.span_days,
            "missing_inputs": self.missing_inputs, "reason": self.reason,
        }


def _fit(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float, float]:
    """Least-squares line. Returns (slope, intercept, r-squared)."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return 0.0, mean_y, 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    ss_total = sum((y - mean_y) ** 2 for y in ys)
    if ss_total <= 0:
        return slope, intercept, 0.0
    ss_residual = sum((y - (slope * x + intercept)) ** 2
                      for x, y in zip(xs, ys))
    return slope, intercept, max(0.0, 1.0 - ss_residual / ss_total)


def _scatter(xs: Sequence[float], ys: Sequence[float],
             slope: float, intercept: float) -> float:
    """Standard error of the residuals, for the width of the range."""
    n = len(xs)
    if n <= 2:
        return 0.0
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    return math.sqrt(sum(r * r for r in residuals) / (n - 2))


def estimate(
    *,
    history: Sequence[tuple[datetime, float]],
    threshold: float,
    feature_name: str = "the tracked feature",
    operating_hours: Optional[float] = None,
    maintenance_history: Optional[int] = None,
    failure_history: Optional[int] = None,
    has_temperature: bool = False,
    has_load: bool = False,
    now: Optional[datetime] = None,
) -> RulVerdict:
    """Estimate remaining life, or say why it cannot be estimated.

    `history` is (timestamp, value) for the health indicator being tracked,
    in any order. `threshold` is the value at which the machine is
    considered to have reached the end of useful life.
    """
    now = now or datetime.now(timezone.utc)
    verdict = RulVerdict()

    missing = []
    if not has_temperature:
        missing.append(UNAVAILABLE_INPUTS["temperature_trend"])
    if not has_load:
        missing.append(
            "No load signal is recorded, so degradation cannot be separated "
            "from a machine simply being worked harder.")
    if operating_hours is None:
        missing.append("Operating hours are not recorded, so wear cannot be "
                       "expressed per running hour.")
    if maintenance_history is None:
        missing.append("No maintenance history, so the estimate cannot "
                       "account for work already done.")
    if failure_history is None:
        missing.append("No failure history for this machine or its type, so "
                       "there is no prior to anchor the estimate against.")
    verdict.missing_inputs = missing

    points = sorted(
        ((t if t.tzinfo else t.replace(tzinfo=timezone.utc), float(v))
         for t, v in history if v is not None),
        key=lambda pair: pair[0])
    verdict.points = len(points)
    # Recorded before the gates, so a refusal still says how much history
    # there was. Reporting the count and leaving the span null makes the
    # shortfall look like half a measurement.
    if len(points) >= 2:
        verdict.span_days = round(
            (points[-1][0] - points[0][0]).total_seconds() / 86400.0, 2)

    if len(points) < MIN_POINTS:
        verdict.reason = (
            f"RUL prediction not available due to insufficient history. "
            f"{len(points)} reading(s) are on record and at least "
            f"{MIN_POINTS} are needed before a slope has enough support "
            f"that one outlier cannot set it.")
        return verdict

    span = verdict.span_days or 0.0

    if span < MIN_HISTORY_DAYS:
        verdict.reason = (
            f"RUL prediction not available due to insufficient history. The "
            f"readings cover {span:.1f} days and at least "
            f"{MIN_HISTORY_DAYS:.0f} are needed. Below that the window is "
            f"shorter than the ordinary week-to-week variation of a running "
            f"machine, so the slope measures weather rather than wear.")
        return verdict

    base = points[0][0]
    xs = [(t - base).total_seconds() / 86400.0 for t, _ in points]
    ys = [v for _, v in points]

    slope, intercept, quality = _fit(xs, ys)

    # The same data on a log scale: a feature climbing exponentially and one
    # climbing linearly look alike over a short window and differ by months
    # at the threshold.
    assumption, use_slope, use_intercept, use_quality = (
        "linear", slope, intercept, quality)
    if all(y > 0 for y in ys) and threshold > 0:
        log_ys = [math.log(y) for y in ys]
        log_slope, log_intercept, log_quality = _fit(xs, log_ys)
        if log_quality > quality + EXPONENTIAL_PREFERENCE_MARGIN \
                and log_slope > 0:
            assumption = "exponential"
            use_slope, use_intercept, use_quality = (
                log_slope, log_intercept, log_quality)

    verdict.assumption = assumption
    verdict.fit_quality = round(use_quality, 3)
    verdict.degradation_rate = round(use_slope, 6)

    # How far the fitted trend actually moved across the window, which is
    # what decides both the direction and whether it is worth
    # extrapolating.
    rise = (use_slope * span) if assumption == "linear" else (
        math.exp(use_intercept + use_slope * xs[-1])
        - math.exp(use_intercept))

    # Direction is reported (section 13.2), so it has to mean something.
    # A fitted slope is almost never exactly zero: on a flat feature with
    # ordinary noise it comes out around 1e-04, and calling that "rising"
    # puts a degrading machine on the screen where there is none. Movement
    # smaller than the rise gate is scatter, and scatter is steady.
    moved_enough = abs(rise) >= threshold * MIN_RISE_FRACTION
    verdict.direction = (
        ("rising" if use_slope > 0 else "falling") if moved_enough
        else "steady")

    if use_slope <= 0:
        verdict.reason = (
            f"RUL prediction not available. {feature_name} is not rising -- "
            f"it is {verdict.direction} over the {span:.0f} days on record. "
            f"A feature that is not degrading has no failure date, and "
            f"extrapolating one from a flat trend produces a confident "
            f"number with nothing behind it.")
        return verdict

    latest = ys[-1]
    if not moved_enough:
        verdict.reason = (
            f"RUL prediction not available. {feature_name} has risen by "
            f"{rise:.4g} across {span:.0f} days, less than "
            f"{MIN_RISE_FRACTION:.0%} of the {threshold:.4g} threshold. "
            f"Dividing by a slope this shallow produces an estimate in the "
            f"thousands of days, which is a way of saying nothing is "
            f"happening rather than a prediction.")
        return verdict

    if use_quality < MIN_FIT_QUALITY:
        verdict.reason = (
            f"RUL prediction not available. The {assumption} fit explains "
            f"only {use_quality:.0%} of the variation in {feature_name}, "
            f"under the {MIN_FIT_QUALITY:.0%} needed. This is scatter with "
            f"a direction rather than a trend, and extrapolating it would "
            f"put a date on noise.")
        return verdict

    if latest >= threshold:
        verdict.available = True
        verdict.reliable = True
        verdict.days_low = 0.0
        verdict.days_high = 0.0
        verdict.confidence = "high"
        verdict.reason = (
            f"{feature_name} is already at or past the {threshold:.4g} "
            f"threshold. There is no remaining life to estimate -- this "
            f"machine is in the condition the threshold describes.")
        return verdict

    # Days from the last reading to the threshold, and the range around it.
    scatter = _scatter(xs, ys if assumption == "linear"
                       else [math.log(y) for y in ys],
                       use_slope, use_intercept)

    def days_to(target: float) -> Optional[float]:
        if assumption == "linear":
            return (target - use_intercept) / use_slope - xs[-1]
        if target <= 0:
            return None
        return (math.log(target) - use_intercept) / use_slope - xs[-1]

    centre = days_to(threshold)
    if centre is None or centre <= 0:
        verdict.reason = (
            "RUL prediction not available: the fitted trend does not reach "
            "the threshold in a meaningful direction.")
        return verdict

    # The band is the threshold plus and minus the residual scatter, which
    # widens the range when the trend is noisy instead of hiding it.
    high_target = (threshold + scatter if assumption == "linear"
                   else threshold * math.exp(scatter))
    low_target = (threshold - scatter if assumption == "linear"
                  else threshold * math.exp(-scatter))
    low = days_to(low_target)
    high = days_to(high_target)
    bounds = sorted(d for d in (low, centre, high) if d is not None and d > 0)

    verdict.days_low = round(bounds[0], 1)
    verdict.days_high = round(bounds[-1], 1)

    if verdict.days_low > MAX_HORIZON_DAYS:
        verdict.available = False
        verdict.reason = (
            f"RUL prediction not available: the trend reaches the threshold "
            f"in about {verdict.days_low:.0f} days, far beyond the "
            f"{MAX_HORIZON_DAYS:.0f}-day horizon this extrapolation can "
            f"support from {span:.0f} days of data. The honest reading is "
            f"that nothing is currently degrading fast enough to date.")
        return verdict

    verdict.available = True
    confidence = ("high" if use_quality >= 0.85 and len(points) >= 60
                  else "medium" if use_quality >= 0.7
                  else "low")

    # A good fit and a wide range are not contradictory -- the line can
    # describe the scatter faithfully and still put the threshold anywhere
    # across a month. The width is what an engineer plans around, so it
    # caps the confidence.
    midpoint = (verdict.days_low + verdict.days_high) / 2.0
    width = ((verdict.days_high - verdict.days_low) / midpoint
             if midpoint > 0 else 0.0)
    if width > VERY_WIDE_RANGE_FRACTION:
        confidence = "low"
    elif width > WIDE_RANGE_FRACTION and confidence == "high":
        confidence = "medium"
    verdict.confidence = confidence
    verdict.range_width = round(width, 3)
    # Reliable only when the platform is not also missing half its inputs.
    verdict.reliable = (verdict.confidence in ("medium", "high")
                        and len(missing) <= 2)

    verdict.reason = (
        f"Estimated remaining life {verdict.days_low:.0f} to "
        f"{verdict.days_high:.0f} days. Confidence: {verdict.confidence}. "
        f"{feature_name} has been rising {assumption}ly over {span:.0f} days "
        f"of data ({len(points)} readings), at {use_slope:.4g} per day, and "
        f"the fit explains {use_quality:.0%} of the variation. The range is "
        f"the scatter around that trend, not a margin of safety."
        + (f" Treat it as indicative rather than reliable: "
           f"{len(missing)} of section 13.1's inputs are not available on "
           f"this platform." if not verdict.reliable else ""))
    return verdict
