"""When a score becomes an alarm — VIK-044 and VIK-046.

A score says how unusual one reading was. An alarm says somebody should go
and look. Those are different claims and the gap between them is where
monitoring systems are won or lost: a platform that alarms on every high
score teaches its users to ignore it, and a platform ignored is worth less
than no platform, because it also carries the belief that the machine is
being watched.

**One reading is not evidence (VIK-044).** This pump produces a capture
every two minutes and scores 368 features on each. At three sigma, pure
chance puts roughly one reading in 370 past the line -- so about one
feature per capture, about seven hundred a day, every one of them a
healthy machine behaving normally. Alarming on those is not sensitivity, it
is arithmetic.

A real fault does not go away on the next capture. So an alarm requires the
same feature to stay past the line for several captures in a row, and the
run has to be consecutive: a feature that alarms, recovers, and alarms
again is doing something different from one that is steadily getting worse,
and the difference matters to whoever is deciding whether to stop the
machine.

**The profiles have to actually do something (VIK-046).** The requirement
asks for four sensitivity modes and they have been a label on a settings
page. Here they set the two numbers that decide whether a score becomes an
alarm -- how high, and for how long -- plus the confidence below which a
finding is held back. Conservative waits longer and demands more;
Early Warning reacts sooner and accepts less certainty, which is the right
trade for a critical machine and the wrong one for a spare pump.

**Confidence gates the alarm, not the score.** VIK-042 keeps how unusual a
reading is apart from how much the comparison is worth. This is where the
second number finally decides something: a 95 from a baseline of thirteen
captures does not wake anybody up. It is still recorded, and it still says
95 -- what it does not do is ring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

CONSERVATIVE = "conservative"
BALANCED = "balanced"
EARLY_WARNING = "early_warning"
EXPERT = "expert"

PROFILES = (CONSERVATIVE, BALANCED, EARLY_WARNING, EXPERT)

#: The default, and the one the requirement calls recommended.
DEFAULT_PROFILE = BALANCED


@dataclass(frozen=True)
class Sensitivity:
    """What a sensitivity profile actually changes.

    Four numbers, each of which moves the alarm rate in a direction somebody
    can reason about. Nothing here is a hidden fudge factor: a person
    choosing Early Warning is choosing to be told sooner and to be wrong
    more often, and these are the terms of that trade.
    """
    profile: str
    #: The 0-100 score at or above which a reading counts towards an alarm.
    #: 61 is the bottom of "abnormal" and 76 the bottom of "high priority",
    #: so the profiles differ by one band rather than by an arbitrary step.
    score_threshold: float
    #: Consecutive captures required before it rings. One is never enough --
    #: see the arithmetic above -- so even Early Warning waits for two.
    persistence: int
    #: Findings below this confidence are recorded and held back.
    min_confidence: float
    #: Days of history a baseline is built from. Conservative learns from a
    #: longer window, which makes its normal broader and its alarms rarer.
    baseline_days: Optional[int] = None

    def as_dict(self) -> dict[str, Any]:
        return {"profile": self.profile,
                "score_threshold": self.score_threshold,
                "persistence": self.persistence,
                "min_confidence": self.min_confidence,
                "baseline_days": self.baseline_days}


#: The three preset profiles. Expert is built from a person's own numbers
#: and so has no entry here.
PRESETS: dict[str, Sensitivity] = {
    # Non-critical machines. Waits for the high-priority band and four
    # captures in a row -- about eight minutes on this gateway -- and wants
    # a baseline it can rely on before it says anything at all.
    CONSERVATIVE: Sensitivity(CONSERVATIVE, 76.0, 4, 0.7, 90),
    # The recommended default: the abnormal band, three captures, and a
    # confidence floor that excludes a baseline built from a mixed
    # population, which halves confidence to 0.5.
    BALANCED: Sensitivity(BALANCED, 61.0, 3, 0.55, 60),
    # Critical machines. Reacts at the same band but on the second capture,
    # and accepts a thinner baseline -- being told early about a machine
    # that matters is worth being wrong more often.
    EARLY_WARNING: Sensitivity(EARLY_WARNING, 61.0, 2, 0.4, 30),
}

#: Bounds for the Expert profile. Wide enough to be useful, narrow enough
#: that nobody can configure the engine into saying nothing (a threshold of
#: 100 and a persistence of 50) or into alarming on everything (a threshold
#: of 0 and a persistence of 1), both of which look like a working setup.
EXPERT_BOUNDS = {
    "score_threshold": (21.0, 99.0),
    "persistence": (2, 20),
    "min_confidence": (0.0, 1.0),
    "baseline_days": (7, 3650),
}


def resolve(profile: Optional[str],
            overrides: Optional[dict[str, Any]] = None) -> Sensitivity:
    """The settings in force, from a profile name and any expert overrides.

    An unknown profile falls back to Balanced rather than raising: this is
    read on every capture, and a typo in a settings row must not stop a
    machine being monitored. It must not silently become the most sensitive
    setting either, which is why the fallback is the recommended default and
    not the most eager one.
    """
    name = (profile or DEFAULT_PROFILE).strip().lower()

    if name != EXPERT:
        return PRESETS.get(name, PRESETS[DEFAULT_PROFILE])

    base = PRESETS[BALANCED]
    values = {
        "score_threshold": base.score_threshold,
        "persistence": base.persistence,
        "min_confidence": base.min_confidence,
        "baseline_days": base.baseline_days,
    }
    for key, raw in (overrides or {}).items():
        if key not in EXPERT_BOUNDS or raw is None:
            continue
        low, high = EXPERT_BOUNDS[key]
        try:
            value = int(raw) if key in ("persistence", "baseline_days") else float(raw)
        except (TypeError, ValueError):
            continue
        values[key] = min(max(value, low), high)

    return Sensitivity(EXPERT, values["score_threshold"], values["persistence"],
                       values["min_confidence"], values["baseline_days"])


#: How much higher the recent half of a run must sit above its older half
#: before the finding counts as rising rather than merely sustained.
#:
#: Scores are noisy and the run is short, so a bare "newer > older" would
#: call half of all flat runs rising by coin flip. Three points on a 0-100
#: scale is small enough to catch a genuine climb early and large enough
#: that ordinary scatter does not trip it -- the flat run measured on this
#: platform spans about two.
RISING_MARGIN = 3.0


@dataclass
class Conditions:
    """The four things escalation needs, each recorded on its own.

    The ticket asks for exactly this: "Escalation needs repetition, a rising
    trend, steady speed and trustworthy data. Record each condition
    separately so the reason for escalating can be audited."

    Separately matters. Collapsed into one boolean, a finding that failed to
    escalate is indistinguishable from one that was never close, and nobody
    reviewing an alarm six months later can tell which of the four was
    missing -- which is the only question worth asking about it.
    """
    repetition: bool = False
    rising: bool = False
    steady_speed: bool = False
    trustworthy: bool = False

    @property
    def all_met(self) -> bool:
        return (self.repetition and self.rising
                and self.steady_speed and self.trustworthy)

    def missing(self) -> list[str]:
        return [name for name, met in (
            ("repetition", self.repetition), ("rising trend", self.rising),
            ("steady speed", self.steady_speed),
            ("trustworthy data", self.trustworthy)) if not met]

    def as_dict(self) -> dict[str, bool]:
        return {"repetition": self.repetition, "rising": self.rising,
                "steady_speed": self.steady_speed,
                "trustworthy": self.trustworthy}


@dataclass
class AlarmVerdict:
    """Whether one feature on one channel should ring, and why not if not."""
    channel: int
    feature_code: str
    alarming: bool = False
    #: All four conditions met: this is not merely high, it is getting worse
    #: on a machine that was running steadily, judged against a normal worth
    #: trusting. A stronger claim than `alarming`, and never a weaker one.
    escalating: bool = False
    conditions: Conditions = field(default_factory=Conditions)
    #: How many consecutive recent captures were at or above the threshold,
    #: newest first. The run, not the total.
    run_length: int = 0
    required: int = 0
    score: Optional[float] = None
    confidence: Optional[float] = None
    band: Optional[str] = None
    stability: Optional[str] = None
    held_back: Optional[str] = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"channel": self.channel, "feature_code": self.feature_code,
                "alarming": self.alarming, "escalating": self.escalating,
                "conditions": self.conditions.as_dict(),
                "run_length": self.run_length,
                "required": self.required, "score": self.score,
                "confidence": self.confidence, "band": self.band,
                "stability": self.stability,
                "held_back": self.held_back, "reason": self.reason}


def is_rising(scores: Sequence[Optional[float]], run_length: int) -> bool:
    """Whether the run is climbing rather than merely staying high.

    Two things must both hold: the newest reading sits at least
    `RISING_MARGIN` above the oldest in the run, and the run gets there
    without mostly going down on the way.

    The endpoint test is what rejects a spike in the middle. An earlier
    version compared the median of the recent half against the median of the
    older half, and the reasoning behind it was wrong: a run is often four
    captures long, so each half holds two values, and the median of two
    values is their mean. A single spike counted in full, and
    `[70, 99, 70, 70]` -- one bad capture in an otherwise flat run -- came
    back as a machine getting worse. Comparing the ends instead makes that
    run's answer depend on the two readings a spike is not sitting on.

    A run that was flat and has just jumped does count as rising, and that
    is deliberate: it has already satisfied repetition, so it is not one odd
    reading, and a step change is exactly the shape of a fault arriving.

    `scores` is newest first. Needs three captures to have a direction at
    all; below that the honest answer is that nobody can tell, which is
    False.
    """
    run = [s for s in scores[:run_length] if s is not None]
    if len(run) < 3:
        return False

    newest, oldest = run[0], run[-1]
    if newest - oldest < RISING_MARGIN:
        return False

    # Oldest to newest, so a step is positive when the reading grew.
    steps = [run[i] - run[i + 1] for i in range(len(run) - 1)]
    return sum(1 for step in steps if step >= 0) * 2 >= len(steps)


def consecutive_run(scores: Sequence[Optional[float]], threshold: float) -> int:
    """How many of the most recent captures were at or above the threshold.

    `scores` is newest first. An unscored capture (None) ends the run rather
    than being skipped over: a gap in the evidence is not evidence, and
    treating it as continuation would let a fault that was only ever seen
    twice, months apart, ring as though it had been steady throughout.
    """
    run = 0
    for score in scores:
        if score is None or score < threshold:
            break
        run += 1
    return run


def evaluate(
    channel: int,
    feature_code: str,
    recent_scores: Sequence[Optional[float]],
    *,
    confidence: Optional[float],
    band: Optional[str],
    sensitivity: Sensitivity,
    stability: Optional[str] = None,
) -> AlarmVerdict:
    """Decide whether this feature should ring, and whether it is escalating.

    `recent_scores` is newest first and includes the current capture.
    `stability` is how the shaft speed behaved during this capture, from the
    quality engine: "steady", "variable", "unstable", or None when nothing
    could assess it.

    **Ringing and escalating are separate claims.** An alarm needs the
    finding to have repeated and the baseline behind it to be worth
    trusting. Escalation needs those plus a rising trend and a steady speed
    -- it is the claim that the machine is getting worse, not merely that it
    is unusual.

    A rising trend is deliberately *not* required to ring. A bearing that
    jumped to 95 and stayed there is not rising and is exactly what an alarm
    is for; requiring a climb would silence the worst findings a machine can
    produce. Nor is steady speed: a fault found while the speed was moving
    is still a fault, and the moving speed is a reason to check the finding
    rather than to discard it. Both are recorded, both feed escalation, and
    neither is allowed to hide a real reading.
    """
    current = recent_scores[0] if recent_scores else None
    verdict = AlarmVerdict(
        channel=channel, feature_code=feature_code, score=current,
        confidence=confidence, band=band, stability=stability,
        required=sensitivity.persistence)

    if current is None:
        verdict.reason = (
            "Nothing could be scored for this feature on this capture, so "
            "there is nothing to alarm on. Not the same as a reading that "
            "came back normal.")
        return verdict

    verdict.run_length = consecutive_run(recent_scores,
                                         sensitivity.score_threshold)

    # All four conditions are computed whatever the outcome, because the
    # ticket asks for them to be recorded rather than merely consulted --
    # a finding that did not escalate has to say which of the four it was
    # short of.
    verdict.conditions = Conditions(
        repetition=verdict.run_length >= sensitivity.persistence,
        rising=is_rising(recent_scores, verdict.run_length),
        # None means nothing assessed it, which is not evidence that it was
        # steady. The steadiness check stands down on records too short to
        # judge, and treating that as steady would let a capture taken
        # during a speed change escalate as though the machine had been
        # holding one speed.
        steady_speed=stability == "steady",
        trustworthy=(confidence is None
                     or confidence >= sensitivity.min_confidence),
    )

    if verdict.run_length == 0:
        verdict.reason = (
            f"Scored {current:.0f}, below the {sensitivity.score_threshold:.0f} "
            f"this machine's {sensitivity.profile} setting acts on.")
        return verdict

    if not verdict.conditions.repetition:
        verdict.held_back = "not_persistent"
        verdict.reason = (
            f"Scored {current:.0f}, past the line, but only for "
            f"{verdict.run_length} capture(s) in a row and "
            f"{sensitivity.persistence} are needed. At this threshold chance "
            f"alone puts about one reading in a few hundred past the line, "
            f"so a single capture is arithmetic rather than evidence. "
            f"Recorded and watched.")
        return verdict

    if not verdict.conditions.trustworthy:
        verdict.held_back = "low_confidence"
        verdict.reason = (
            f"Scored {current:.0f} for {verdict.run_length} captures in a "
            f"row, which would ring -- but the comparison behind it carries "
            f"a confidence of {confidence:.2f}, under the "
            f"{sensitivity.min_confidence:.2f} this setting requires. The "
            f"reading is real and is recorded at {current:.0f}; what is in "
            f"doubt is the normal it was measured against.")
        return verdict

    verdict.alarming = True
    verdict.escalating = verdict.conditions.all_met
    verdict.reason = (
        f"Scored {current:.0f} ({band}) for {verdict.run_length} consecutive "
        f"captures, against the {sensitivity.persistence} required at this "
        f"machine's {sensitivity.profile} setting. A single high reading is "
        f"chance; this one has not gone away.")

    if verdict.escalating:
        verdict.reason += (
            " It is also climbing, on a machine whose speed held steady --"
            " so this is a fault getting worse rather than a level sitting"
            " high.")
    else:
        short = verdict.conditions.missing()
        verdict.reason += (
            f" Not escalated: {' and '.join(short)} "
            f"{'is' if len(short) == 1 else 'are'} missing, so this reads as"
            f" a sustained finding rather than a worsening one.")
    return verdict


def evaluate_capture(
    histories: dict[tuple[int, str], Sequence[Optional[float]]],
    current: dict[tuple[int, str], dict[str, Any]],
    sensitivity: Sensitivity,
    stability: Optional[str] = None,
) -> list[AlarmVerdict]:
    """Every feature in one capture, worst first.

    Escalating findings sort above merely ringing ones of the same score: a
    fault getting worse is the one to look at first, and a list ordered on
    score alone would bury it under a higher reading that has been flat for
    a month.
    """
    verdicts = []
    for key, scores in sorted(histories.items()):
        channel, code = key
        row = current.get(key) or {}
        verdicts.append(evaluate(
            channel, code, scores,
            confidence=row.get("confidence"), band=row.get("band"),
            sensitivity=sensitivity, stability=stability))
    verdicts.sort(key=lambda v: (not v.alarming, not v.escalating,
                                 -(v.score or 0.0)))
    return verdicts
