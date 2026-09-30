"""Which machine to walk to first — section 15.

Phase 3 can name a fault. This is the question a maintenance team actually
asks, which is not "what is wrong with this pump" but "of the fourteen
things the platform is telling me, which three matter today". A list that
does not rank itself is a list nobody reads past the top of.

Section 15.1 lists eleven inputs. They are not eleven versions of the same
thing, and the design turns on that:

**Severity says how bad it is; criticality and impact say how much that
matters.** A bearing going in a spare pump and the same bearing going in
the only boiler feed pump are the same fault and different problems, and no
amount of vibration analysis can tell them apart -- the difference is a
fact about the plant. So condition and consequence are scored separately
and then multiplied.

Measured rather than asserted, because the obvious claim to make here is
wrong: a *mild* fault on a safety-critical machine does not overtake a
*severe* one on a spare. It very nearly does -- the two land within a few
points of each other and in the same band -- which is the honest answer,
because a watch-level finding really is a watch-level finding whatever it
is bolted to. What consequence does is close almost the whole gap, so the
same fault on a critical machine and on a spare are three times apart.

**Confidence and data quality scale the whole thing down, never up.** A
platform that ranks by how alarming a reading looks will put its least
trustworthy readings at the top, because noise produces the most extreme
values. Every input that describes how well the machine can be seen acts as
a multiplier below one, so the top of the queue is the place the platform
is both most worried and most sure -- which is the only ordering an
engineer will keep believing after the first few false trips.

**Safety and production impact are unknown until somebody says.** They
cannot be derived from vibration. An unclassified machine is scored on a
neutral assumption and the queue says so, rather than quietly treating it
as harmless -- which would put every machine nobody has got round to
classifying at the bottom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

#: How much each input can contribute to the condition half of the score.
#: These sum to 1.0 so the condition score is readable as a percentage of
#: "as bad as this engine can say".
CONDITION_WEIGHTS = {
    "severity": 0.32,
    "anomaly": 0.19,
    "acceleration": 0.15,
    "persistence": 0.11,
    "alarms": 0.09,
    "symptoms": 0.07,
    # Section 15.1's "alarm history": how often this machine has rung at
    # all, as opposed to what is ringing now. Light, because the record is
    # mostly the reliability score's job and the feedback loop already
    # discounts a machine whose alarms keep being rejected -- weighting it
    # heavily here would charge the same history three times.
    "alarm_history": 0.07,
}

#: Historic alarm episodes at which that input saturates. A machine that
#: has alarmed thirty times and one that has alarmed sixty are both
#: machines with a long history of alarming.
ALARM_HISTORY_SATURATION = 20

#: Machine criticality, as the equipment record spells it.
CRITICALITY = {"critical": 1.0, "high": 0.8, "medium": 0.55, "low": 0.3}

#: Section 15.1's safety and production impact.
IMPACT = {"severe": 1.0, "high": 0.8, "medium": 0.55, "low": 0.3,
          "none": 0.15}

#: Used when nobody has classified the machine. Deliberately mid-scale
#: rather than low: an unclassified machine is unknown, and assuming a
#: pump is harmless because nobody filled the field in is how the one that
#: matters ends up at the bottom of the queue.
UNKNOWN_IMPACT = 0.5

#: Data quality multipliers. These only ever reduce.
QUALITY_FACTOR = {"good": 1.0, "limited": 0.9, "poor": 0.75, "blind": 0.55,
                  "high": 1.0, "medium": 0.9, "low": 0.7}

#: Below this confidence a finding cannot reach the top band however bad it
#: looks, because the thing most likely to produce an extreme reading is a
#: measurement problem.
CONFIDENCE_FLOOR = 0.35

#: Sightings at which persistence stops adding. A fault seen twenty times
#: is not twice as urgent as one seen ten times; it is the same fault.
PERSISTENCE_SATURATION = 10

#: Days since maintenance beyond which a machine is treated as due. Used
#: as a tie-breaker only -- it is context, not evidence of a fault.
MAINTENANCE_STALE_DAYS = 365.0

BANDS = ((75, "immediate"), (55, "high"), (35, "medium"), (15, "low"),
         (0, "watch"))


def band_for(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    for lower, label in BANDS:
        if score >= lower:
            return label
    return "watch"


@dataclass
class PriorityVerdict:
    score: Optional[float] = None
    band: str = "unknown"
    condition: Optional[float] = None
    consequence: Optional[float] = None
    trust: Optional[float] = None
    inputs: dict[str, Any] = field(default_factory=dict)
    #: Inputs nobody has supplied, named so they can be supplied.
    unknowns: list[str] = field(default_factory=list)
    reason: str = ""
    suppressed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "band": self.band,
                "condition": self.condition, "consequence": self.consequence,
                "trust": self.trust, "inputs": self.inputs,
                "unknowns": self.unknowns, "reason": self.reason,
                "suppressed": self.suppressed}


def _days_since(when: Optional[datetime]) -> Optional[float]:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0


def rank(
    *,
    severity: int,
    confidence: float,
    anomaly_score: Optional[float] = None,
    times_seen: int = 1,
    accelerating: Optional[bool] = None,
    direction: Optional[str] = None,
    symptom_count: int = 0,
    #: What is ringing on this machine now.
    active_alarms: int = 0,
    #: How many features have *ever* rung on it. Section 15.1 lists this
    #: separately from the live count and they answer different questions.
    alarm_history: int = 0,
    data_quality: Optional[str] = None,
    criticality: Optional[str] = None,
    safety_impact: Optional[str] = None,
    production_impact: Optional[str] = None,
    last_maintenance: Optional[datetime] = None,
    suppressed: bool = False,
) -> PriorityVerdict:
    """Score one finding for the triage queue.

    Returns a verdict rather than a number so the queue can explain itself.
    An engineer who cannot see why the third item outranks the fourth stops
    trusting the order, and then reads the list top to bottom anyway.
    """
    verdict = PriorityVerdict(suppressed=suppressed)
    unknowns: list[str] = []

    # ------------------------------------------------------- condition --
    parts: dict[str, float] = {}
    parts["severity"] = min(max(severity, 0), 5) / 5.0

    if anomaly_score is None:
        unknowns.append("No anomaly score: how unusual this machine is "
                        "against its own baseline is unknown, not low.")
        parts["anomaly"] = 0.0
    else:
        parts["anomaly"] = min(max(float(anomaly_score), 0.0), 100.0) / 100.0

    if accelerating is None:
        unknowns.append("Whether the deterioration is speeding up could not "
                        "be established from the readings available.")
        parts["acceleration"] = 0.0
    else:
        parts["acceleration"] = 1.0 if accelerating else (
            0.45 if direction == "rising" else 0.0)

    parts["persistence"] = min(times_seen, PERSISTENCE_SATURATION) / \
        PERSISTENCE_SATURATION
    parts["alarms"] = min(active_alarms, 3) / 3.0
    parts["symptoms"] = min(symptom_count, 5) / 5.0
    parts["alarm_history"] = (
        min(alarm_history, ALARM_HISTORY_SATURATION)
        / ALARM_HISTORY_SATURATION)

    condition = sum(parts[k] * w for k, w in CONDITION_WEIGHTS.items())

    # ----------------------------------------------------- consequence --
    crit = CRITICALITY.get((criticality or "").strip().lower())
    if crit is None:
        unknowns.append("Machine criticality is not recorded.")
        crit = UNKNOWN_IMPACT

    safety = IMPACT.get((safety_impact or "").strip().lower())
    if safety is None:
        unknowns.append(
            "Safety impact is not recorded. It cannot be worked out from "
            "vibration -- somebody has to say whether this machine failing "
            "can hurt anyone -- so it is scored as unknown rather than as "
            "safe.")
        safety = UNKNOWN_IMPACT

    production = IMPACT.get((production_impact or "").strip().lower())
    if production is None:
        unknowns.append(
            "Production impact is not recorded, so what this machine "
            "stopping would cost is unknown rather than nothing.")
        production = UNKNOWN_IMPACT

    # The worst of the three leads, with the others able to lift it. A
    # machine that is a safety problem is a safety problem whatever its
    # production role, and averaging is how that gets diluted away.
    consequence = max(crit, safety, production) * 0.75 + \
        (crit + safety + production) / 3.0 * 0.25

    # ---------------------------------------------------------- trust ---
    quality = QUALITY_FACTOR.get((data_quality or "").strip().lower())
    if quality is None:
        unknowns.append("Data quality for this machine is not recorded.")
        quality = 0.8
    trust = quality * (0.5 + 0.5 * min(max(confidence, 0.0), 1.0))

    score = condition * consequence * trust * 100.0

    # Maintenance history as a tie-breaker, never as evidence of a fault.
    days = _days_since(last_maintenance)
    if days is None:
        unknowns.append("No maintenance date on record.")
    elif days > MAINTENANCE_STALE_DAYS:
        score *= 1.05
        parts["maintenance_overdue_days"] = round(days, 0)

    verdict.condition = round(condition, 4)
    verdict.consequence = round(consequence, 4)
    verdict.trust = round(trust, 4)
    verdict.score = round(min(score, 100.0), 1)
    verdict.band = band_for(verdict.score)

    # A finding the engine is barely confident in cannot head the queue,
    # whatever the arithmetic says.
    #
    # Written as an invariant rather than a correction, deliberately. The
    # trust multiplier already holds such a finding under the top band --
    # with confidence below the floor the score cannot reach it -- so a
    # guard that only fires when the band *is* "immediate" is unreachable
    # code that would quietly become reachable the first time somebody
    # retunes a weight. Stating it unconditionally means the rule survives
    # the arithmetic changing underneath it.
    if confidence < CONFIDENCE_FLOOR:
        if BANDS[0][1] == verdict.band:
            verdict.band = BANDS[1][1]
        unknowns.append(
            f"Cannot lead the queue: engine confidence is {confidence:.0%}, "
            f"under the {CONFIDENCE_FLOOR:.0%} floor. The most extreme "
            f"readings are the ones most likely to be measurement problems, "
            f"so a queue that ranks purely by how alarming a number looks "
            f"puts its least trustworthy findings on top.")

    if suppressed:
        verdict.band = "suppressed"

    verdict.inputs = {k: round(v, 4) for k, v in parts.items()}
    verdict.unknowns = unknowns

    leading = max(CONDITION_WEIGHTS, key=lambda k: parts.get(k, 0.0) *
                  CONDITION_WEIGHTS[k])
    verdict.reason = (
        f"Priority {verdict.score:.0f} of 100 ({verdict.band}). Condition "
        f"scores {condition:.2f}, led by {leading.replace('_', ' ')}; "
        f"consequence {consequence:.2f} from criticality, safety and "
        f"production impact; and the whole is scaled by {trust:.2f} for how "
        f"well this machine can be seen and how sure the engine is."
        + (f" {len(unknowns)} input(s) were not available and are listed "
           f"rather than assumed." if unknowns else ""))
    if suppressed:
        verdict.reason = ("Muted by an analyst, so it is kept out of the "
                          "queue rather than ranked. " + verdict.reason)
    return verdict


def order(verdicts: Sequence[tuple[Any, PriorityVerdict]]
          ) -> list[tuple[int, Any, PriorityVerdict]]:
    """Rank a set of scored findings, worst first. Suppressed ones sink.

    Returns the rank alongside each, because section 15.2 asks for "Rank"
    as a field -- and a position in a list is not one, since the list can be
    filtered or paged and the number has to survive that.
    """
    ordered = sorted(
        verdicts,
        key=lambda pair: (pair[1].suppressed, -(pair[1].score or 0.0)))
    return [(i, item, verdict)
            for i, (item, verdict) in enumerate(ordered, start=1)]
