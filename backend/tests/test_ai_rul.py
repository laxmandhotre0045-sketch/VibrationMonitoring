"""Remaining useful life, and the far commoner answer — section 13.

The requirement opens with the condition, not the calculation: "RUL should
be provided only when enough historical trend data is available." So most
of these tests are about refusing, and that is the right proportion. RUL is
the most dangerous number this platform can produce — wrong one way a
machine fails unattended, wrong the other a healthy line is stopped.

The one test worth reading twice is the exponential one. A fault that is
accelerating and one that is not look nearly identical over a few months of
data — 0.97 against 0.99 on the fit — and they differ by a month at the
threshold. Getting that wrong under-calls the urgency, which is the
dangerous direction.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from app.ai.rul import (
    MAX_HORIZON_DAYS,
    MIN_FIT_QUALITY,
    MIN_HISTORY_DAYS,
    MIN_POINTS,
    estimate,
)

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def series(days: float, count: int, fn, noise: float = 0.0, seed: int = 11):
    rng = random.Random(seed)
    out = []
    for i in range(count):
        share = i / (count - 1)
        out.append((NOW - timedelta(days=days) + timedelta(days=days * share),
                    fn(days * share) + rng.gauss(0, noise)))
    return out


FULL_CONTEXT = dict(has_load=True, operating_hours=8000.0,
                    maintenance_history=2, failure_history=0)


# ------------------------------------------------- refusing, in detail ---

def test_this_gateways_history_is_far_too_short():
    """162 captures across five days. The readings exist; the span does
    not, and the span is what an extrapolation rests on."""
    verdict = estimate(
        history=series(5, 162, lambda x: 0.4 + 0.01 * x, 0.01),
        threshold=1.0, now=NOW)

    assert verdict.available is False
    assert "insufficient history" in verdict.reason
    assert verdict.points == 162
    assert verdict.span_days == pytest.approx(5.0, abs=0.1)


def test_a_refusal_still_reports_how_much_history_there_was():
    """Reporting the count and leaving the span null makes the shortfall
    look like half a measurement."""
    verdict = estimate(history=series(90, MIN_POINTS - 5, lambda x: 0.4 + 0.005 * x),
                       threshold=1.0, now=NOW)
    assert verdict.available is False
    assert verdict.points == MIN_POINTS - 5
    assert verdict.span_days == pytest.approx(90.0, abs=0.1)


def test_many_readings_over_a_few_days_are_not_history():
    """A thousand captures in a week describe a week."""
    verdict = estimate(history=series(10, 400, lambda x: 0.4 + 0.02 * x, 0.01),
                       threshold=1.0, now=NOW)
    assert verdict.available is False
    assert f"{MIN_HISTORY_DAYS:.0f}" in verdict.reason


def test_a_flat_feature_has_no_failure_date():
    verdict = estimate(history=series(120, 80, lambda x: 0.5, 0.02),
                       threshold=1.0, now=NOW)
    assert verdict.available is False
    assert verdict.direction in ("steady", "falling")


def test_a_recovering_feature_is_refused_rather_than_extrapolated():
    verdict = estimate(history=series(120, 80, lambda x: 0.9 - 0.004 * x, 0.01),
                       threshold=1.0, now=NOW)
    assert verdict.available is False
    assert verdict.direction == "falling"


def test_scatter_with_a_direction_is_not_a_trend():
    """A slope fitted through noise produces a confident-looking date on
    nothing."""
    verdict = estimate(history=series(120, 80, lambda x: 0.4 + 0.002 * x, 0.25),
                       threshold=1.0, now=NOW)
    assert verdict.available is False
    assert verdict.fit_quality < MIN_FIT_QUALITY
    assert "scatter with a direction" in verdict.reason


def test_a_trend_beyond_the_horizon_is_refused():
    """Reaching the threshold in 900 days, extrapolated from 200, is a way
    of saying nothing is happening."""
    verdict = estimate(
        history=series(200, 120, lambda x: 0.30 + 0.0006 * x, 0.004),
        threshold=1.0, now=NOW)
    assert verdict.available is False
    assert f"{MAX_HORIZON_DAYS:.0f}" in verdict.reason


def test_the_refusal_uses_the_documents_own_words():
    """Section 13 specifies the message for the insufficient-data case."""
    verdict = estimate(history=series(5, 30, lambda x: 0.5 + 0.01 * x),
                       threshold=1.0, now=NOW)
    assert "RUL prediction not available" in verdict.reason
    assert "insufficient history" in verdict.reason


# ------------------------------------------------------- when it answers --

def test_a_clean_climb_produces_a_range_not_a_date():
    """"57 days" is a claim about confidence nobody has."""
    verdict = estimate(
        history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.015),
        threshold=1.0, feature_name="envelope BPFO energy",
        now=NOW, **FULL_CONTEXT)

    assert verdict.available is True
    assert verdict.days_low is not None and verdict.days_high is not None
    assert verdict.days_high > verdict.days_low
    assert verdict.assumption == "linear"
    assert verdict.direction == "rising"
    assert verdict.degradation_rate > 0


def test_an_accelerating_fault_is_not_reported_as_a_straight_line():
    """The test worth reading twice.

    A clean exponential climb is fitted well by a straight line too — 0.97
    against 0.99 — so any real preference margin picks "linear" and reports
    a fault that is accelerating as one that is not. On the same data that
    is the difference between 42-54 days and 16-21: the straight line says
    there is a month and a half of life left when there are two weeks.
    """
    history = series(120, 90, lambda x: 0.25 * math.exp(0.010 * x), 0.01)
    verdict = estimate(history=history, threshold=1.0, now=NOW,
                       **FULL_CONTEXT)

    assert verdict.available is True
    assert verdict.assumption == "exponential"

    straight = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x,
                                       0.015),
                        threshold=1.0, now=NOW, **FULL_CONTEXT)
    assert verdict.days_high < straight.days_low, (
        "the accelerating fault must come due sooner than the linear one")


def test_a_noisy_trend_widens_the_range_rather_than_hiding_it():
    tight = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.015),
                     threshold=1.0, now=NOW, **FULL_CONTEXT)
    loose = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.06),
                     threshold=1.0, now=NOW, **FULL_CONTEXT)

    assert (loose.days_high - loose.days_low) > (tight.days_high -
                                                 tight.days_low)


def test_a_wide_range_cannot_be_called_high_confidence():
    """A fit can describe a noisy trend faithfully and still put the
    threshold anywhere across a month. The width is what gets planned
    around."""
    loose = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.06),
                     threshold=1.0, now=NOW, **FULL_CONTEXT)
    assert loose.range_width > 0.35
    assert loose.confidence != "high"


def test_a_machine_already_past_the_threshold_has_no_life_to_estimate():
    verdict = estimate(history=series(120, 90, lambda x: 0.6 + 0.006 * x, 0.01),
                       threshold=1.0, now=NOW, **FULL_CONTEXT)
    assert verdict.available is True
    assert verdict.days_low == 0.0
    assert "already at or past" in verdict.reason


# --------------------------------------------- inputs that do not exist --

def test_the_inputs_section_13_1_asks_for_and_cannot_have_are_named():
    """Temperature is listed as an RUL input and nothing on this platform
    measures one. An estimate that quietly omits it claims a completeness
    it does not have."""
    verdict = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.015),
                       threshold=1.0, now=NOW)
    assert verdict.missing_inputs
    assert any("temperature" in m.lower() for m in verdict.missing_inputs)


def test_an_estimate_missing_most_of_its_inputs_is_not_called_reliable():
    """Section 13.2 asks for "whether RUL is reliable or not" as its own
    field, separately from confidence. Confidence is about the fit;
    reliability is about whether the platform had what the method needs."""
    bare = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.015),
                    threshold=1.0, now=NOW)
    full = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.015),
                    threshold=1.0, now=NOW, **FULL_CONTEXT)

    assert bare.reliable is False
    assert full.reliable is True
    assert bare.confidence == full.confidence, (
        "the fit is identical; only the available inputs differ")


def test_every_output_section_13_2_asks_for_is_present():
    verdict = estimate(history=series(120, 90, lambda x: 0.30 + 0.004 * x, 0.015),
                       threshold=1.0, now=NOW, **FULL_CONTEXT).as_dict()
    for field in ("days_low", "days_high", "confidence", "degradation_rate",
                  "direction", "assumption", "reliable", "reason"):
        assert field in verdict, field
