"""A health score that is a measurement rather than a restatement — VIK-055.

What this replaces is a three-entry lookup: normal was 100, warning 60,
critical 20. That is not a score, it is the status written in a different
font. It cannot separate a machine that has been at warning for ten minutes
from one that has been there for six weeks, it moves in steps of forty, and
its 100 is indistinguishable from the 100 of a machine nobody has ever
managed to take a reading from.

The ticket lists eight inputs -- severity, unusualness, symptoms, trend,
alarms, data quality, criticality and history. Three design decisions carry
most of the weight.

**Poor data lowers the ceiling, never the score.** This is the whole
platform's rule applied to a number. A machine with no baseline, or whose
spectrum cannot resolve its own bearing frequencies, must not be reported
at 100 -- not because anything is wrong with it, but because nobody has
looked hard enough to say. So data quality caps what the score is allowed to
claim rather than deducting from it. A machine we can barely see tops out
around 70 with "the instrument cannot see far enough to say better", which
is a different sentence from "this machine is at 70 because of a fault".

**Penalties combine so the worst one dominates.** Adding them up means four
mild concerns outrank one severe fault, and a machine at critical with a
handful of small observations goes below zero and has to be clamped -- which
silently throws away the difference between bad and much worse. Combining
them as independent chances of ill health keeps every contribution visible,
lets the worst one lead, and cannot leave the scale.

**Criticality changes the priority, not the condition.** A spare pump and a
boiler feed pump in identical mechanical condition are in identical
mechanical condition. Letting criticality move the health score means the
number answers two questions at once and cannot be checked against either.
So it is reported, and it drives `priority` -- what to do first -- while
`score` stays a statement about the machine.

Every deduction carries the sentence that produced it. A score nobody can
take apart is the lookup table again, with more decimal places.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

#: Weight of each input in the combined penalty. The weight is the most a
#: single input can take off a perfect score on its own, before the others
#: are combined with it.
#:
#: Severity leads because a named fault at a confirmed stage is the
#: strongest statement the platform makes. Unusualness is next and
#: deliberately below it: a high anomaly score says this capture is unlike
#: the baseline, which is a reason to look rather than a diagnosis. Symptoms
#: are observations with no verdict attached, so they are lighter still.
WEIGHTS = {
    "severity": 0.80,
    "unusualness": 0.55,
    "alarms": 0.50,
    "trend": 0.35,
    "acceleration": 0.30,
    "history": 0.30,
    "symptoms": 0.25,
}

#: Penalty per fault stage, indexed by severity 0-5. Not linear: the
#: distance from "developing" to "severe" is a bigger change in what anyone
#: should do than the distance from "normal" to "watch".
STAGE_PENALTY = (0.0, 0.12, 0.30, 0.55, 0.80, 1.0)

#: The best score each data-quality state is allowed to report.
#:
#: 100 is reserved for a machine with an established baseline, a resolvable
#: spectrum and a recent capture. Everything else is some degree of "we
#: cannot see well enough to certify this", and the ceiling is how that gets
#: said in the same units as the score.
CEILINGS = {
    "good": 100.0,
    "limited": 88.0,
    "poor": 72.0,
    "blind": 55.0,
}

#: Exponent applied to the anomaly score before it becomes a penalty.
#:
#: The scores arriving here are already non-linear -- they come off the
#: sigma anchors, where 40 is two sigma and 61 is three -- so treating them
#: as a straight fraction charges twice for the same curve. A single feature
#: at 55 was costing 30 points, and across forty features something sits
#: near three sigma by chance most of the time. Squaring puts the cost back
#: where the evidence is: 55 costs 17, 99 costs 54.
UNUSUALNESS_EXPONENT = 2.0

#: How much of the history weight a machine's worst-ever stage can claim.
#:
#: Capped well below a live finding on purpose. That this pump reached
#: severe in March is a real fact about the asset and belongs in the score,
#: but it is not evidence about its condition today, and a machine that was
#: repaired properly should be able to read healthy again.
HISTORY_PEAK_SHARE = 0.35

#: How long before a capture stops describing the machine as it is now.
STALE_AFTER_HOURS = 24.0

#: Criticality multipliers for priority. These never touch `score`.
CRITICALITY_WEIGHT = {
    "critical": 1.0, "high": 0.85, "medium": 0.6, "low": 0.4,
}


@dataclass
class Contribution:
    """One input's effect on the score, with the reason it had it."""
    key: str
    name: str
    penalty: float          # 0-1 before weighting
    weighted: float         # 0-1 after weighting
    points: float           # this input's share of the points lost
    alone: float = 0.0      # what it would have cost by itself
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name,
                "penalty": round(self.penalty, 4),
                "points_off": round(self.points, 1),
                "points_alone": round(self.alone, 1),
                "reason": self.reason, "detail": self.detail}


