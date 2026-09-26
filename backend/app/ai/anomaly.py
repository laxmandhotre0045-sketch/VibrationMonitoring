"""How unusual a reading is, from 0 to 100 — VIK-042.

The first machine learning this platform has had. Everything before it
measured things; this is the part that says whether a measurement is
surprising.

**Unknown is not zero, and this is the whole ticket.** A feature with no
learned normal cannot be scored, and the only honest output is nothing at
all. Writing 0 would say "perfectly ordinary" about a reading nothing has
ever been compared to -- which makes an unmonitored machine score better
than a monitored healthy one, and puts it at the bottom of every priority
list precisely because nobody is watching it. `Score.scored` is False and
`Score.value` is None, and every caller has to deal with that.

**Robust statistics, because the baseline is.** The normal is a median and a
MAD-derived sigma built from captures nobody inspected. Scoring against a
mean and a standard deviation would reintroduce, at the last step, exactly
the sensitivity to one bad capture that VIK-025 spent its effort removing.

**The bands come from the requirement, and the map is anchored to sigma.**
0-20 normal, 21-40 slight, 41-60 watch, 61-75 abnormal, 76-90 high
priority, 91-100 critical. A reading inside one sigma of normal is normal; a
reading at three sigma is abnormal, which is where conventional practice
puts it; six sigma and beyond is critical. The map between them is
piecewise linear, so a score of 61 always means the same distance from
normal whatever the feature or the machine -- which is what makes two
machines comparable at all.

**The score is not the confidence.** How far out a reading is and how much
the comparison is worth are different facts, and multiplying them together
would hide both: a 90 from a baseline of thirteen captures and a 45 from a
baseline of two hundred are not the same finding and must not collapse to
the same number. They travel side by side.

**Direction is kept.** `z` is signed. A bearing band that collapses is as
interesting as one that climbs, and folding it into a magnitude loses the
difference between a machine getting worse and a sensor falling off.

What this does not do: VIK-043's Isolation Forest and PCA residual are
separate methods, and `contributions` is shaped to hold them beside this
one rather than averaged into it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: Band lower bounds, from the requirement. A score of exactly 21 is
#: "slight", 41 is "watch", and so on.
BANDS: tuple[tuple[int, str], ...] = (
    (0, "normal"),
    (21, "slight"),
    (41, "watch"),
    (61, "abnormal"),
    (76, "high"),
    (91, "critical"),
)

#: (sigma, score) anchors. Between them the map is linear, above the last it
#: is clamped.
#:
#: One sigma is the top of normal: on a well-behaved feature about two
#: thirds of healthy captures sit inside it, and calling those anything but
#: normal would bury a real finding under them. Three sigma is where
#: conventional practice calls a reading abnormal, so it lands at the bottom
#: of that band rather than in the middle of it. Six is where the baseline's
#: own contamination check draws its line, so beyond it the reading is not
#: merely extreme -- it is outside the population the normal describes.
SIGMA_ANCHORS: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (1.0, 20.0),
    (2.0, 40.0),
    (3.0, 61.0),
    (4.5, 76.0),
    (6.0, 91.0),
    (9.0, 100.0),
)

#: A feature whose baseline has no spread cannot produce a z-score: every
#: reading is either exactly the median or infinitely far from it. It
#: happens on a quantisation-limited channel where the same value repeats,
#: and the honest answer is that the feature is unscorable, not that it is
#: infinitely anomalous.
MIN_SIGMA = 1e-12


def band_for(score: float) -> str:
    label = BANDS[0][1]
    for lower, name in BANDS:
        if score >= lower:
            label = name
    return label


def score_from_sigma(sigma_distance: float) -> float:
    """Map a distance in robust sigmas onto 0-100."""
    distance = abs(float(sigma_distance))
    anchors = SIGMA_ANCHORS
    # Stated up front rather than left to the fallthrough below, which
    # reaches the same answer. Redundant, and deliberately: the ceiling is
    # the one property of this map a reader most needs to be sure of, and
    # finding it only by exhausting a loop is not being sure of it.
    if distance >= anchors[-1][0]:
        return 100.0
    for (low_s, low_v), (high_s, high_v) in zip(anchors, anchors[1:]):
        if distance <= high_s:
            span = high_s - low_s
            if span <= 0:
                return high_v
            fraction = (distance - low_s) / span
            return round(low_v + fraction * (high_v - low_v), 1)
    return 100.0


@dataclass
class Score:
    """How unusual one reading was, and how much that judgement is worth."""
    feature_code: str
    channel: int
    value: Optional[float] = None          # the 0-100 score
    band: Optional[str] = None
    scored: bool = False
    z: Optional[float] = None
    reading: Optional[float] = None
    confidence: float = 0.0
    baseline_version: Optional[int] = None
    mode_id: Optional[str] = None
    reason: str = ""
    contributions: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_code": self.feature_code, "channel": self.channel,
            "score": self.value, "band": self.band, "is_scored": self.scored,
            "z_score": self.z, "reading": self.reading,
            "confidence": self.confidence,
            "baseline_version": self.baseline_version,
            "mode_id": self.mode_id, "reason": self.reason,
            "contributions": self.contributions,
        }


def _unscored(code: str, channel: int, reading: Optional[float],
              reason: str, **kw: Any) -> Score:
    return Score(feature_code=code, channel=channel, reading=reading,
                 scored=False, value=None, band=None, reason=reason, **kw)


def score_feature(
    feature_code: str,
    channel: int,
    reading: Optional[float],
    baseline: Optional[dict[str, Any]],
    *,
    quality_factor: float = 1.0,
    informational: bool = False,
) -> Score:
    """Score one feature on one channel against its learned normal.

    `quality_factor` is the capture's own trustworthiness, from VIK-022. It
    lowers the confidence rather than the score: a clipped capture that
    reads eight sigma out really is eight sigma out, and pretending
    otherwise would hide a genuine clipping fault. What it changes is how
    much anyone should act on it.
    """
    if reading is None:
        return _unscored(feature_code, channel, None,
                         "The feature was not computed for this capture.")

    if informational:
        return _unscored(
            feature_code, channel, reading,
            "This feature describes the signal rather than the machine's "
            "health, so a distance from normal on it is not evidence of "
            "anything. Recorded, not scored.")

    if not baseline:
        return _unscored(
            feature_code, channel, reading,
            "No normal has been learned for this feature, so there is "
            "nothing to compare the reading against. Reported as unscored "
            "rather than as zero: a reading nothing has been compared to is "
            "not a reading that looks ordinary.")

    sigma = baseline.get("robust_sigma")
    median = baseline.get("median")
    if median is None or sigma is None:
        return _unscored(feature_code, channel, reading,
                         "The stored baseline is incomplete.")

    sigma = float(sigma)
    median = float(median)
    if sigma <= MIN_SIGMA:
        return _unscored(
            feature_code, channel, reading,
            f"The learned normal for this feature has no spread -- every "
            f"capture behind it read {median:g}. That happens on a channel "
            f"whose resolution is too coarse to show variation, and it makes "
            f"every reading either exactly normal or infinitely abnormal. "
            f"Neither is a useful answer.",
            baseline_version=baseline.get("baseline_version"),
            mode_id=(str(baseline["mode_id"])
                     if baseline.get("mode_id") else None))

    z = (float(reading) - median) / sigma
    value = score_from_sigma(z)

    # The baseline's own worth, and the capture's, multiplied. Both are
    # already 0-1 and both are reasons to act less firmly on the same
    # number.
    baseline_confidence = baseline.get("confidence")
    confidence = float(baseline_confidence if baseline_confidence is not None
                       else 1.0) * float(quality_factor)

    direction = "above" if z >= 0 else "below"
    reason = (f"{feature_code} on channel {channel} read {reading:.5g} "
              f"against a learned normal of {median:.5g}, which is "
              f"{abs(z):.1f} robust sigma {direction} it.")
    if baseline.get("mixed_population"):
        reason += (" The baseline's percentiles describe more than one "
                   "population, though its median and spread are usable.")

    return Score(
        feature_code=feature_code, channel=channel,
        value=value, band=band_for(value), scored=True,
        z=round(z, 3), reading=float(reading),
        confidence=round(min(max(confidence, 0.0), 1.0), 3),
        baseline_version=baseline.get("baseline_version"),
        mode_id=(str(baseline["mode_id"]) if baseline.get("mode_id") else None),
        reason=reason,
        contributions={"robust_z": {"z": round(z, 3), "score": value}},
    )


def score_capture(
    features: dict[tuple[int, str], float],
    baselines: dict[tuple[int, str], dict[str, Any]],
    *,
    quality_by_channel: Optional[dict[int, float]] = None,
    informational: Optional[set[str]] = None,
) -> list[Score]:
    """Score every feature in one capture."""
    quality = quality_by_channel or {}
    skip = informational or set()
    scores = []
    for (channel, code), reading in sorted(features.items()):
        scores.append(score_feature(
            code, channel, reading, baselines.get((channel, code)),
            quality_factor=quality.get(channel, 1.0),
            informational=code in skip,
        ))
    return scores


def worst(scores: list[Score]) -> Optional[Score]:
    """The most unusual scored reading, or None if nothing could be scored.

    None rather than a zero-score stand-in: a capture where nothing could be
    scored has no worst feature, and inventing one at the bottom of the
    range would report it as the healthiest thing on the machine.
    """
    scored = [s for s in scores if s.scored and s.value is not None]
    return max(scored, key=lambda s: s.value) if scored else None
