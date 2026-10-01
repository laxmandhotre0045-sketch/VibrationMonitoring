"""What an analyst says back, and what it changes — section 16.

Section 16.1 lists eleven things an analyst must be able to mark. Section
16.2 then says what the feedback is *for*, and that second list is the one
that makes this hard: improving the model, reducing false alarms, improving
prioritisation, improving classification, and building site-specific
intelligence.

**Feedback that is only stored is not a feedback loop.** A verdict column
that nothing reads is a comment box. So every verdict here declares what it
actually does, and the ones that do nothing yet say so rather than implying
they are being learned from. Three of the eleven change behaviour today:

  * `false_alarm` and `fault_not_found` lower the engine's standing on that
    fault for that machine, which lowers its priority next time.
  * `ignore_for_machine` mutes it -- for a while, attributably, and only
    until it gets materially worse.
  * `severity_too_high` / `severity_too_low` shift the stage the engine
    reports for that fault on that machine.

The rest are recorded with everything needed to learn from them later. That
is not a failure: `wrong_fault_type` with a correction attached is the most
valuable row in the table, and what it needs is a retraining step that does
not exist yet. Pretending otherwise would be worse than saying so.

**A correction is evidence, not an instruction.** One analyst saying "false
alarm" once does not mean the rule is wrong -- they may have looked at the
wrong machine, or the fault may have been real and fixed between the
reading and the inspection. So adjustments need agreement across several
reports, they are bounded, and they decay: a correction from a year ago
should not still be suppressing a fault that has since come back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

#: Section 16.1's eleven options, with what each one does today. The
#: `effect` is what the platform actually changes; `learns` is what the row
#: is kept for.
VERDICTS: dict[str, dict[str, str]] = {
    "correct_detection": {
        "label": "Correct detection",
        "effect": "Raises the engine's standing on this fault for this "
                  "machine, so a repeat is prioritised a little higher.",
        "learns": "Confirmed positives are what any future retraining "
                  "measures itself against."},
    "false_alarm": {
        "label": "False alarm",
        "effect": "Lowers the engine's standing on this fault for this "
                  "machine, which lowers its priority next time.",
        "learns": "Repeated false alarms on one rule and one machine are "
                  "the clearest signal a threshold is wrong here."},
    "wrong_fault_type": {
        "label": "Wrong fault type",
        "effect": "Recorded with the correct fault, and shown beside the "
                  "engine's answer on any repeat.",
        "learns": "A correction that names the right answer is the only "
                  "kind a rule can be retrained from."},
    "severity_too_high": {
        "label": "Severity too high",
        "effect": "Shifts the stage reported for this fault on this machine "
                  "down by one, once enough analysts agree.",
        "learns": "Systematic over-calling is what makes a severity scale "
                  "stop being read."},
    "severity_too_low": {
        "label": "Severity too low",
        "effect": "Shifts the stage reported for this fault on this machine "
                  "up by one, once enough analysts agree.",
        "learns": "Under-calling is the more dangerous error and the harder "
                  "one to notice without being told."},
    "maintenance_confirmed": {
        "label": "Maintenance confirmed",
        "effect": "Closes the finding and records that the fault was real "
                  "and dealt with.",
        "learns": "A confirmed repair is the strongest label available -- "
                  "somebody opened the machine and looked."},
    "fault_not_found": {
        "label": "Fault not found",
        "effect": "Lowers the engine's standing on this fault for this "
                  "machine.",
        "learns": "Different from a false alarm: the reading was real and "
                  "the inspection found nothing, which more often means the "
                  "wrong place was inspected than that nothing is wrong."},
    "sensor_issue": {
        "label": "Sensor issue",
        "effect": "Recorded against the sensor rather than the machine.",
        "learns": "Groups by sensor rather than by fault, which is how a "
                  "failing accelerometer is spotted."},
    "process_related": {
        "label": "Process-related issue",
        "effect": "Recorded as normal for the process rather than a fault.",
        "learns": "Builds the site-specific picture section 16.2 asks for: "
                  "what is ordinary on this plant."},
    "ignore_for_machine": {
        "label": "Ignore for this machine",
        "effect": "Mutes this fault on this machine for a fixed period, "
                  "attributably, and only while it does not get worse.",
        "learns": "A mute that has to be renewed is a question that keeps "
                  "getting asked."},
    "new_fault_label": {
        "label": "Create new fault label",
        "effect": "Recorded as a fault the rule table does not cover.",
        "learns": "Repeated new labels are the backlog for the next set of "
                  "rules."},
}

#: Verdicts that say the engine was wrong about there being a fault at all.
NEGATIVE = ("false_alarm", "fault_not_found")
#: Verdicts that say it was right.
POSITIVE = ("correct_detection", "maintenance_confirmed")

#: How long `ignore_for_machine` mutes something. Weeks rather than
#: forever: a permanent mute is indistinguishable from not monitoring, and
#: nobody ever goes back to review one.
SUPPRESSION_DAYS = 90

#: How much worse a muted finding must get before it comes back anyway.
#: Without this, "ignore" is how a developing fault disappears quietly.
SUPPRESSION_BREAKOUT = 0.20

#: Reports needed before an adjustment is applied. One analyst on one day
#: is an opinion; three is a pattern.
AGREEMENT_NEEDED = 3

#: How far the standing adjustment can move the priority, either way.
#: Bounded so the loop can be wrong without becoming unrecoverable.
MAX_ADJUSTMENT = 0.30

#: Feedback older than this stops counting. A correction from last year
#: should not still be suppressing a fault that has come back since.
FEEDBACK_HALF_LIFE_DAYS = 180.0


@dataclass
class Standing:
    """What this machine's history says about this fault's credibility."""
    adjustment: float = 0.0          # -MAX .. +MAX, applied to priority
    confirmed: int = 0
    rejected: int = 0
    severity_shift: int = 0          # -1, 0 or +1
    reason: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"adjustment": round(self.adjustment, 3),
                "confirmed": self.confirmed, "rejected": self.rejected,
                "severity_shift": self.severity_shift, "reason": self.reason,
                "notes": self.notes}


def _weight(created_at: datetime, now: Optional[datetime] = None) -> float:
    """How much an old report still counts. Halves every half-life."""
    now = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days = max((now - created_at).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (days / FEEDBACK_HALF_LIFE_DAYS)


def standing_from(rows: Sequence[dict[str, Any]],
                  now: Optional[datetime] = None) -> Standing:
    """Turn a machine's feedback history on one fault into an adjustment.

    `rows` are feedback rows for one (sensor, channel, fault), newest
    first or oldest first -- order does not matter. Retracted rows must
    already have been filtered out by the caller.
    """
    standing = Standing()
    if not rows:
        standing.reason = ("No analyst has commented on this fault for this "
                           "machine, so the engine's own score stands.")
        return standing

    positive = negative = 0.0
    too_high = too_low = 0.0

    for row in rows:
        verdict = row.get("verdict")
        weight = _weight(row["created_at"], now)
        if verdict in POSITIVE:
            positive += weight
            standing.confirmed += 1
        elif verdict in NEGATIVE:
            negative += weight
            standing.rejected += 1
        elif verdict == "severity_too_high":
            too_high += weight
        elif verdict == "severity_too_low":
            too_low += weight

    total = positive + negative
    if total > 0:
        # Signed agreement, scaled by how much evidence there is. A single
        # report moves the number a little; several move it most of the way.
        balance = (positive - negative) / total
        evidence = min(total / AGREEMENT_NEEDED, 1.0)
        standing.adjustment = round(balance * evidence * MAX_ADJUSTMENT, 4)

    if too_high >= AGREEMENT_NEEDED and too_high > too_low:
        standing.severity_shift = -1
    elif too_low >= AGREEMENT_NEEDED and too_low > too_high:
        standing.severity_shift = 1

    bits = []
    if standing.confirmed:
        bits.append(f"{standing.confirmed} confirmation(s)")
    if standing.rejected:
        bits.append(f"{standing.rejected} rejection(s)")
    standing.reason = (
        f"{' and '.join(bits) or 'Feedback'} from analysts on this machine "
        f"move its priority by {standing.adjustment:+.0%}"
        + (f", and the reported stage by {standing.severity_shift:+d}."
           if standing.severity_shift else ".")
        + (" Older reports count for less; feedback halves in weight every "
           f"{FEEDBACK_HALF_LIFE_DAYS:.0f} days."
           if len(rows) > 1 else ""))

    if standing.rejected and not standing.confirmed and \
            standing.rejected < AGREEMENT_NEEDED:
        standing.notes.append(
            f"Only {standing.rejected} of the {AGREEMENT_NEEDED} reports "
            f"needed for a full adjustment. One analyst on one day is an "
            f"opinion -- the fault may have been real and repaired between "
            f"the reading and the inspection.")
    return standing


@dataclass
class Suppression:
    until: Optional[datetime] = None
    breakout_score: Optional[float] = None
    reason: str = ""

    def active_at(self, score: float,
                  when: Optional[datetime] = None) -> bool:
        """Whether the mute still holds for a finding now scoring `score`."""
        when = when or datetime.now(timezone.utc)
        if self.until is None:
            return False
        until = self.until
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if when >= until:
            return False
        if self.breakout_score is not None and score > self.breakout_score:
            return False
        return True


def suppress(*, current_score: float, analyst: str, reason: str,
             days: int = SUPPRESSION_DAYS,
             now: Optional[datetime] = None) -> Suppression:
    """Mute a fault on a machine -- temporarily, and with an escape hatch.

    The escape hatch is the point. A mute that cannot be broken is
    indistinguishable from not monitoring the machine, and it is granted at
    a moment when the fault looks harmless, which is exactly when nobody
    thinks to set a review date.
    """
    now = now or datetime.now(timezone.utc)
    until = now + timedelta(days=days)
    headroom = current_score + SUPPRESSION_BREAKOUT

    # A finding already at the top of the scale has no "materially worse"
    # left to reach, so there is no score that can break it out. Clamping
    # the breakout to 1.0 instead made the mute void the instant it was
    # granted -- the score was already 1.0, the comparison fired, and the
    # finding never left the queue. Saying there is no escape score is the
    # honest version, and the expiry still applies.
    if headroom > 1.0:
        return Suppression(
            until=until, breakout_score=None,
            reason=(
                f"Muted by {analyst} until {until.date()} because: "
                f"{reason.rstrip('.')}. This finding is already at the top "
                f"of the scale, so there is no higher score that could "
                f"bring it back early -- the mute holds until it expires, "
                f"and nothing else will interrupt it."))

    return Suppression(
        until=until,
        breakout_score=round(headroom, 4),
        reason=(
            f"Muted by {analyst} until {until.date()} because: "
            f"{reason.rstrip('.')}. It will come back on its own if the "
            f"score rises above {headroom:.2f} before then."))


def describe(verdict: str) -> dict[str, str]:
    """What this verdict means and what it changes. For the UI."""
    return VERDICTS.get(verdict, {
        "label": verdict, "effect": "Recorded.", "learns": ""})