@dataclass
class HealthVerdict:
    score: Optional[float] = None
    #: What the score was allowed to reach, and why it was not 100.
    ceiling: float = 100.0
    data_quality: str = "good"
    band: str = "unknown"
    contributions: list[Contribution] = field(default_factory=list)
    #: Concerns that could not be assessed, rather than assessed as clear.
    unknowns: list[str] = field(default_factory=list)
    criticality: Optional[str] = None
    priority: Optional[float] = None
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.score is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score, "band": self.band, "ceiling": self.ceiling,
            "data_quality": self.data_quality, "usable": self.usable,
            "criticality": self.criticality, "priority": self.priority,
            "contributions": [c.as_dict() for c in self.contributions],
            "unknowns": self.unknowns, "reason": self.reason,
        }


#: Requirement 12.1's bands, verbatim: lower bound and label.
#:
#: These were originally invented -- five bands at different boundaries,
#: with "healthy" and "acceptable" in place of "Excellent" and "Good" --
#: on the reasoning that a health band and a fault stage should not share
#: vocabulary, since one describes a machine and the other one finding on
#: one channel. That reasoning is fine and the decision was still wrong:
#: the requirement specifies the boundaries and the words, somebody will
#: check the screen against the document, and a band that reads "degraded"
#: where the specification says "Watch" is a defect however well argued.
#:
#: The collision the original choice avoided is handled by context instead.
#: A machine has a health band; a finding has a stage. They are never shown
#: in the same column.
BANDS = ((90, "Excellent"), (75, "Good"), (60, "Watch"), (40, "Poor"),
         (20, "High risk"), (0, "Critical"))


def band_for(score: Optional[float]) -> str:
    """The word that goes with the number, per requirement 12.1."""
    if score is None:
        return "unknown"
    for lower, label in BANDS:
        if score >= lower:
            return label
    return "Critical"


def _quality(
    *, has_baseline: bool, resolution_usable: Optional[bool],
    hours_since_capture: Optional[float], captures_seen: Optional[int],
) -> tuple[str, list[str]]:
    """How well this machine can be seen at all, and what is in the way."""
    unknowns: list[str] = []

    if not has_baseline:
        unknowns.append(
            "No learned baseline is in force, so nothing this machine does "
            "can be called unusual. Not a clean result -- an unmeasured one.")
    if resolution_usable is False:
        unknowns.append(
            "The spectrum cannot separate the bearing defect frequencies "
            "from ordinary shaft harmonics, so the absence of a bearing "
            "fault here is the instrument's limit rather than the machine's "
            "condition.")
    if resolution_usable is None:
        unknowns.append(
            "Whether the spectrum could resolve the diagnostic orders was "
            "not recorded for this capture.")
    if hours_since_capture is not None and hours_since_capture > STALE_AFTER_HOURS:
        unknowns.append(
            f"The most recent capture is {hours_since_capture:.0f} hours "
            f"old, so this describes the machine as it was, not as it is.")
    if hours_since_capture is None:
        unknowns.append("No capture time was recorded.")
    if captures_seen is not None and captures_seen < 12:
        unknowns.append(
            f"Only {captures_seen} captures exist for this machine, which is "
            f"too few for the baseline statistics to be stable.")

    blind = (not has_baseline) and (resolution_usable is not True)
    if blind:
        return "blind", unknowns
    if len(unknowns) >= 2:
        return "poor", unknowns
    if unknowns:
        return "limited", unknowns
    return "good", unknowns


