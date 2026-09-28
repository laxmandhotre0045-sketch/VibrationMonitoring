"""Direction, urgency and the recommended action — requirement 9.2 and 14.

Requirement 9.2 lists nine things that must appear beside every suspected
fault. An audit against the document found four missing: the fault family,
the trend direction, the recommended next action, and whether a shutdown is
needed or only an inspection. Requirement 14 asks for the last two again in
its own words.

**The tests that matter here are the ones about restraint.** Producing an
urgency from a stage is a lookup. Refusing to produce a high one when the
evidence will not carry it is the whole design, because the failure this
guards against is expensive in both directions: a shutdown recommendation
off an untrustworthy capture stops a healthy production line, and the
fourth false alarm is the one after which nobody acts on the third real
one.
"""

from __future__ import annotations

import json
import os

import pytest

from app.ai.recommendation import (
    CONFIDENCE_FOR_ACTION,
    CONFIDENCE_FOR_INSPECTION,
    HISTORY_LENGTH,
    MIN_SIGHTINGS_FOR_DIRECTION,
    STAGE_URGENCY,
    URGENCY,
    direction_of,
    recommend,
)

VIBCORE_RULES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "vibcore", "data", "fault_signatures.json")


def rules():
    with open(VIBCORE_RULES, encoding="utf-8") as handle:
        return json.load(handle)["rules"]


# ------------------------------------------------------- fault family ----

def test_every_rule_has_a_family():
    """Requirement 9.2 asks for the family beside the name. A rule without
    one is a data error, not a fault that belongs to nothing."""
    missing = [k for k, r in rules().items() if not r.get("family")]
    assert not missing, f"no family on {sorted(missing)}"


def test_families_group_faults_that_are_fixed_the_same_way():
    """The point of a family is that it decides who gets called out, so the
    four bearing defects must not land in four different families."""
    by_family = {}
    for key, rule in rules().items():
        by_family.setdefault(rule["family"], set()).add(key)

    bearings = {k for k in rules() if k.startswith("bearing_")}
    assert any(bearings <= members for members in by_family.values()), (
        "the bearing defects are split across families, so a bearing "
        "problem would be routed to more than one trade")


# ---------------------------------------------------- trend direction ----

def test_two_readings_are_not_a_direction():
    """Two readings always have a direction and it is noise half the time.
    Reporting that as 'steady' would be a claim nobody measured."""
    verdict = direction_of([0.4, 0.9])
    assert verdict.direction == "unknown"
    assert "not the same as holding steady" in verdict.reason


def test_a_climbing_score_reads_as_rising():
    verdict = direction_of([0.30, 0.42, 0.55, 0.71])
    assert verdict.direction == "rising"
    assert verdict.rising is True
    assert verdict.change == pytest.approx(0.41, abs=0.01)


def test_a_falling_score_reads_as_recovering():
    verdict = direction_of([0.80, 0.62, 0.45, 0.31])
    assert verdict.direction == "falling"
    assert "recovering" in verdict.reason


def test_run_to_run_wobble_is_not_a_trend():
    verdict = direction_of([0.50, 0.52, 0.49, 0.51])
    assert verdict.direction == "steady"


def test_one_spike_does_not_make_a_rising_trend():
    """The mistake a mean-of-halves comparison makes on short runs: with
    four readings each half is two, so a single spike counts in full."""
    assert direction_of([0.70, 0.99, 0.70, 0.70]).direction != "rising"


def test_a_direction_needs_three_readings():
    assert MIN_SIGHTINGS_FOR_DIRECTION >= 3
    assert direction_of([0.2] * (MIN_SIGHTINGS_FOR_DIRECTION - 1)
                        ).direction == "unknown"


# ---------------------------------------------------------- urgency -----

def test_each_stage_proposes_an_urgency():
    from app.ai.severity import STAGES as SEVERITY_STAGES
    assert set(STAGE_URGENCY) == set(SEVERITY_STAGES)
    assert all(v in URGENCY for v in STAGE_URGENCY.values())


def test_only_critical_can_advise_a_shutdown():
    """The one field somebody may act on without reading the rest."""
    for stage in STAGE_URGENCY:
        advice = recommend(stage=stage, confidence=1.0,
                           resolution_usable=True, capture_trustworthy=True)
        if stage != "critical":
            assert advice.shutdown_advised is False, stage
    top = recommend(stage="critical", confidence=1.0, resolution_usable=True,
                    capture_trustworthy=True)
    assert top.shutdown_advised is True


