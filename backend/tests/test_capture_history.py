"""Tests for the 7/30-day window logic — MOM items 10 and 12.

The behaviour worth protecting is the *withholding*. A trend arrow is easy to
draw and almost always wrong early in a deployment, so these tests pin both
directions: it must appear when the data supports it, and must not appear when
it does not. A card that always withheld would look identical to a working one
until someone waited three days to find out.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.capture_history import _trend_for, FLAT_BAND, MIN_POINTS_FOR_TREND

NOW = datetime.now(timezone.utc)


def ramp(n: int, span_h: float, start: float, end: float):
    """n captures evenly spread over span_h hours, value ramping start -> end."""
    return [
        (NOW - timedelta(hours=span_h) + timedelta(hours=span_h * i / (n - 1)),
         start + (end - start) * i / (n - 1))
        for i in range(n)
    ]


# ------------------------------------------------------------- withholding --

def test_too_few_captures_withholds():
    change, direction, reason = _trend_for(ramp(3, 0.67, 0.02, 0.02), 7, 0.67)
    assert change is None
    assert direction == "unknown"
    assert str(MIN_POINTS_FOR_TREND) in reason


def test_enough_captures_but_too_short_a_span_withholds():
    """The case this project actually hit: 30 captures in 40 minutes.

    Point count alone would pass. The span is what makes it meaningless — forty
    minutes of data describes forty minutes however many samples it holds.
    """
    change, _, reason = _trend_for(ramp(30, 0.67, 0.02, 0.02), 7, 0.67)
    assert change is None
    assert "spans" in reason


def test_span_threshold_is_a_real_boundary():
    """71 h withheld, 72 h reported, in a 30-day window (10% of 720 h)."""
    assert _trend_for(ramp(30, 71, 0.020, 0.028), 30, 71)[0] is None
    assert _trend_for(ramp(30, 72, 0.020, 0.028), 30, 72)[0] is not None


# ---------------------------------------------------------------- reporting --

def test_a_rise_is_reported():
    change, direction, reason = _trend_for(ramp(30, 72, 0.020, 0.028), 7, 72)
    assert direction == "rising"
    assert change > 0
    assert reason is None


def test_a_fall_is_reported():
    change, direction, _ = _trend_for(ramp(30, 72, 0.020, 0.014), 7, 72)
    assert direction == "falling"
    assert change < 0


def test_a_steady_level_reads_flat_not_rising():
    """Vibration wanders a little with nothing changing. Without a dead band
    every card would carry an arrow permanently, which trains readers to ignore
    it — the opposite of what the arrow is for."""
    change, direction, _ = _trend_for(ramp(30, 72, 0.0200, 0.0201), 7, 72)
    assert direction == "flat"
    assert abs(change) < FLAT_BAND


def test_half_vs_half_of_a_linear_ramp_is_half_the_end_to_end_change():
    """+40% end to end reads as roughly +19% between the window's two halves.

    Pinned because it is the kind of thing that looks like a bug to someone
    comparing the card against the first and last readings, and because a
    "fix" that reported the end-to-end change would overstate every trend.
    """
    change, _, _ = _trend_for(ramp(30, 72, 0.020, 0.028), 7, 72)
    assert change == pytest.approx(0.189, abs=0.01)


def test_a_zero_baseline_does_not_divide_by_zero():
    change, direction, reason = _trend_for(ramp(30, 72, 0.0, 0.0), 7, 72)
    assert change is None
    assert reason
