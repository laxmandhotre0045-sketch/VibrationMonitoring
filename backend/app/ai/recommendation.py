"""Which way it is going, how urgent it is, and what to do — VIK-057 gaps.

Requirement 9.2 asks for nine things beside every suspected fault. Six were
built: name, family, severity, confidence, evidence, and the plots that
would prove it. Three were not, and they are the three a maintenance
engineer actually reads first:

  * **Trend direction** -- is this getting worse, holding, or recovering?
  * **Urgency** -- is this a shutdown or an inspection?
  * **Recommended action** -- what do I actually do?

Requirement 14 asks for the last two again, in its own words: "How urgent is
it?" and "What should the analyst do next?". A finding that answers neither
is a diagnosis nobody can act on, which is the same as no diagnosis.

**Urgency is capped by how well the machine can be seen.** This is the only
decision in this module that is not obvious, and it is the important one. A
stage of "critical" computed from an untrustworthy capture, or from a rule
the engine is barely confident in, must not produce the words "stop the
machine". Shutting down a healthy line costs real money and, worse, it
costs belief: the fourth false shutdown is the one after which nobody acts
on the third real one. So the stage proposes and the evidence disposes --
the ceiling is stated in the same breath as the recommendation, and a
capped urgency says what would lift it.

**Direction needs three sightings, not two.** Two readings always have a
direction; it is just noise half the time. Below three this returns
"unknown" rather than "steady", because a fault nobody has watched long
enough is not a fault that is holding steady.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

#: Stage order, matching `app.ai.severity.STAGES` and the migration's check
#: constraint. Repeated rather than imported so this module stays usable
#: without a database session.
STAGES = ("normal", "watch", "early_fault_suspected", "developing",
          "severe", "critical")

#: Urgency levels, least to most. `immediate` is the only one that carries a
#: shutdown recommendation, and it is deliberately hard to reach.
URGENCY = ("none", "monitor", "inspect_when_convenient", "inspect_soon",
           "plan_maintenance", "immediate")

#: What each stage proposes, before any cap is applied.
STAGE_URGENCY = {
    "normal": "none",
    "watch": "monitor",
    "early_fault_suspected": "inspect_when_convenient",
    "developing": "inspect_soon",
    "severe": "plan_maintenance",
    "critical": "immediate",
}

#: Engine confidence below which urgency cannot exceed "inspect_soon".
#:
#: A rule that matched weakly is a reason to go and look, never a reason to
#: stop a machine. 0.5 is where the fault engine's own score stops being
#: dominated by a single matched order.
CONFIDENCE_FOR_ACTION = 0.5

#: Confidence below which nothing above "monitor" is proposed at all.
CONFIDENCE_FOR_INSPECTION = 0.25

#: Highest urgency allowed when the capture itself cannot be trusted.
UNTRUSTWORTHY_CEILING = "inspect_when_convenient"

#: Highest urgency allowed when the spectrum could not separate the orders
#: the diagnosis rests on. The finding may still be right -- it just cannot
#: be told apart from an ordinary harmonic, so it earns a look, not a
#: shutdown.
UNRESOLVED_CEILING = "inspect_soon"

#: Sightings needed before a direction means anything.
MIN_SIGHTINGS_FOR_DIRECTION = 3

#: How much of the score must change before it counts as movement rather
#: than noise. The engine's scores sit on 0-1, and run-to-run wobble on a
#: steady machine is a couple of points.
DIRECTION_MARGIN = 0.05

#: How many scores to keep on a finding. Enough to see a trend, few enough
#: that the row stays small.
HISTORY_LENGTH = 12

URGENCY_WORDS = {
    "none": "No action.",
    "monitor": "Keep watching; no action needed yet.",
    "inspect_when_convenient": "Look at it when convenient.",
    "inspect_soon": "Inspect at the next opportunity.",
    "plan_maintenance": "Plan maintenance; do not leave it to run "
                        "indefinitely.",
    "immediate": "Act now. This is the level at which stopping the machine "
                 "is on the table.",
}


@dataclass
class Direction:
    """Which way a finding is moving, and whether that is knowable yet."""
    direction: str = "unknown"      # rising | steady | falling | unknown
    change: Optional[float] = None
    reason: str = ""

    @property
    def rising(self) -> bool:
        return self.direction == "rising"

    def as_dict(self) -> dict[str, Any]:
        return {"direction": self.direction, "change": self.change,
                "reason": self.reason}


def direction_of(scores: Sequence[float]) -> Direction:
    """Read a trend off a finding's score history.

    Compares where it started with where it is now, and checks that the
    steps in between mostly agree. Comparing the mean of two halves was the
    obvious approach and is wrong on short runs: with four readings each
    half is two, the median of two is their mean, and one spike counts in
    full.
    """
    values = [float(s) for s in scores if s is not None]
    if len(values) < MIN_SIGHTINGS_FOR_DIRECTION:
        return Direction(
            reason=f"Seen {len(values)} time(s). A direction needs at least "
                   f"{MIN_SIGHTINGS_FOR_DIRECTION} readings -- two always "
                   f"have a direction and it is noise half the time. This is "
                   f"not the same as holding steady.")

    change = values[-1] - values[0]
    steps = [b - a for a, b in zip(values, values[1:])]
    up = sum(1 for s in steps if s > 0)
    down = sum(1 for s in steps if s < 0)

    if change > DIRECTION_MARGIN and up >= down:
        return Direction(
            "rising", round(change, 3),
            f"The score has gone from {values[0]:.2f} to {values[-1]:.2f} "
            f"over {len(values)} readings, and {up} of the {len(steps)} "
            f"steps between them were upward. It is getting worse.")
    if change < -DIRECTION_MARGIN and down >= up:
        return Direction(
            "falling", round(change, 3),
            f"The score has fallen from {values[0]:.2f} to {values[-1]:.2f} "
            f"over {len(values)} readings. It is recovering, or whatever "
            f"caused it has been dealt with.")
    return Direction(
        "steady", round(change, 3),
        f"The score has moved from {values[0]:.2f} to {values[-1]:.2f} over "
        f"{len(values)} readings, which is inside the {DIRECTION_MARGIN:.2f} "
        f"margin that separates movement from run-to-run wobble.")


def _cap(proposed: str, ceiling: str) -> str:
    return proposed if URGENCY.index(proposed) <= URGENCY.index(ceiling) \
        else ceiling


@dataclass
class Recommendation:
    urgency: str = "none"
    proposed: str = "none"
    capped: bool = False
    shutdown_advised: bool = False
    headline: str = ""
    action: str = ""
    caps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"urgency": self.urgency, "proposed_urgency": self.proposed,
                "capped": self.capped,
                "shutdown_advised": self.shutdown_advised,
                "headline": self.headline, "action": self.action,
                "caps": self.caps}


def recommend(
    *,
    stage: str,
    confidence: float,
    direction: Optional[Direction] = None,
    resolution_usable: Optional[bool] = None,
    capture_trustworthy: Optional[bool] = None,
    action_now: Optional[str] = None,
    action_planned: Optional[str] = None,
) -> Recommendation:
    """How urgent this finding is, and what to do about it.

    `action_now` and `action_planned` come from the seeded recommendation
    table, so the words an engineer reads can be corrected without a deploy.
    """
    proposed = STAGE_URGENCY.get(stage, "monitor")
    result = Recommendation(proposed=proposed, urgency=proposed)
    caps: list[str] = []

    if confidence < CONFIDENCE_FOR_INSPECTION:
        result.urgency = _cap(result.urgency, "monitor")
        caps.append(
            f"The engine is only {confidence:.0%} confident in this match, "
            f"below the {CONFIDENCE_FOR_INSPECTION:.0%} at which it is worth "
            f"sending anyone to look.")
    elif confidence < CONFIDENCE_FOR_ACTION:
        result.urgency = _cap(result.urgency, "inspect_soon")
        caps.append(
            f"Engine confidence is {confidence:.0%}, below the "
            f"{CONFIDENCE_FOR_ACTION:.0%} needed before a finding justifies "
            f"planned maintenance. A weak match is a reason to look, not a "
            f"reason to stop a machine.")

    if capture_trustworthy is False:
        result.urgency = _cap(result.urgency, UNTRUSTWORTHY_CEILING)
        caps.append(
            "The capture this rests on did not pass its own quality checks, "
            "so the finding may be describing the instrument rather than the "
            "machine.")

    if resolution_usable is False:
        result.urgency = _cap(result.urgency, UNRESOLVED_CEILING)
        caps.append(
            "The spectrum cannot separate the frequencies this diagnosis "
            "turns on from ordinary shaft harmonics, so the finding may be a "
            "perfectly normal machine. It earns a look, not a shutdown.")
    elif resolution_usable is None:
        result.urgency = _cap(result.urgency, UNRESOLVED_CEILING)
        caps.append(
            "Whether the spectrum could separate the diagnostic frequencies "
            "was not recorded, so it cannot be assumed that it could.")

    if direction is not None and direction.direction == "falling":
        result.urgency = _cap(result.urgency, "monitor")
        caps.append(
            "The finding is weakening reading by reading, which usually "
            "means it has already been dealt with.")

    result.caps = caps
    result.capped = result.urgency != proposed
    result.shutdown_advised = result.urgency == "immediate"

    result.headline = URGENCY_WORDS.get(result.urgency, "")
    if result.capped:
        result.headline += (
            f" The fault is at stage '{stage.replace('_', ' ')}', which on "
            f"its own would mean \"{URGENCY_WORDS[proposed].rstrip('.')}\" "
            f"-- held back because: " + " ".join(caps))

    # The words an engineer acts on.
    parts: list[str] = []
    if result.urgency in ("plan_maintenance", "immediate") and action_now:
        parts.append(action_now)
    elif action_planned:
        parts.append(action_planned)
    elif action_now:
        parts.append(action_now)

    if direction is not None and direction.rising:
        parts.append("It is getting worse reading by reading, so the "
                     "interval before it is looked at matters.")
    if result.capped:
        parts.append("Before escalating this further, close the gap that is "
                     "holding it back rather than overriding it.")

    result.action = " ".join(parts) or (
        "No action beyond continuing to monitor.")
    return result