def test_an_untrustworthy_capture_cannot_advise_a_shutdown():
    """The expensive one. A capture that failed its own quality checks may
    be describing the instrument, and stopping a healthy line on that is
    how a monitoring system stops being believed."""
    advice = recommend(stage="critical", confidence=1.0,
                       resolution_usable=True, capture_trustworthy=False)

    assert advice.shutdown_advised is False
    assert advice.capped is True
    assert advice.proposed == "immediate"
    assert advice.urgency != "immediate"
    assert any("quality checks" in c for c in advice.caps)


def test_a_spectrum_that_cannot_resolve_the_orders_caps_the_urgency():
    """On this gateway the outer-race frequency and the third shaft
    harmonic land on the same line, so a 'critical' bearing finding may be
    an ordinary machine."""
    advice = recommend(stage="critical", confidence=1.0,
                       resolution_usable=False, capture_trustworthy=True)
    assert advice.shutdown_advised is False
    assert any("cannot separate" in c for c in advice.caps)


def test_an_unrecorded_resolution_is_treated_as_unresolved():
    """Not knowing whether the instrument could see is not the same as
    knowing it could."""
    advice = recommend(stage="critical", confidence=1.0,
                       resolution_usable=None, capture_trustworthy=True)
    assert advice.shutdown_advised is False


def test_a_weak_match_cannot_justify_planned_maintenance():
    advice = recommend(stage="severe",
                       confidence=CONFIDENCE_FOR_ACTION - 0.05,
                       resolution_usable=True, capture_trustworthy=True)
    assert URGENCY.index(advice.urgency) <= URGENCY.index("inspect_soon")


def test_a_very_weak_match_does_not_send_anyone_out_at_all():
    advice = recommend(stage="severe",
                       confidence=CONFIDENCE_FOR_INSPECTION - 0.05,
                       resolution_usable=True, capture_trustworthy=True)
    assert advice.urgency == "monitor"


def test_a_capped_urgency_says_what_it_would_have_been_and_why():
    """A cap nobody can see is a cap nobody will go and fix."""
    advice = recommend(stage="critical", confidence=1.0,
                       resolution_usable=True, capture_trustworthy=False)
    assert advice.proposed == "immediate"
    assert advice.caps
    assert "held back because" in advice.headline
    assert "would mean" in advice.headline


def test_a_good_finding_on_a_good_capture_is_not_capped():
    """The guard must not swallow the case it exists to allow through."""
    advice = recommend(stage="critical", confidence=0.95,
                       resolution_usable=True, capture_trustworthy=True)
    assert advice.capped is False
    assert advice.urgency == "immediate"
    assert advice.shutdown_advised is True


def test_a_recovering_fault_is_not_escalated():
    from app.ai.recommendation import direction_of as heading
    advice = recommend(stage="severe", confidence=0.9,
                       direction=heading([0.9, 0.6, 0.3]),
                       resolution_usable=True, capture_trustworthy=True)
    assert advice.urgency == "monitor"


# ----------------------------------------------------------- action -----

def test_the_recommendation_carries_words_an_engineer_can_act_on():
    advice = recommend(stage="developing", confidence=0.8,
                       resolution_usable=True, capture_trustworthy=True,
                       action_now="Stop and replace the bearing.",
                       action_planned="Plan a bearing inspection.")
    assert advice.action
    assert "inspection" in advice.action


def test_an_urgent_finding_gets_the_urgent_action_not_the_planned_one():
    advice = recommend(stage="critical", confidence=0.95,
                       resolution_usable=True, capture_trustworthy=True,
                       action_now="Stop and replace the bearing.",
                       action_planned="Plan a bearing inspection.")
    assert "Stop and replace" in advice.action


def test_a_rising_finding_says_the_interval_matters():
    from app.ai.recommendation import direction_of as heading
    advice = recommend(stage="developing", confidence=0.8,
                       direction=heading([0.3, 0.5, 0.7]),
                       resolution_usable=True, capture_trustworthy=True,
                       action_planned="Plan an inspection.")
    assert "getting worse" in advice.action


def test_a_fault_with_no_recorded_action_still_returns_something_usable():
    advice = recommend(stage="watch", confidence=0.6, resolution_usable=True,
                       capture_trustworthy=True)
    assert advice.action


def test_the_history_is_capped_so_a_row_cannot_grow_without_limit():
    assert 4 <= HISTORY_LENGTH <= 50