def assess(
    *,
    findings: Sequence[dict[str, Any]] = (),
    anomaly_scores: Sequence[float] = (),
    symptoms: Sequence[dict[str, Any]] = (),
    active_alarms: Sequence[dict[str, Any]] = (),
    trend_rising: Optional[bool] = None,
    trend_detail: Optional[dict[str, Any]] = None,
    trend_accelerating: Optional[bool] = None,
    acceleration_detail: Optional[dict[str, Any]] = None,
    has_baseline: bool = False,
    resolution_usable: Optional[bool] = None,
    hours_since_capture: Optional[float] = None,
    captures_seen: Optional[int] = None,
    criticality: Optional[str] = None,
) -> HealthVerdict:
    """Score a machine's condition from everything known about it.

    Returns a verdict whose score may be ``None``: a machine with no
    captures at all has no health score, and reporting one would be the
    lookup table's original sin in a new form.
    """
    quality, unknowns = _quality(
        has_baseline=has_baseline, resolution_usable=resolution_usable,
        hours_since_capture=hours_since_capture, captures_seen=captures_seen)

    verdict = HealthVerdict(data_quality=quality, ceiling=CEILINGS[quality],
                            unknowns=unknowns,
                            criticality=(criticality or "").strip().lower()
                            or None)

    if not findings and not anomaly_scores and not active_alarms:
        verdict.band = "unknown"
        verdict.reason = (
            "Nothing has been measured on this machine, so it has no health "
            "score. An unmeasured machine is not a healthy one, and the "
            "difference is the only thing this field can usefully say.")
        return verdict

    contributions: list[Contribution] = []

    def add(key: str, name: str, penalty: float, reason: str,
            detail: Optional[dict[str, Any]] = None) -> None:
        penalty = max(0.0, min(1.0, float(penalty)))
        if penalty <= 0:
            return
        contributions.append(Contribution(
            key=key, name=name, penalty=penalty,
            weighted=penalty * WEIGHTS[key], points=0.0, reason=reason,
            detail=detail or {}))

    # ------------------------------------------------- severity of findings
    open_findings = [f for f in findings if not f.get("resolved_at")]
    if open_findings:
        worst = max(open_findings, key=lambda f: int(f.get("severity") or 0))
        severity = int(worst.get("severity") or 0)
        if severity > 0:
            # Confidence scales it: a severe stage the engine is unsure of
            # is not the same claim as a severe stage it is certain of.
            confidence = float(worst.get("confidence") or 0.0)
            add("severity", "Named fault",
                STAGE_PENALTY[min(severity, 5)] * (0.5 + 0.5 * confidence),
                f"{worst.get('fault_name') or worst.get('fault_key')} on "
                f"channel {worst.get('channel')} is at stage "
                f"{worst.get('stage')}, seen "
                f"{worst.get('times_seen')} times, engine confidence "
                f"{confidence:.0%}.",
                {"fault_key": worst.get("fault_key"),
                 "stage": worst.get("stage"), "severity": severity,
                 "other_open": len(open_findings) - 1})

    # ------------------------------------------------------- unusualness
    scores = [float(s) for s in anomaly_scores if s is not None]
    if scores:
        peak = max(scores)
        add("unusualness", "Unlike its own baseline",
            (peak / 100.0) ** UNUSUALNESS_EXPONENT,
            f"The most unusual feature on this machine scores {peak:.0f} out "
            f"of 100 against its learned baseline"
            + (f", and {sum(1 for s in scores if s >= 60)} of {len(scores)} "
               f"features are above 60." if peak >= 60 else "."),
            {"peak": round(peak, 1), "features": len(scores)})
    elif has_baseline:
        unknowns.append(
            "No feature on this machine has been scored against its "
            "baseline, so its unusualness is unknown rather than low.")

    # ------------------------------------------------------------ alarms
    if active_alarms:
        worst_alarm = max(
            active_alarms,
            key=lambda a: {"critical": 3, "warning": 2}.get(
                str(a.get("severity") or a.get("level") or "").lower(), 1))
        level = str(worst_alarm.get("severity")
                    or worst_alarm.get("level") or "").lower()
        add("alarms", "Alarms standing",
            {"critical": 1.0, "warning": 0.55}.get(level, 0.3),
            f"{len(active_alarms)} alarm"
            f"{'s are' if len(active_alarms) != 1 else ' is'} standing on "
            f"this machine, the most severe at {level or 'unknown'} level. "
            f"An alarm here has already passed the four conditions -- "
            f"repetition, rising, steady speed and a trustworthy capture.",
            {"count": len(active_alarms), "worst": level})

    # ------------------------------------------------------------- trend
    if trend_rising is True:
        add("trend", "Getting worse", 0.85,
            (trend_detail or {}).get("statement")
            or "The measured level is higher at the end of the run than at "
               "the start, and the direction of travel agrees.",
            trend_detail or {})
    elif trend_rising is None:
        unknowns.append(
            "Whether this machine is getting worse could not be established "
            "-- the steadiness check needs about ten shaft revolutions per "
            "half of the record and this gateway's captures are too short.")

    # Requirement 12.1 lists trend acceleration separately from the trend
    # itself, and it is right to: something getting worse steadily and
    # something getting worse faster and faster are different amounts of
    # time to act in, and only the second one has a deadline.
    if trend_accelerating is True:
        add("acceleration", "Getting worse faster",
            0.9,
            (acceleration_detail or {}).get("statement")
            or "The rate of change is itself increasing, so the time "
               "available to act is shortening.",
            acceleration_detail or {})
    elif trend_accelerating is None and trend_rising is not None:
        unknowns.append(
            "Whether the deterioration is speeding up could not be "
            "established, which needs a longer run of readings than this "
            "machine has.")

    # ----------------------------------------------------------- symptoms
    named = [s for s in symptoms if s.get("key")]
    if named:
        # Capped below a fault: symptoms are observations, and observing
        # five of them is not five times as bad as observing one.
        add("symptoms", "Signal observations", min(1.0, 0.3 * len(named)),
            f"{len(named)} observation"
            f"{'s' if len(named) != 1 else ''} in the signal: "
            + ", ".join(str(s.get("name") or s["key"]) for s in named[:4])
            + ("." if len(named) <= 4 else f", and {len(named) - 4} more."),
            {"keys": [s["key"] for s in named]})

    # ------------------------------------------------------------ history
    peak_stages = [str(f.get("peak_stage") or "") for f in findings]
    ranks = {"normal": 0, "watch": 1, "early_fault_suspected": 2,
             "developing": 3, "severe": 4, "critical": 5}
    worst_ever = max((ranks.get(p, 0) for p in peak_stages), default=0)
    current = max((int(f.get("severity") or 0) for f in open_findings),
                  default=0)
    if worst_ever > current:
        # A machine that reached severe and recovered is not the same asset
        # as one that never left normal, even when they read alike today.
        add("history", "Has been worse before",
            HISTORY_PEAK_SHARE * worst_ever / 5.0,
            f"This machine has previously reached "
            f"{[k for k, v in ranks.items() if v == worst_ever][0].replace('_', ' ')}"
            f" and has come back down. A fault that recurs is a different "
            f"maintenance history from one that never happened.",
            {"peak_stage_rank": worst_ever, "current_rank": current})
    resolved = [f for f in findings if f.get("resolved_at")]
    if len(resolved) >= 3:
        add("history", "Recurring findings", min(1.0, 0.2 * len(resolved)),
            f"{len(resolved)} findings on this machine have opened and "
            f"closed. Repeated appearance and disappearance of a fault is "
            f"usually a marginal detection or an intermittent condition, "
            f"and both warrant a look.",
            {"resolved_count": len(resolved)})

    # ------------------------------------------------------------ combine
    # Independent chances of ill health rather than a sum: the worst input
    # leads, the others move the number less and less, and the total cannot
    # walk off the end of the scale.
    survival = 1.0
    for item in contributions:
        survival *= (1.0 - item.weighted)
    total_penalty = 1.0 - survival

    ceiling = verdict.ceiling
    score = ceiling * (1.0 - total_penalty)

    # Attribute the points each input cost. Largest first, so the split is
    # fixed by the size of each contribution rather than by the order the
    # code happens to add them in -- otherwise moving two blocks in this
    # function would change every number on the screen.
    #
    # `alone` is the counterfactual each reader actually wants: what this
    # one input would have cost on its own. It does not sum to the total,
    # and `points` does.
    contributions.sort(key=lambda c: -c.weighted)
    running = 1.0
    for item in contributions:
        before = running
        running *= (1.0 - item.weighted)
        item.points = round(ceiling * (before - running), 2)
        item.alone = round(ceiling * item.weighted, 2)
    verdict.contributions = contributions
    verdict.score = round(max(0.0, min(100.0, score)), 1)
    verdict.band = band_for(verdict.score)
    verdict.unknowns = unknowns

    if verdict.criticality:
        weight = CRITICALITY_WEIGHT.get(verdict.criticality, 0.6)
        verdict.priority = round((100.0 - verdict.score) * weight, 1)

    lead = contributions[0] if contributions else None
    if lead is None:
        verdict.reason = (
            f"Nothing measured on this machine is currently a concern. The "
            f"score stops at {ceiling:.0f} rather than 100 because "
            f"{quality} data quality is as well as this machine can be seen."
            if ceiling < 100 else
            "Nothing measured on this machine is currently a concern.")
    else:
        verdict.reason = (
            f"{verdict.score:.0f} out of {ceiling:.0f}, {verdict.band}. The "
            f"largest single contribution is {lead.name.lower()}, costing "
            f"{lead.points:.0f} points: {lead.reason}")
        if ceiling < 100:
            verdict.reason += (
                f" The score could not have exceeded {ceiling:.0f} in any "
                f"case, because data quality on this machine is {quality}.")
    return verdict
