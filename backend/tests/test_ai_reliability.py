"""How dependable an asset has been — section 12.2.

Section 12 asks for two scores and they are listed separately on purpose.
Health is a measurement of now; reliability is a reading of a record. They
come apart constantly, and the tests that matter here are the ones proving
they do: a machine repaired four times can read perfectly healthy this
morning and still not be one to stake a shutdown window on.

**The trap in any score built from past events is that an asset with no
past looks perfect.** No alarms, no failures, no repairs -- every
history-based input reads clean, and a machine nobody has watched for a
fortnight tops the list. That is the single most important thing these
tests pin down.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.ai.reliability import (
    MAINTENANCE_INTERVAL_DAYS,
    PROVEN_AFTER_CAPTURES,
    PROVEN_AFTER_DAYS,
    STABILITY_THRESHOLD,
    UNPROVEN_CEILING,
    assess,
    band_for,
)

NOW = datetime.now(timezone.utc)
PROVEN = dict(captures=PROVEN_AFTER_CAPTURES * 2,
              history_days=PROVEN_AFTER_DAYS * 2)
STEADY = [90.0, 91.0, 89.0, 90.0, 91.0]


def test_a_machine_with_no_captures_has_no_record():
    verdict = assess()
    assert verdict.score is None
    assert verdict.usable is False
    assert "unproven asset is not a dependable one" in verdict.reason


def test_a_short_record_is_unproven_not_reliable():
    """The trap this score exists to avoid. An asset nobody has watched has
    no alarms, no failures and no repairs, so every history input reads
    perfectly and it would come top of the list."""
    new = assess(current_health=98.0, captures=40, history_days=14.0,
                 score_history=STEADY)
    established = assess(current_health=98.0, score_history=STEADY, **PROVEN)

    assert new.proven is False
    assert new.ceiling == UNPROVEN_CEILING
    assert new.score < established.score
    assert any("unproven rather than reliable" in u for u in new.unknowns)


def test_a_long_clean_record_scores_near_a_hundred():
    verdict = assess(current_health=98.0, score_history=STEADY, **PROVEN)
    assert verdict.proven is True
    assert verdict.score >= 95
    assert verdict.band == "Excellent"


def test_both_capture_count_and_elapsed_time_are_required():
    """A thousand captures taken in two days say a great deal about two
    days."""
    dense = assess(current_health=98.0, captures=PROVEN_AFTER_CAPTURES * 5,
                   history_days=3.0, score_history=STEADY)
    assert dense.proven is False


def test_a_healthy_machine_with_a_bad_record_is_not_dependable():
    """The whole reason section 12 asks for two scores. Health says the
    machine is fine this morning; reliability says it has been repaired
    four times and failed twice."""
    clean = assess(current_health=95.0, score_history=STEADY, **PROVEN)
    scarred = assess(current_health=95.0, repairs=4, previous_failures=2,
                     score_history=STEADY, **PROVEN)

    assert scarred.score < clean.score - 10
    assert {f.key for f in scarred.factors} >= {"repair_history",
                                                "previous_failures"}


def test_current_health_is_one_input_of_nine_not_the_basis():
    """A bad morning must not erase a good record, and vice versa."""
    verdict = assess(current_health=10.0, score_history=STEADY, **PROVEN)
    health_points = next(f.points for f in verdict.factors
                         if f.key == "current_health")
    assert health_points < 30, (
        "condition today dominates the record; reliability would just be "
        "health with extra steps")


def test_alarming_constantly_counts_against_a_machine():
    quiet = assess(current_health=80.0, alarm_episodes=0,
                   score_history=STEADY, **PROVEN)
    noisy = assess(current_health=80.0, alarm_episodes=120,
                   score_history=STEADY, **PROVEN)
    assert noisy.score < quiet.score


def test_a_fault_left_open_counts_against_a_machine():
    closed = assess(current_health=80.0, open_fault_days=[],
                    score_history=STEADY, **PROVEN)
    lingering = assess(current_health=80.0, open_fault_days=[200.0],
                       score_history=STEADY, **PROVEN)
    assert lingering.score < closed.score


def test_erratic_readings_count_against_a_machine_even_when_healthy():
    """A machine whose behaviour jumps about is hard to plan around even
    when nothing is currently wrong."""
    steady = assess(current_health=90.0, score_history=STEADY, **PROVEN)
    erratic = assess(current_health=90.0,
                     score_history=[10.0, 95.0, 20.0, 90.0, 15.0, 88.0],
                     **PROVEN)
    assert erratic.score < steady.score
    assert any(f.key == "trend_stability" for f in erratic.factors)


def test_stability_needs_three_readings_before_it_judges():
    verdict = assess(current_health=90.0, score_history=[50.0, 90.0],
                     **PROVEN)
    assert all(f.key != "trend_stability" for f in verdict.factors)
    assert any("steady" in u for u in verdict.unknowns)


def test_ordinary_scatter_is_not_erratic():
    verdict = assess(current_health=90.0, score_history=STEADY, **PROVEN)
    assert all(f.key != "trend_stability" for f in verdict.factors)
    assert STABILITY_THRESHOLD > 0.2


def test_overdue_maintenance_counts_but_lightly():
    overdue = assess(
        current_health=90.0, score_history=STEADY,
        last_maintenance=NOW - timedelta(days=MAINTENANCE_INTERVAL_DAYS * 3),
        **PROVEN)
    recent = assess(current_health=90.0, score_history=STEADY,
                    last_maintenance=NOW - timedelta(days=30), **PROVEN)
    assert overdue.score < recent.score
    points = next(f.points for f in overdue.factors
                  if f.key == "maintenance_overdue")
    assert points < 10, "being overdue is context, not a fault"


def test_missing_inputs_are_listed_rather_than_assumed():
    verdict = assess(current_health=None, captures=300,
                     history_days=200.0)
    assert verdict.unknowns
    assert any("health score" in u for u in verdict.unknowns)
    assert any("maintenance date" in u for u in verdict.unknowns)


def test_criticality_does_not_move_the_score():
    """A spare pump and a boiler feed pump with identical records are
    equally dependable; what differs is the cost of being wrong."""
    args = dict(current_health=70.0, repairs=2, score_history=STEADY,
                **PROVEN)
    high = assess(criticality="critical", **args)
    low = assess(criticality="low", **args)
    assert high.score == low.score
    assert high.criticality == "critical"


def test_the_score_cannot_leave_the_scale():
    verdict = assess(
        current_health=0.0, captures=500, history_days=400.0,
        alarm_episodes=500, open_fault_days=[400.0], repairs=20,
        previous_failures=20,
        score_history=[5.0, 95.0, 10.0, 90.0, 2.0, 99.0],
        hours_outside_normal_mode=400.0, hours_observed=400.0,
        last_maintenance=NOW - timedelta(days=3000))
    assert 0.0 <= verdict.score <= 100.0
    assert verdict.band == "Unreliable"


def test_every_factor_carries_its_reason_and_the_points_add_up():
    verdict = assess(current_health=60.0, repairs=3, previous_failures=1,
                     alarm_episodes=40, score_history=STEADY, **PROVEN)
    assert verdict.factors
    for factor in verdict.factors:
        assert factor.reason, f"{factor.key} moved the score without saying why"
    attributed = sum(f.points for f in verdict.factors)
    assert attributed == pytest.approx(verdict.ceiling - verdict.score,
                                       abs=0.2)


def test_bands_run_from_excellent_to_unreliable():
    assert band_for(None) == "unknown"
    assert band_for(95) == "Excellent"
    assert band_for(10) == "Unreliable"
