"""How dependable this asset has been — section 12.2.

Health says how a machine is now. Reliability says how much you can lean on
it, and the two come apart constantly: a pump that has been repaired four
times this year can read perfectly healthy this morning and still be the
one you would not stake a shutdown window on. Section 12.1 and 12.2 are
listed separately for that reason, and collapsing them would lose the
distinction that makes either useful.

**Health is a measurement; reliability is a history.** Every input here is
about what the machine has done over time -- how often it has alarmed, how
long its faults stay open, how many times it has been repaired, how steady
its readings are. Current health appears as one input among nine rather
than as the basis, because an asset's record is not erased by a good
morning.

**A machine with no history is unproven, not reliable.** This is the trap
in any score built from past events: an asset nobody has watched has no
alarms, no failures and no repairs, so every history-based input reads
perfectly. It would come top of the list. So the score is capped by how
much history exists, and a machine with a fortnight of data is reported as
unproven with the cap stated -- the same rule the health score applies to
data quality, for the same reason.

**Criticality does not move it.** A spare pump and a boiler feed pump with
identical records are equally dependable; what differs is the cost of being
wrong. Criticality is reported beside the score and drives the priority
queue, exactly as it does for health.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

#: How much each of section 12.2's inputs can take off a perfect record.
#: They sum to 1.0, so the deduction is readable as a share of "as poor a
#: record as this engine can describe".
WEIGHTS = {
    "current_health": 0.22,
    "previous_failures": 0.18,
    "repeated_alarms": 0.15,
    "fault_persistence": 0.13,
    "repair_history": 0.12,
    "trend_stability": 0.10,
    "operating_stress": 0.06,
    "maintenance_overdue": 0.04,
}

#: Captures before the record is worth treating as evidence. Below this the
#: score is capped and says so.
PROVEN_AFTER_CAPTURES = 200

#: Days of history before the record is worth treating as evidence. Both
#: this and the capture count must be met -- a thousand captures taken in
#: two days say a great deal about two days.
PROVEN_AFTER_DAYS = 90.0

#: The best score an unproven machine may report.
UNPROVEN_CEILING = 75.0

#: Alarm episodes per hundred captures at which the alarm input saturates.
#: A machine that alarms on one capture in ten is not twice as unreliable
#: as one that alarms on one in twenty; both are alarming constantly.
ALARM_RATE_SATURATION = 10.0

#: Days a fault may stay open before persistence counts fully against the
#: record. A fault open for a quarter is either being ignored or cannot be
#: fixed, and both are facts about dependability.
PERSISTENCE_SATURATION_DAYS = 90.0

#: Repairs before repair history saturates.
REPAIR_SATURATION = 5

#: Days since maintenance beyond which the asset counts as overdue.
MAINTENANCE_INTERVAL_DAYS = 365.0

#: Coefficient of variation in the score history above which a machine's
#: readings count as unsteady. Below it, ordinary scatter.
STABILITY_THRESHOLD = 0.35

BANDS = ((90, "Excellent"), (75, "Good"), (60, "Fair"), (40, "Poor"),
         (0, "Unreliable"))


def band_for(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    for lower, label in BANDS:
        if score >= lower:
            return label
    return "Unreliable"


@dataclass
class Factor:
    """One input's effect on the record, and the reason it had it."""
    key: str
    name: str
    penalty: float          # 0-1 before weighting
    points: float           # points off, for display
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name,
                "penalty": round(self.penalty, 4),
                "points_off": round(self.points, 1),
                "reason": self.reason, "detail": self.detail}


@dataclass
class ReliabilityVerdict:
    score: Optional[float] = None
    band: str = "unknown"
    ceiling: float = 100.0
    proven: bool = False
    factors: list[Factor] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    criticality: Optional[str] = None
    reason: str = ""

    @property
    def usable(self) -> bool:
        return self.score is not None

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "band": self.band,
                "ceiling": self.ceiling, "proven": self.proven,
                "usable": self.usable, "criticality": self.criticality,
                "factors": [f.as_dict() for f in self.factors],
                "unknowns": self.unknowns, "reason": self.reason}


def _days_since(when: Optional[datetime]) -> Optional[float]:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() / 86400.0


