"""How far along a fault is, on a scale of six — VIK-054.

Normal, Watch, Early Fault Suspected, Developing, Severe, Critical. The
ticket's one hard rule is the whole design: **a stage rises only under the
persistence conditions -- never on one reading.**

That rule exists because a severity scale is read as a prediction. "Severe"
tells somebody to plan an outage; if a single noisy capture can produce it,
the platform will send people to healthy machines and they will stop
believing the fourth one. Phase 2 already built the persistence machinery
for alarms, and this is the same idea applied to the diagnosis: a stage is
a claim about the machine over time, not about the last two minutes.

**Rising is slow, falling is immediate.** A stage climbs one step at a time
and only when the evidence has repeated; it drops as soon as the evidence
stops. The asymmetry is deliberate and it is not symmetry-for-its-own-sake
that is wanted here: being slow to alarm protects against noise, but being
slow to stand down means a machine that was repaired goes on reading
"severe" for a week, and the next real finding on it is ignored.

**A stage never rises above what the evidence can support.** The engine's
own confidence caps it. A rule that fired at 0.4 confidence cannot produce
"critical" however many times it repeats -- repetition of a weak signal is
a weak signal seen often, not a strong one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

#: The six stages, lowest first. Position in this tuple is the severity
#: number, so `STAGES.index(stage)` is the 0-5 the ticket asks for.
STAGES: tuple[str, ...] = (
    "normal",
    "watch",
    "early_fault_suspected",
    "developing",
    "severe",
    "critical",
)

LABELS: dict[str, str] = {
    "normal": "Normal",
    "watch": "Watch",
    "early_fault_suspected": "Early fault suspected",
    "developing": "Developing",
    "severe": "Severe",
    "critical": "Critical",
}

#: The engine score at or above which each stage becomes reachable.
#:
#: These are ceilings on what the evidence allows, not triggers. A score of
#: 0.8 makes "severe" reachable; it takes repetition to actually get there.
SCORE_CEILING: tuple[tuple[float, str], ...] = (
    (0.85, "critical"),
    (0.70, "severe"),
    (0.50, "developing"),
    (0.30, "early_fault_suspected"),
    (0.15, "watch"),
    (0.00, "normal"),
)

#: How many times a finding must have been seen before each stage is
#: allowed. Index matches STAGES.
#:
#: "Watch" needs two sightings, because one is the noise this whole scale
#: exists to absorb. Each step up costs more, and "critical" wants eight --
#: on a two-minute capture interval that is about a quarter of an hour of
#: the fault being continuously present, which is a low bar in time and a
#: high one in evidence.
SIGHTINGS_REQUIRED: tuple[int, ...] = (0, 2, 3, 4, 6, 8)

#: Confidence below which a stage cannot be reached at all. Repetition of a
#: weak signal is a weak signal seen often.
CONFIDENCE_REQUIRED: tuple[float, ...] = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6)


@dataclass
class StageVerdict:
    """What stage a finding is at, and why it is not higher."""
    stage: str = "normal"
    severity: int = 0
    previous: Optional[str] = None
    rose: bool = False
    fell: bool = False
    #: The highest stage the evidence would allow if it kept repeating.
    ceiling: str = "normal"
    reason: str = ""

    @property
    def label(self) -> str:
        return LABELS[self.stage]

    def as_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "severity": self.severity,
                "label": self.label, "previous": self.previous,
                "rose": self.rose, "fell": self.fell,
                "ceiling": self.ceiling, "reason": self.reason}


def ceiling_for(score: float, confidence: float) -> str:
    """The highest stage this evidence could ever justify.

    Both the score and the confidence cap it, and the lower cap wins. A
    confident reading of a weak pattern and a doubtful reading of a strong
    one are both limited, for different reasons.
    """
    by_score = "normal"
    for threshold, stage in SCORE_CEILING:
        if score >= threshold:
            by_score = stage
            break

    by_confidence = "normal"
    for index in range(len(STAGES) - 1, -1, -1):
        if confidence >= CONFIDENCE_REQUIRED[index]:
            by_confidence = STAGES[index]
            break

    return STAGES[min(STAGES.index(by_score), STAGES.index(by_confidence))]


def grade(
    *,
    score: float,
    confidence: float,
    times_seen: int,
    previous_stage: Optional[str] = None,
) -> StageVerdict:
    """Decide the stage for one finding.

    `times_seen` counts how many captures this finding has appeared in,
    including the current one.
    """
    previous = previous_stage if previous_stage in STAGES else None
    ceiling = ceiling_for(score, confidence)
    ceiling_index = STAGES.index(ceiling)

    # The highest stage repetition has earned so far.
    earned_index = 0
    for index in range(len(STAGES) - 1, -1, -1):
        if times_seen >= SIGHTINGS_REQUIRED[index]:
            earned_index = index
            break

    allowed_index = min(ceiling_index, earned_index)
    previous_index = STAGES.index(previous) if previous else 0

    if allowed_index > previous_index:
        # One step at a time. A finding that arrives already looking severe
        # still passes through the stages, because "severe" is a claim about
        # a fault that has been watched and is getting worse -- and arriving
        # at it in one capture is exactly the single reading this rule
        # exists to refuse.
        new_index = previous_index + 1
        rose, fell = True, False
    elif allowed_index < previous_index:
        # Straight down. Slow to stand down means a repaired machine reads
        # severe for a week, and the next real finding on it is ignored.
        new_index = allowed_index
        rose, fell = False, True
    else:
        new_index = previous_index
        rose = fell = False

    verdict = StageVerdict(
        stage=STAGES[new_index], severity=new_index, previous=previous,
        rose=rose, fell=fell, ceiling=ceiling)

    if fell:
        verdict.reason = (
            f"Dropped to {LABELS[verdict.stage].lower()} from "
            f"{LABELS[previous].lower()}: the evidence no longer supports "
            f"the higher stage. A stage falls as soon as its evidence does, "
            f"because a machine that has been repaired must stop reading as "
            f"faulty.")
    elif rose:
        verdict.reason = (
            f"Rose to {LABELS[verdict.stage].lower()} after "
            f"{times_seen} sighting(s). Stages climb one step at a time, so "
            f"a finding that arrives looking worse than this still has to be "
            f"watched into it.")
    elif allowed_index < ceiling_index:
        needed = SIGHTINGS_REQUIRED[min(previous_index + 1, len(STAGES) - 1)]
        verdict.reason = (
            f"Holding at {LABELS[verdict.stage].lower()}. The evidence would "
            f"allow {LABELS[ceiling].lower()}, but that needs {needed} "
            f"sightings and this has {times_seen}.")
    else:
        verdict.reason = (
            f"Holding at {LABELS[verdict.stage].lower()}, which is as far as "
            f"a score of {score:.2f} at {confidence:.2f} confidence reaches.")
    return verdict
