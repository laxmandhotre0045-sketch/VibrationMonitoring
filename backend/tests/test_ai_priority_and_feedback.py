"""Phase 4 — the priority queue and the analyst feedback loop.

Section 15 ranks the work; section 16 is how the platform finds out whether
it was right. They are tested together because they are one loop: feedback
that does not move the queue is a comment box, and a queue that cannot be
corrected is one nobody keeps using.

**The tests worth reading are the ones about restraint and about honesty.**
Producing a ranking is arithmetic. Not letting the least trustworthy
readings float to the top of it is the design, because noise produces the
most extreme values and a queue led by measurement problems is abandoned
within a fortnight. Likewise a mute that cannot expire or be broken is
indistinguishable from not monitoring the machine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ai.feedback import (
    AGREEMENT_NEEDED,
    FEEDBACK_HALF_LIFE_DAYS,
    MAX_ADJUSTMENT,
    NEGATIVE,
    POSITIVE,
    SUPPRESSION_BREAKOUT,
    VERDICTS,
    standing_from,
    suppress,
)
from app.ai.priority import (
    CONFIDENCE_FLOOR,
    UNKNOWN_IMPACT,
    band_for,
    order,
    rank,
)

NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)

SEEN_WELL = dict(data_quality="good", anomaly_score=70, times_seen=6,
                 symptom_count=3, active_alarms=1)
CRITICAL_MACHINE = dict(criticality="critical", safety_impact="high",
                        production_impact="high")
SPARE_MACHINE = dict(criticality="low", safety_impact="none",
                     production_impact="low")


def report(verdict, days_ago=0):
    return {"verdict": verdict, "created_at": NOW - timedelta(days=days_ago)}


# ================================================ priority (section 15) ===

def test_the_same_fault_matters_more_on_a_machine_that_matters_more():
    """The whole reason consequence is scored separately. No amount of
    vibration analysis can tell a spare pump from a boiler feed pump."""
    critical = rank(severity=4, confidence=0.9, **CRITICAL_MACHINE,
                    **SEEN_WELL)
    spare = rank(severity=4, confidence=0.9, **SPARE_MACHINE, **SEEN_WELL)

    assert critical.score > spare.score * 2


def test_a_finding_the_engine_is_unsure_of_is_ranked_below_one_it_is_sure_of():
    sure = rank(severity=4, confidence=0.95, **CRITICAL_MACHINE, **SEEN_WELL)
    unsure = rank(severity=4, confidence=0.2, **CRITICAL_MACHINE, **SEEN_WELL)
    assert unsure.score < sure.score


def test_a_machine_that_cannot_be_seen_is_ranked_below_one_that_can():
    """Otherwise the queue is led by measurement problems, because noise
    produces the most extreme readings."""
    seen = rank(severity=4, confidence=0.9, **CRITICAL_MACHINE, **SEEN_WELL)
    blind = rank(severity=4, confidence=0.9, **CRITICAL_MACHINE,
                 anomaly_score=70, times_seen=6, symptom_count=3,
                 active_alarms=1, data_quality="blind")
    assert blind.score < seen.score


def test_a_barely_confident_finding_cannot_lead_the_queue():
    verdict = rank(severity=5, confidence=CONFIDENCE_FLOOR - 0.05,
                   criticality="critical", safety_impact="severe",
                   production_impact="severe", data_quality="good",
                   anomaly_score=100, times_seen=20, symptom_count=5,
                   active_alarms=3, accelerating=True)
    assert verdict.band != "immediate"
    assert any("lead the queue" in u for u in verdict.unknowns)


def test_an_unclassified_machine_is_unknown_not_harmless():
    """Safety and production impact cannot be derived from vibration. A
    machine nobody has classified must not sink to the bottom for it."""
    unclassified = rank(severity=4, confidence=0.9, **SEEN_WELL)
    spare = rank(severity=4, confidence=0.9, **SPARE_MACHINE, **SEEN_WELL)

    assert unclassified.score > spare.score
    assert UNKNOWN_IMPACT > 0.3
    assert any("Safety impact is not recorded" in u
               for u in unclassified.unknowns)
    assert any("not recorded" in u for u in unclassified.unknowns)


def test_a_safety_problem_is_not_averaged_away():
    """A machine that can hurt somebody is a safety problem whatever its
    production role, and a mean is how that gets diluted.

    The multiple matters and was originally set too low. Averaging the
    three consequence inputs instead of leading on the worst still
    separates these two by about 1.9x, so a threshold of 1.8 passed either
    way and the guard was untested. Leading on the worst gives about 3.0x.
    """
    dangerous = rank(severity=3, confidence=0.9, criticality="low",
                     safety_impact="severe", production_impact="none",
                     **SEEN_WELL)
    ordinary = rank(severity=3, confidence=0.9, criticality="low",
                    safety_impact="low", production_impact="none",
                    **SEEN_WELL)
    assert dangerous.score > ordinary.score * 2.5


def test_an_accelerating_fault_outranks_a_steady_one():
    speeding = rank(severity=3, confidence=0.9, accelerating=True,
                    direction="rising", **CRITICAL_MACHINE, **SEEN_WELL)
    steady = rank(severity=3, confidence=0.9, accelerating=False,
                  direction="steady", **CRITICAL_MACHINE, **SEEN_WELL)
    assert speeding.score > steady.score


def test_persistence_saturates():
    """A fault seen twenty times is not twice as urgent as one seen ten."""
    ten = rank(severity=3, confidence=0.9, times_seen=10,
               **CRITICAL_MACHINE, data_quality="good", anomaly_score=70,
               symptom_count=3, active_alarms=1)
    forty = rank(severity=3, confidence=0.9, times_seen=40,
                 **CRITICAL_MACHINE, data_quality="good", anomaly_score=70,
                 symptom_count=3, active_alarms=1)
    assert ten.score == forty.score


def test_the_queue_explains_its_own_order():
    """An engineer who cannot see why item three outranks item four stops
    trusting the order and reads the list top to bottom anyway."""
    verdict = rank(severity=4, confidence=0.9, **CRITICAL_MACHINE,
                   **SEEN_WELL)
    assert verdict.reason
    assert "condition" in verdict.reason.lower()
    assert "consequence" in verdict.reason.lower()
    assert verdict.inputs


def test_muted_findings_sink_to_the_bottom_whatever_they_score():
    loud = rank(severity=2, confidence=0.7, **SPARE_MACHINE, **SEEN_WELL)
    muted = rank(severity=5, confidence=0.95, criticality="critical",
                 safety_impact="severe", production_impact="severe",
                 suppressed=True, **SEEN_WELL)

    ranked = order([("quiet", loud), ("muted", muted)])
    assert ranked[0][1] == "quiet"
    assert ranked[-1][1] == "muted"
    assert muted.band == "suppressed"


def test_rank_is_a_number_not_a_position():
    """Section 15.2 asks for "Rank" as a field. A position in a list is not
    one, because the list can be filtered or paged."""
    items = [(f"m{i}", rank(severity=i, confidence=0.9, **CRITICAL_MACHINE,
                            **SEEN_WELL)) for i in range(1, 5)]
    ranked = order(items)
    assert [r for r, _, _ in ranked] == [1, 2, 3, 4]


def test_priority_bands_are_ordered():
    assert band_for(None) == "unknown"
    assert band_for(90) == "immediate"
    assert band_for(5) == "watch"


# ================================================ feedback (section 16) ===

def test_all_eleven_of_section_16_1s_options_exist():
    assert len(VERDICTS) == 11
    for key, entry in VERDICTS.items():
        assert entry["label"], key
        assert entry["effect"], f"{key} does not say what it changes"
        assert entry["learns"], f"{key} does not say what it is kept for"


def test_no_feedback_leaves_the_engines_score_alone():
    standing = standing_from([], NOW)
    assert standing.adjustment == 0.0
    assert "No analyst has commented" in standing.reason


def test_one_report_moves_the_score_a_little_and_says_it_is_only_one():
    """One analyst on one day is an opinion. The fault may have been real
    and repaired between the reading and the inspection."""
    standing = standing_from([report("false_alarm")], NOW)
    assert -MAX_ADJUSTMENT < standing.adjustment < 0
    assert standing.notes
    assert str(AGREEMENT_NEEDED) in standing.notes[0]


def test_agreement_moves_it_the_whole_way():
    standing = standing_from([report("false_alarm")] * AGREEMENT_NEEDED, NOW)
    assert standing.adjustment == pytest.approx(-MAX_ADJUSTMENT, abs=0.001)
    assert not standing.notes


def test_confirmations_raise_the_standing():
    standing = standing_from([report("correct_detection")] * AGREEMENT_NEEDED,
                             NOW)
    assert standing.adjustment == pytest.approx(MAX_ADJUSTMENT, abs=0.001)


def test_analysts_who_disagree_cancel_out():
    standing = standing_from([report("false_alarm")] * 2
                             + [report("correct_detection")] * 2, NOW)
    assert standing.adjustment == pytest.approx(0.0, abs=0.001)


def test_old_feedback_counts_for_less():
    """A correction from last year should not still be suppressing a fault
    that has come back since."""
    fresh = standing_from([report("false_alarm")] * 3, NOW)
    stale = standing_from(
        [report("false_alarm", FEEDBACK_HALF_LIFE_DAYS * 2)] * 3, NOW)

    assert abs(stale.adjustment) < abs(fresh.adjustment) / 2


def test_the_adjustment_is_bounded_however_much_feedback_arrives():
    """The loop has to be able to be wrong without becoming unrecoverable."""
    standing = standing_from([report("false_alarm")] * 500, NOW)
    assert standing.adjustment >= -MAX_ADJUSTMENT


def test_repeated_severity_complaints_shift_the_stage():
    high = standing_from([report("severity_too_high")] * AGREEMENT_NEEDED, NOW)
    low = standing_from([report("severity_too_low")] * AGREEMENT_NEEDED, NOW)
    assert high.severity_shift == -1
    assert low.severity_shift == 1


def test_one_severity_complaint_does_not_shift_anything():
    assert standing_from([report("severity_too_high")], NOW).severity_shift == 0


# ------------------------------------------------------- suppression ----

def test_a_mute_expires():
    """A permanent mute is indistinguishable from not monitoring, and
    nobody ever goes back to review one."""
    mute = suppress(current_score=0.4, analyst="a", reason="known resonance",
                    days=30, now=NOW)
    assert mute.active_at(0.4, NOW + timedelta(days=10)) is True
    assert mute.active_at(0.4, NOW + timedelta(days=31)) is False


def test_a_muted_fault_comes_back_if_it_gets_materially_worse():
    """Otherwise "ignore for this machine" is how a developing fault
    disappears quietly."""
    mute = suppress(current_score=0.40, analyst="a", reason="known",
                    now=NOW)
    assert mute.active_at(0.45, NOW) is True
    assert mute.active_at(0.40 + SUPPRESSION_BREAKOUT + 0.01, NOW) is False


def test_a_mute_records_who_asked_for_it_and_why():
    mute = suppress(current_score=0.4, analyst="a.kulkarni",
                    reason="known pipe resonance", now=NOW)
    assert "a.kulkarni" in mute.reason
    assert "known pipe resonance" in mute.reason
    assert "come back on its own" in mute.reason


def test_the_two_kinds_of_negative_feedback_are_kept_apart():
    """"False alarm" and "fault not found" mean different things: one says
    the reading was wrong, the other that the reading was right and the
    inspection found nothing -- which more often means the wrong place was
    inspected."""
    assert set(NEGATIVE) == {"false_alarm", "fault_not_found"}
    assert VERDICTS["false_alarm"]["learns"] != \
        VERDICTS["fault_not_found"]["learns"]
    assert set(POSITIVE) == {"correct_detection", "maintenance_confirmed"}