def _variation(values: Sequence[float]) -> Optional[float]:
    """Coefficient of variation, or None below three readings."""
    numbers = [float(v) for v in values if v is not None]
    if len(numbers) < 3:
        return None
    mean = sum(numbers) / len(numbers)
    if mean <= 0:
        return None
    variance = sum((v - mean) ** 2 for v in numbers) / len(numbers)
    return (variance ** 0.5) / mean


def assess(
    *,
    current_health: Optional[float] = None,
    captures: int = 0,
    history_days: Optional[float] = None,
    alarm_episodes: int = 0,
    open_fault_days: Sequence[float] = (),
    repairs: int = 0,
    previous_failures: int = 0,
    last_maintenance: Optional[datetime] = None,
    score_history: Sequence[float] = (),
    hours_outside_normal_mode: Optional[float] = None,
    hours_observed: Optional[float] = None,
    criticality: Optional[str] = None,
) -> ReliabilityVerdict:
    """Score how dependable this asset's record is. Section 12.2.

    Returns a verdict whose score may be ``None``: an asset with no
    captures has no record, and reporting one would be the same mistake the
    fixed health lookup made.
    """
    verdict = ReliabilityVerdict(
        criticality=(criticality or "").strip().lower() or None)
    unknowns: list[str] = []
    factors: list[Factor] = []

    if captures <= 0:
        verdict.reason = (
            "Nothing has ever been recorded from this machine, so it has no "
            "track record to judge. An unproven asset is not a dependable "
            "one, and the difference is the only thing this field can "
            "usefully say.")
        return verdict

    proven = (captures >= PROVEN_AFTER_CAPTURES
              and (history_days or 0) >= PROVEN_AFTER_DAYS)
    verdict.proven = proven
    verdict.ceiling = 100.0 if proven else UNPROVEN_CEILING
    if not proven:
        unknowns.append(
            f"Only {captures} capture(s) over "
            f"{(history_days or 0):.0f} days. A record needs about "
            f"{PROVEN_AFTER_CAPTURES} captures across "
            f"{PROVEN_AFTER_DAYS:.0f} days before it is evidence, so this "
            f"machine is unproven rather than reliable -- every "
            f"history-based input reads perfectly on an asset nobody has "
            f"watched.")

    def add(key, name, penalty, reason, detail=None):
        penalty = max(0.0, min(1.0, float(penalty)))
        if penalty <= 0:
            return
        factors.append(Factor(key=key, name=name, penalty=penalty,
                              points=0.0, reason=reason, detail=detail or {}))

    # ------------------------------------------------- current health ---
    if current_health is None:
        unknowns.append("This machine has no health score, so its present "
                        "condition is unknown rather than good.")
    else:
        add("current_health", "Condition today",
            max(0.0, (100.0 - float(current_health)) / 100.0),
            f"Health is {current_health:.0f} of 100 today. One input of "
            f"nine: a good morning does not erase a record, and a bad one "
            f"does not create a history.",
            {"health": round(float(current_health), 1)})

    # --------------------------------------------- previous failures ----
    if previous_failures:
        add("previous_failures", "Has failed before",
            min(previous_failures / 3.0, 1.0),
            f"{previous_failures} finding(s) on this machine have reached "
            f"severe or critical. An asset that has failed is more likely "
            f"to fail again -- the same weakness is usually still there.",
            {"count": previous_failures})

    # ------------------------------------------------ repeated alarms ---
    rate = (alarm_episodes / captures) * 100.0
    if alarm_episodes:
        add("repeated_alarms", "Alarms often",
            min(rate / ALARM_RATE_SATURATION, 1.0),
            f"{alarm_episodes} alarm episode(s) across {captures} captures "
            f"-- {rate:.1f} per hundred. A machine that alarms constantly "
            f"is either genuinely unwell or wrongly configured, and neither "
            f"is dependable.",
            {"episodes": alarm_episodes, "per_hundred": round(rate, 2)})

    # ---------------------------------------------- fault persistence ---
    if open_fault_days:
        longest = max(float(d) for d in open_fault_days)
        add("fault_persistence", "Faults stay open",
            min(longest / PERSISTENCE_SATURATION_DAYS, 1.0),
            f"The longest-standing open finding has been there "
            f"{longest:.0f} days. A fault that does not close is either "
            f"being lived with or cannot be fixed, and both are facts "
            f"about how much this asset can be relied on.",
            {"longest_days": round(longest, 1),
             "open_findings": len(open_fault_days)})

    # ------------------------------------------------- repair history ---
    if repairs:
        add("repair_history", "Repeatedly repaired",
            min(repairs / REPAIR_SATURATION, 1.0),
            f"{repairs} confirmed repair(s) on record. Repairs are good "
            f"news about the maintenance team and bad news about the "
            f"machine.",
            {"repairs": repairs})

    # ------------------------------------------------ trend stability ---
    variation = _variation(score_history)
    if variation is None:
        unknowns.append("Too few readings to say whether this machine's "
                        "behaviour is steady.")
    elif variation > STABILITY_THRESHOLD:
        add("trend_stability", "Behaves erratically",
            min((variation - STABILITY_THRESHOLD) / STABILITY_THRESHOLD, 1.0),
            f"Its readings vary by {variation:.0%} around their own mean, "
            f"against the {STABILITY_THRESHOLD:.0%} that counts as ordinary "
            f"scatter. A machine whose behaviour jumps about is hard to "
            f"plan around even when nothing is wrong.",
            {"coefficient_of_variation": round(variation, 3)})

    # ----------------------------------------------- operating stress ---
    if hours_observed and hours_outside_normal_mode is not None:
        share = min(hours_outside_normal_mode / hours_observed, 1.0)
        if share > 0:
            add("operating_stress", "Run outside its normal band",
                share,
                f"{share:.0%} of observed running has been outside this "
                f"machine's normal operating mode. Running a machine away "
                f"from its design point wears it faster, whatever its "
                f"condition reads today.",
                {"share_outside": round(share, 3)})
    else:
        unknowns.append("How much of the time this machine runs outside its "
                        "normal operating band is not known.")

    # ------------------------------------------- maintenance overdue ----
    days = _days_since(last_maintenance)
    if days is None:
        unknowns.append("No maintenance date on record, so whether this "
                        "machine is overdue is unknown.")
    elif days > MAINTENANCE_INTERVAL_DAYS:
        add("maintenance_overdue", "Maintenance overdue",
            min((days - MAINTENANCE_INTERVAL_DAYS)
                / MAINTENANCE_INTERVAL_DAYS, 1.0),
            f"Last maintained {days:.0f} days ago, past the "
            f"{MAINTENANCE_INTERVAL_DAYS:.0f}-day interval.",
            {"days_since": round(days, 0)})

    # --------------------------------------------------------- combine --
    # Independent detractions rather than a sum, so the worst leads and the
    # total cannot walk off the scale. The same arithmetic the health score
    # uses, for the same reason.
    survival = 1.0
    for factor in factors:
        survival *= (1.0 - factor.penalty * WEIGHTS[factor.key])
    deduction = 1.0 - survival

    ceiling = verdict.ceiling
    score = ceiling * (1.0 - deduction)

    factors.sort(key=lambda f: -(f.penalty * WEIGHTS[f.key]))
    running = 1.0
    for factor in factors:
        before = running
        running *= (1.0 - factor.penalty * WEIGHTS[factor.key])
        factor.points = round(ceiling * (before - running), 2)

    verdict.factors = factors
    verdict.unknowns = unknowns
    verdict.score = round(max(0.0, min(100.0, score)), 1)
    verdict.band = band_for(verdict.score)

    lead = factors[0] if factors else None
    if lead is None:
        verdict.reason = (
            f"Nothing on this machine's record counts against it."
            + (f" The score stops at {ceiling:.0f} rather than 100 because "
               f"it is not yet proven: {captures} captures over "
               f"{(history_days or 0):.0f} days." if not proven else ""))
    else:
        verdict.reason = (
            f"{verdict.score:.0f} out of {ceiling:.0f}, {verdict.band}. The "
            f"largest single mark against it is {lead.name.lower()}, costing "
            f"{lead.points:.0f} points: {lead.reason}")
        if not proven:
            verdict.reason += (
                f" It could not have exceeded {ceiling:.0f} in any case, "
                f"because its record is too short to be evidence.")
    return verdict
